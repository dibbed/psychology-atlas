"""Bridge the maintained enrollment/login flow; restrict raw auth writers."""
from django.contrib import admin
from django.contrib.auth import logout
from django.contrib.auth.models import Group, Permission, User
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.db import transaction
from django.http import JsonResponse
from django.middleware.gzip import GZipMiddleware
from django.utils import timezone
from django.utils.decorators import method_decorator
from two_factor.admin import AdminSiteOTPRequired
from two_factor.signals import user_verified
from two_factor.views import BackupTokensView, SetupView
from two_factor.forms import TOTPDeviceForm
from django_otp import verify_token

from .cms_models import AccountSecurityState, AdminLoginThrottle, AdminAuditEvent, AdminSession, RolePolicy
from .cms_policy import CMSFailure, effective_permissions
from .cms_sessions import generation, login_attempt, login_succeeded
from .cms_audit import failure_response


class CMSGZipMiddleware(GZipMiddleware):
    def process_response(self, request, response):
        # Compression weakens ETags; CMS preconditions require the exact strong version tag.
        if request.path.startswith("/api/admin/"):
            return response
        return super().process_response(request, response)


@receiver(user_verified)
def verified_session(sender, request, user, device, **kwargs):
    if "cms_enter" in effective_permissions(user):
        request.session["cms_verified_at"] = timezone.now().timestamp()


@receiver(user_logged_in)
def enrollment_verified(sender, request, user, **kwargs):
    request.session["cms_security_version"] = generation(user.pk)
    device = getattr(user, "otp_device", None)
    if device is not None and device.confirmed and device.user_id == user.pk:
        verified_session(sender, request, user, device)


@method_decorator(transaction.non_atomic_requests, name="dispatch")
class CMSSetupView(SetupView):
    def done(self, form_list, **kwargs):
        from .cms_policy import policy_lock, require
        try:
            with policy_lock():
                require(self.request.user, "cms_enter")
                if self.request.session.get("cms_security_version") != generation(self.request.user.pk):
                    raise CMSFailure("UNAUTHENTICATED")
                response = super().done(form_list, **kwargs)
                device = getattr(self.request.user, "otp_device", None)
                form = next(f for f in form_list if isinstance(f, TOTPDeviceForm))
                # Consume the enrollment proof with the package's replay protection too.
                device = verify_token(self.request.user, device.persistent_id, str(form.cleaned_data["token"]))
                if device is None:
                    raise CMSFailure("MFA_INVALID")
                verified_session(type(self), self.request, self.request.user, device)
                AdminAuditEvent.objects.create(actor=self.request.user, target_id=self.request.user.pk, action="mfa.enroll", outcome="success")
                return response
        except Exception as exc:
            return failure_response(self.request, exc)


@method_decorator(transaction.non_atomic_requests, name="dispatch")
class CMSBackupTokensView(BackupTokensView):
    def get_context_data(self, **kwargs):
        from django_otp.plugins.otp_static.models import StaticDevice
        # Existing recovery credentials are never redisplayed from a stolen session cookie.
        context = super(BackupTokensView, self).get_context_data(**kwargs)
        device = StaticDevice.objects.filter(user=self.request.user, name="backup").first()
        context["remaining"] = device.token_set.count() if device else 0
        return context

    def form_valid(self, form):
        from .cms_policy import policy_lock
        from .cms_sessions import consume_step_up, current_session
        try:
            with policy_lock():
                row = current_session(self.request.session.get("cms_session_id"), self.request.user, self.request.session.session_key)
                consume_step_up(row.pk, self.request.user, "regenerate_recovery", self.request.user.pk, {})
                super().form_valid(form)
                context = self.get_context_data()
                context["codes"] = list(self.get_device().token_set.values_list("token", flat=True))
                response = self.render_to_response(context)
                response.render()
                AdminAuditEvent.objects.create(actor=self.request.user, target_id=self.request.user.pk, action="mfa.recovery_codes", outcome="success")
                return response
        except Exception as exc:
            return failure_response(self.request, exc)


class CMSAdminSite(AdminSiteOTPRequired):
    def has_permission(self, request):
        if not super().has_permission(request):
            return False
        from .cms_policy import policy_lock
        from .cms_sessions import current_session
        try:
            with policy_lock():
                current_session(request.session.get("cms_session_id"), request.user, request.session.session_key, touch=True)
        except CMSFailure:
            return False
        return True


class ReadOnlySecurityAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(f.name for f in self.model._meta.fields) + tuple(f.name for f in self.model._meta.many_to_many)

    def has_view_permission(self, request, obj=None):
        return "cms_roles_view" in effective_permissions(request.user)


def configure_admin():
    admin.site.__class__ = CMSAdminSite
    # Password hashes, session keys, tokens and OTP seeds are never exposed as raw admin fields.
    if admin.site.is_registered(User):
        admin.site.unregister(User)
    if admin.site.is_registered(Group):
        admin.site.unregister(Group)
    class UserView(ReadOnlySecurityAdmin):
        fields = ("username", "email", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")
    admin.site.register(User, UserView)
    admin.site.register(Group, ReadOnlySecurityAdmin)
    from .models import SourceReference
    from .cms_domains import DOMAIN_SPECS, MODEL_KINDS, domain_for
    class ContentView(ReadOnlySecurityAdmin):
        # Raw DSM imports require the purpose-bound, audited CMS raw endpoint.
        # A Django-admin view permission does not grant that separate capability.
        def get_fields(self, request, obj=None):
            fields = super().get_fields(request, obj)
            return [field for field in fields if field not in {"raw_document", "source_payload"}]

        def has_view_permission(self, request, obj=None):
            return "cms_" + domain_for(MODEL_KINDS[self.model]) + "_view" in effective_permissions(request.user)
    for model in (spec["model"] for spec in DOMAIN_SPECS.values()):
        if admin.site.is_registered(model):
            admin.site.unregister(model)
        admin.site.register(model, ContentView)
    class SourceView(ReadOnlySecurityAdmin):
        def has_view_permission(self, request, obj=None):
            return "cms_source_view" in effective_permissions(request.user)
    if admin.site.is_registered(SourceReference):
        admin.site.unregister(SourceReference)
    admin.site.register(SourceReference, SourceView)
    # Legacy ModelAdmin registrations can write cases, quiz answers, learner history
    # and metadata outside the revision/audit/policy services. Never expose them.
    for model, handler in tuple(admin.site._registry.items()):
        if model._meta.app_label == "atlas" and not isinstance(handler, ReadOnlySecurityAdmin):
            admin.site.unregister(model)
    # No raw permission/device/session/security-state edit route; services own the writes.
    from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
    from django_otp.plugins.otp_totp.models import TOTPDevice
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
    for model in (Permission, StaticDevice, StaticToken, TOTPDevice, AdminSession, AccountSecurityState,
                  RolePolicy, AdminLoginThrottle, AdminAuditEvent, BlacklistedToken, OutstandingToken):
        if admin.site.is_registered(model):
            admin.site.unregister(model)


class CMSIntegrationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path == "/account/login/" and request.user.is_authenticated:
            if "cms_enter" not in effective_permissions(request.user):
                logout(request)
                response = JsonResponse({"code": "LOGIN_FAILED"}, status=403)
            elif request.session.get("cms_verified_at") and hasattr(request, "cms_login_keys"):
                login_succeeded(request.cms_login_keys)
        if request.path.startswith(("/api/admin/", "/admin/", "/account/")):
            response["Cache-Control"] = "no-store"
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.path.startswith("/account/"):
            return None
        if request.path == "/account/two_factor/disable/":
            return JsonResponse({"code": "USE_CMS_MFA_REVOKE", "endpoint": "/api/admin/auth/mfa/revoke/"}, status=403)
        if request.path != "/account/login/":
            if not request.user.is_authenticated or "cms_enter" not in effective_permissions(request.user):
                return JsonResponse({"code": "PERMISSION_DENIED"}, status=403)
            if request.session.get("cms_security_version") != generation(request.user.pk):
                return JsonResponse({"code": "UNAUTHENTICATED"}, status=403)
            if request.path in {"/account/two_factor/setup/", "/account/two_factor/qrcode/"}:
                if request.session.get("cms_pending_until", 0) <= timezone.now().timestamp() and not request.session.get("cms_verified_at"):
                    return JsonResponse({"code": "UNAUTHENTICATED"}, status=403)
            elif request.path == "/account/two_factor/backup/tokens/":
                from .cms_policy import policy_lock
                from .cms_sessions import current_session
                try:
                    with policy_lock():
                        row = current_session(request.session.get("cms_session_id"), request.user, request.session.session_key, touch=True)
                except CMSFailure as exc:
                    return JsonResponse({"code": str(exc.detail["code"])}, status=exc.status_code)
        elif request.method == "POST":
            username = next((value for key, value in request.POST.items() if key.endswith("-username")), "")
            if username:
                request.session["cms_login_account"] = username[:254]
            username = username or request.session.get("cms_login_account", "")
            try:
                keys = login_attempt(username, request.META.get("REMOTE_ADDR", ""))
            except CMSFailure as exc:
                return JsonResponse({"code": str(exc.detail["code"])}, status=exc.status_code)
            # The maintained view performs password and OTP verification; only completed login resets the limit.
            request.cms_login_keys = keys
        return None
