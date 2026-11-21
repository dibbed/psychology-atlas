import hashlib
import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django_otp import login as otp_login, verify_token
from django_otp.models import Device
from django_otp.plugins.otp_static.models import StaticDevice
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .cms_models import AccountSecurityState, AdminLoginThrottle, AdminAuditEvent, AdminSession
from .cms_policy import CMSFailure, effective_permissions, policy_lock


def generation(user_id):
    return AccountSecurityState.objects.filter(user_id=user_id).values_list("security_version", flat=True).first() or 0


def login_attempt(username, ip):
    # DB-backed account AND IP limits are shared by every process; no permanent account lockout.
    now = timezone.now()
    keys = [salted_hmac("cms-login", value).hexdigest() for value in ("account:" + username.casefold(), "ip:" + ip)]
    with policy_lock():
        rows = []
        for key in keys:
            row, _ = AdminLoginThrottle.objects.get_or_create(key=key, defaults={"window_start": now})
            if row.window_start <= now - timedelta(minutes=5):
                row.window_start, row.failures = now, 0
                row.save(update_fields=("window_start", "failures"))
            rows.append(row)
        if any(row.failures >= 5 for row in rows):
            raise CMSFailure("LOGIN_THROTTLED", 429)
        AdminLoginThrottle.objects.filter(key__in=keys).update(failures=F("failures") + 1)
    return keys


def login_succeeded(keys):
    with policy_lock():
        AdminLoginThrottle.objects.filter(key__in=keys).update(failures=0)


def verify_mfa(user, token, method="totp"):
    if not isinstance(token, str) or len(token) > 32 or method not in {"totp", "recovery"}:
        raise CMSFailure("INVALID_MFA", 400)
    if method == "recovery":
        device = StaticDevice.objects.filter(user=user, name="backup", confirmed=True).first()
    else:
        from two_factor.utils import default_device
        device = default_device(user)
    if device is None:
        raise CMSFailure("MFA_ENROLLMENT_REQUIRED")
    device = verify_token(user, device.persistent_id, token)
    if device is None:
        raise CMSFailure("MFA_INVALID")
    return device


def establish_session(request, device):
    now = timezone.now()
    with policy_lock():
        user = User.objects.get(pk=request.user.pk)
        if "cms_enter" not in effective_permissions(user):
            raise CMSFailure("PERMISSION_DENIED")
        if request.session.get("cms_security_version") != generation(user.pk):
            raise CMSFailure("UNAUTHENTICATED")
        # Only a freshly verified package device can cross the CMS boundary.
        device = Device.from_persistent_id(device.persistent_id)
        if device is None or device.user_id != user.pk or not device.confirmed:
            raise CMSFailure("MFA_REQUIRED")
        old_id = request.session.get("cms_session_id")
        if old_id:
            AdminSession.objects.filter(pk=old_id, user=user).update(revoked_at=now)
        request.session.cycle_key()
        request.session.set_expiry(8 * 3600)
        otp_login(request, device)
        request.session.save()
        row = AdminSession.objects.create(user=user, django_session_id=request.session.session_key,
            last_seen=now, expires_at=now + timedelta(hours=8), mfa_at=now, security_version=generation(user.pk))
        request.session["cms_session_id"] = str(row.pk)
        request.session.pop("cms_pending_until", None)
        request.session.pop("cms_verified_at", None)
        request.session.save()
        AdminAuditEvent.objects.create(actor=user, target_id=user.pk, action="session.login", outcome="success")
        return row


def current_session(session_id, user, session_key=None, touch=False):
    now = timezone.now()
    row = AdminSession.objects.select_for_update().filter(pk=session_id, user_id=user.pk, revoked_at__isnull=True).first() if session_id else None
    fresh = User.objects.filter(pk=user.pk, is_active=True, is_staff=True).first()
    if (row is None or fresh is None or row.django_session_id is None
        or (session_key is not None and row.django_session_id != session_key)
        or row.expires_at <= now or row.last_seen <= now - timedelta(minutes=30)
        or row.security_version != generation(user.pk)):
        raise CMSFailure("UNAUTHENTICATED")
    stored = Session.objects.filter(pk=row.django_session_id, expire_date__gt=now).first()
    if stored is None:
        raise CMSFailure("UNAUTHENTICATED")
    device_id = stored.get_decoded().get("otp_device_id")
    device = Device.from_persistent_id(device_id) if device_id else None
    if device is None or device.user_id != user.pk or not device.confirmed:
        raise CMSFailure("UNAUTHENTICATED")
    if "cms_enter" not in effective_permissions(fresh):
        raise CMSFailure("PERMISSION_DENIED")
    if touch:
        AdminSession.objects.filter(pk=row.pk, revoked_at__isnull=True).update(last_seen=now)
    return row


def binding(action, target_id, payload):
    return hashlib.sha256(json.dumps([action, target_id, payload], sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def consume_step_up(session_id, user, action, target_id, payload):
    row = AdminSession.objects.select_for_update().get(pk=session_id, user=user)
    proof = row.step_up
    if proof.get("digest") != binding(action, target_id, payload) or proof.get("expires", 0) <= timezone.now().timestamp():
        raise CMSFailure("STEP_UP_REQUIRED")
    row.step_up = {}
    row.save(update_fields=("step_up",))


def revoke_account(user):
    # Caller owns policy_lock; generation prevents same-second JWT/recovery races.
    now = timezone.now()
    state, _ = AccountSecurityState.objects.get_or_create(user=user)
    AccountSecurityState.objects.filter(pk=state.pk).update(security_version=F("security_version") + 1, revoked_before=now)
    rows = AdminSession.objects.filter(user=user, revoked_at__isnull=True)
    Session.objects.filter(pk__in=list(rows.values_list("django_session_id", flat=True))).delete()
    rows.update(revoked_at=now, step_up={})
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)


def security_status():
    return {"mfa": "AVAILABLE_TOTP", "recovery_codes": "AVAILABLE_ONE_TIME", "login_throttle": "SHARED_DATABASE",
        "email_sms_recovery": "UNAVAILABLE", "offline_owner_recovery": "AVAILABLE_LOCAL_COMMAND",
        "production_ready": False, "blockers": ["TARGET_HTTPS_PROXY_AND_COOKIE_REHEARSAL", "STAGING_MFA_RECOVERY_REHEARSAL"]}
