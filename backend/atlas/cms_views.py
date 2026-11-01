from datetime import timedelta
import uuid

from django.db import DatabaseError, transaction
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import Group, User
from django.contrib.sessions.models import Session
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django_otp.models import Device
from rest_framework.authentication import CSRFCheck, SessionAuthentication
from rest_framework.exceptions import APIException
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer
from rest_framework.views import APIView

from .cms_capabilities import CAPABILITIES, READY_CAPABILITIES
from .cms_models import AdminAuditEvent, AdminSession, RolePolicy
from .cms_policy import CMSFailure, effective_permissions, grantable, mutate_role, policy_lock, require, visible_group
from .cms_sessions import (binding, consume_step_up, current_session, establish_session, login_attempt,
    login_succeeded, revoke_account, security_status, verify_mfa)


class PendingSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        check = CSRFCheck(lambda r: None)
        check.process_request(request)
        if check.process_view(request, None, (), {}):
            raise CMSFailure("CSRF_FAILED")


class AdminSessionAuthentication(PendingSessionAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            with policy_lock():
                request.cms_session = current_session(request.session.get("cms_session_id"), result[0], request.session.session_key, touch=True)
        return result


class AdminPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated or not hasattr(request, "cms_session"):
            raise CMSFailure("UNAUTHENTICATED")
        capability = getattr(view, "capability", None)
        require(request.user, capability)
        return True


@method_decorator(transaction.non_atomic_requests, name="dispatch")
class AdminAPIView(APIView):
    renderer_classes = (JSONRenderer,)
    authentication_classes = (AdminSessionAuthentication,)
    permission_classes = (AdminPermission,)
    capability = None  # New endpoints fail closed until explicitly assigned.

    def initial(self, request, *args, **kwargs):
        self.request_id = uuid.uuid4()
        return super().initial(request, *args, **kwargs)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        response["X-Request-ID"] = str(self.request_id)
        return response

    def handle_exception(self, exc):
        from .cms_audit import security_event
        if isinstance(exc, DatabaseError):
            # No SQL, request body or exception text enters the response or audit metadata.
            response = Response({"code": "WRITE_FAILED", "message": "ذخیره انجام نشد؛ دوباره تلاش کنید."}, status=503)
        elif not isinstance(exc, APIException):
            response = Response({"code": "INTERNAL_ERROR", "message": "عملیات انجام نشد؛ دوباره تلاش کنید."}, status=503)
        else:
            response = super().handle_exception(exc)
        if "code" not in response.data:
            response.data = {"code": "INVALID_INPUT" if response.status_code == 400 else "PERMISSION_DENIED", "field_errors": response.data}
        response.data["request_id"] = str(self.request_id)
        if response.status_code in {400, 403, 404, 409, 412, 428, 429, 503}:
            try:
                security_event(getattr(self.request, "user", None), str(response.data["code"]), response.status_code, self.request_id)
            except DatabaseError:
                response = Response({"code": "AUDIT_UNAVAILABLE", "message": "ثبت رویداد در دسترس نیست؛ ذخیره انجام نشد.", "request_id": str(self.request_id)}, status=503)
        return response


class AuthAPIView(AdminAPIView):
    authentication_classes = (PendingSessionAuthentication,)
    permission_classes = ()

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            PendingSessionAuthentication().enforce_csrf(request)


def payload(request, allowed):
    if not isinstance(request.data, dict) or set(request.data) - set(allowed):
        raise CMSFailure("INVALID_FIELDS", 400)
    return request.data


def expected_version(request):
    value = request.headers.get("If-Match")
    if value is None:
        raise CMSFailure("PRECONDITION_REQUIRED", 428)
    if not (value.startswith('"') and value.endswith('"') and value[1:-1].isascii() and value[1:-1].isdigit() and len(value) <= 22):
        raise CMSFailure("INVALID_PRECONDITION", 400)
    return int(value[1:-1])


def versioned(data, version=None):
    response = Response(data)
    response["ETag"] = '"%s"' % (RolePolicy.objects.get(pk=1).version if version is None else version)
    return response


def page(request, rows, extra=()):
    if set(request.query_params) - {"page", "page_size", *extra}:
        raise CMSFailure("INVALID_QUERY", 400)
    values = [request.query_params.get("page", "1"), request.query_params.get("page_size", "30")]
    if any(not v.isascii() or not v.isdigit() or len(v) > 9 or int(v) < 1 for v in values) or int(values[1]) > 100:
        raise CMSFailure("INVALID_QUERY", 400)
    number, size = map(int, values)
    count = len(rows) if isinstance(rows, list) else rows.count()
    return {"count": count, "page": number, "page_size": size}, rows[(number - 1) * size:number * size]


class CSRFView(AuthAPIView):
    def get(self, request):
        return Response({"csrf_token": get_token(request), "mfa": "REQUIRED"})


class LoginView(AuthAPIView):
    def post(self, request):
        data = payload(request, {"username", "password"})
        if not all(isinstance(data.get(k), str) and 0 < len(data[k]) <= n for k, n in (("username", 254), ("password", 1024))):
            raise CMSFailure("INVALID_INPUT", 400)
        keys = login_attempt(data["username"], request.META.get("REMOTE_ADDR", ""))
        user = authenticate(request, username=data["username"], password=data["password"])
        if user is None or "cms_enter" not in effective_permissions(user):
            AdminAuditEvent.objects.create(action="session.login", outcome="denied")
            raise CMSFailure("LOGIN_FAILED")
        with policy_lock():
            require(user, "cms_enter")
            old_id = request.session.get("cms_session_id")
            if old_id:
                AdminSession.objects.filter(pk=old_id, django_session_id=request.session.session_key).update(revoked_at=timezone.now(), step_up={})
            request.session.flush()
            login(request._request, user)
            request.session.set_expiry(300)
            request.session["cms_pending_until"] = (timezone.now() + timedelta(minutes=5)).timestamp()
        login_succeeded(keys)
        return Response({"status": "MFA_REQUIRED", "csrf_token": get_token(request), "setup_url": "/account/two_factor/setup/", "verify_url": "/api/admin/auth/verify/"})


def pending_user(request):
    user = request._request.user
    if not user.is_authenticated:
        raise CMSFailure("UNAUTHENTICATED")
    require(user, "cms_enter")
    from .cms_sessions import generation
    if request.session.get("cms_security_version") != generation(user.pk):
        raise CMSFailure("UNAUTHENTICATED")
    if request.session.get("cms_pending_until", 0) <= timezone.now().timestamp():
        raise CMSFailure("UNAUTHENTICATED")
    return user


class VerifyView(AuthAPIView):
    def post(self, request):
        data = payload(request, {"token", "method"})
        user = pending_user(request)
        keys = login_attempt(user.username, request.META.get("REMOTE_ADDR", ""))
        device = verify_mfa(user, data.get("token"), data.get("method", "totp"))
        establish_session(request._request, device)
        login_succeeded(keys)
        return Response({"status": "AUTHENTICATED", "csrf_token": get_token(request)})


class CompleteView(AuthAPIView):
    def post(self, request):
        payload(request, set())
        user = request._request.user
        if not user.is_authenticated or request.session.get("cms_verified_at", 0) <= (timezone.now() - timedelta(seconds=60)).timestamp():
            raise CMSFailure("MFA_REQUIRED")
        from .cms_sessions import generation
        if request.session.get("cms_security_version") != generation(user.pk):
            raise CMSFailure("UNAUTHENTICATED")
        device_id = request.session.get("otp_device_id")
        device = Device.from_persistent_id(device_id) if device_id else None
        if device is None:
            raise CMSFailure("MFA_REQUIRED")
        establish_session(request._request, device)
        return Response({"status": "AUTHENTICATED", "csrf_token": get_token(request)})


class LogoutView(AuthAPIView):
    def post(self, request):
        payload(request, set())
        with policy_lock():
            actor = request.user if request.user.is_authenticated else None
            row_id = request.session.get("cms_session_id")
            if row_id:
                AdminSession.objects.filter(pk=row_id, django_session_id=request.session.session_key).update(revoked_at=timezone.now(), step_up={})
            logout(request._request)
            AdminAuditEvent.objects.create(actor=actor, action="session.logout", outcome="success")
        return Response({"status": "LOGGED_OUT"})


def ready_content_kinds(held):
    from .cms_domains import DOMAIN_SPECS
    return [kind for kind, spec in DOMAIN_SPECS.items() if "cms_" + spec["domain"] + "_view" in held]


class MeView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request):
        held = effective_permissions(request.user)
        return Response({"user": {"id": request.user.pk, "username": request.user.username},
            "capabilities": sorted(held & CAPABILITIES), "ready_capabilities": sorted(held & READY_CAPABILITIES),
            "session": {"id": str(request.cms_session.pk), "expires_at": request.cms_session.expires_at}, "security": security_status(),
            "ready_content_kinds": ready_content_kinds(held)})


class CatalogView(AdminAPIView):
    capability = "cms_catalog"

    def get(self, request):
        held = effective_permissions(request.user)
        return Response({"ready_content_kinds": ready_content_kinds(held), "capabilities": [{"codename": c, "status": "READY" if c in READY_CAPABILITIES else "PLANNED"}
            for c in sorted(held & CAPABILITIES)]})


class StepUpView(AdminAPIView):
    capability = "cms_enter"

    def post(self, request):
        data = payload(request, {"token", "method", "action", "target_id", "payload"})
        action, target_id, bound = data.get("action"), data.get("target_id"), data.get("payload")
        valid_target = type(target_id) is int and target_id >= 0
        if action == "revoke_session":
            import uuid
            try:
                target_id = str(uuid.UUID(str(target_id)))
                valid_target = True
            except (ValueError, TypeError, AttributeError):
                valid_target = False
        if action not in {"user", "group", "delete_group", "create_group", "revoke_account", "revoke_session", "revoke_mfa", "regenerate_recovery", "review_policy", "case_publish", "case_withdraw"} or not valid_target or not isinstance(bound, dict):
            raise CMSFailure("INVALID_INPUT", 400)
        required = "cms_roles_edit" if action in {"user", "group", "delete_group", "create_group"} else "cms_user_revoke_sessions"
        if action == "review_policy":
            if target_id != 1:
                raise CMSFailure("NOT_FOUND", 404)
            require(request.user, "cms_owner")
            required = "cms_settings_edit"
        if action in {"case_publish", "case_withdraw"}:
            required = "cms_publication_apply_cases" if action == "case_publish" else "cms_publication_withdraw_cases"
            require(request.user, "cms_cases_view")
        if action in {"revoke_mfa", "regenerate_recovery"}:
            if target_id != request.user.pk:
                raise CMSFailure("NOT_FOUND", 404)
            required = "cms_enter"
        require(request.user, required)
        keys = login_attempt(request.user.username, request.META.get("REMOTE_ADDR", ""))
        device = verify_mfa(request.user, data.get("token"), data.get("method", "totp"))
        with policy_lock():
            row = current_session(request.cms_session.pk, request.user)
            request.session.cycle_key()
            request.session.save()
            row.django_session_id = request.session.session_key
            row.step_up = {"digest": binding(action, target_id, bound), "expires": (timezone.now() + timedelta(minutes=10)).timestamp()}
            row.save(update_fields=("django_session", "step_up"))
            AdminAuditEvent.objects.create(actor=request.user, target_id=target_id if type(target_id) is int else None, action="session.step_up", outcome="success")
        login_succeeded(keys)
        return Response({"status": "STEP_UP_READY"})


class PermissionsView(AdminAPIView):
    capability = "cms_roles_edit"

    def get(self, request):
        return versioned({"permissions": sorted(grantable(request.user))})


class GroupsView(AdminAPIView):
    capability = "cms_roles_view"

    def get(self, request):
        groups = [g for g in Group.objects.prefetch_related("permissions__content_type").order_by("pk") if visible_group(request.user, g)]
        meta, groups = page(request, groups)
        return versioned({**meta, "results": [{"id": g.pk, "name": g.name, "permissions": sorted(p.codename for p in g.permissions.all())} for g in groups]})

    def post(self, request):
        data = payload(request, {"name", "permissions"})
        result = mutate_role(request.user.pk, "create_group", 0, data, expected_version(request), request.cms_session.pk)
        return versioned({"status": "CREATED"}, result)


class GroupView(AdminAPIView):
    capability = "cms_roles_view"

    def get(self, request, target_id):
        group = Group.objects.filter(pk=target_id).first()
        if group is None or not visible_group(request.user, group):
            raise CMSFailure("NOT_FOUND", 404)
        return versioned({"id": group.pk, "name": group.name, "permissions": sorted(group.permissions.values_list("codename", flat=True))})

    def post(self, request, target_id):
        result = mutate_role(request.user.pk, "group", target_id, payload(request, {"permissions"}), expected_version(request), request.cms_session.pk)
        return versioned({"status": "UPDATED"}, result)


class GroupDeleteView(AdminAPIView):
    capability = "cms_roles_edit"

    def post(self, request, target_id):
        result = mutate_role(request.user.pk, "delete_group", target_id, payload(request, set()), expected_version(request), request.cms_session.pk)
        return versioned({"status": "DELETED"}, result)


class RoleUserView(AdminAPIView):
    capability = "cms_roles_view"

    def get(self, request, target_id):
        user = User.objects.filter(pk=target_id).first()
        if user is None:
            raise CMSFailure("NOT_FOUND", 404)
        return versioned({"id": user.pk, "username": user.username, "is_active": user.is_active, "is_staff": user.is_staff,
            "is_superuser": user.is_superuser, "groups": list(user.groups.values_list("pk", flat=True)),
            "permissions": sorted(effective_permissions(user) & grantable(request.user))})

    def post(self, request, target_id):
        result = mutate_role(request.user.pk, "user", target_id,
            payload(request, {"permissions", "groups", "is_active", "is_staff", "is_superuser"}), expected_version(request), request.cms_session.pk)
        return versioned({"status": "UPDATED"}, result)


class SessionsView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request):
        user_id = request.query_params.get("user_id", str(request.user.pk))
        if not user_id.isascii() or not user_id.isdigit() or len(user_id) > 20:
            raise CMSFailure("INVALID_INPUT", 400)
        if int(user_id) != request.user.pk:
            require(request.user, "cms_user_revoke_sessions")
        meta, rows = page(request, AdminSession.objects.filter(user_id=user_id).order_by("-created_at"), ("user_id",))
        return Response({**meta, "results": [{"id": str(r.pk), "created_at": r.created_at, "last_seen": r.last_seen, "expires_at": r.expires_at, "revoked_at": r.revoked_at} for r in rows]})


class RevokeSessionView(AdminAPIView):
    capability = "cms_enter"

    def post(self, request, session_id):
        data = payload(request, set())
        with policy_lock(expected_version(request)):
            current_session(request.cms_session.pk, request.user)
            rows = AdminSession.objects.filter(pk=session_id)
            if "cms_user_revoke_sessions" not in effective_permissions(request.user):
                rows = rows.filter(user=request.user)
            row = rows.first()
            if row is None:
                raise CMSFailure("NOT_FOUND", 404)
            if row.user_id != request.user.pk:
                consume_step_up(request.cms_session.pk, request.user, "revoke_session", str(row.pk), data)
            row.revoked_at, row.step_up = timezone.now(), {}
            row.save(update_fields=("revoked_at", "step_up"))
            Session.objects.filter(pk=row.django_session_id).delete()
            AdminAuditEvent.objects.create(actor=request.user, target_id=row.user_id, action="session.revoke", outcome="success")
        return Response({"status": "REVOKED"})


class RevokeAccountView(AdminAPIView):
    capability = "cms_user_revoke_sessions"

    def post(self, request, target_id):
        data = payload(request, set())
        with policy_lock(expected_version(request)):
            current_session(request.cms_session.pk, request.user)
            require(request.user, "cms_user_revoke_sessions")
            target = User.objects.filter(pk=target_id).first()
            if target is None:
                raise CMSFailure("NOT_FOUND", 404)
            consume_step_up(request.cms_session.pk, request.user, "revoke_account", target_id, data)
            revoke_account(target)
            AdminAuditEvent.objects.create(actor=request.user, target_id=target_id, action="account.revoke", outcome="success")
        return Response({"status": "REVOKED"})


class RevokeMFAView(AdminAPIView):
    capability = "cms_enter"

    def post(self, request):
        data = payload(request, set())
        with policy_lock(expected_version(request)):
            current_session(request.cms_session.pk, request.user)
            consume_step_up(request.cms_session.pk, request.user, "revoke_mfa", request.user.pk, data)
            from django_otp import devices_for_user
            for device in devices_for_user(request.user, confirmed=None):
                device.delete()
            revoke_account(request.user)
            AdminAuditEvent.objects.create(actor=request.user, target_id=request.user.pk, action="mfa.revoke", outcome="success")
        logout(request._request)
        return Response({"status": "MFA_ENROLLMENT_REQUIRED"})
