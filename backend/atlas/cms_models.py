"""Security lifecycle only; existing Django users, groups and permissions remain authoritative."""
import uuid

from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError

from .cms_capabilities import KNOWN_PERMISSIONS
from .cms_content_models import AppendOnlyModel


class RolePolicy(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    version = models.PositiveBigIntegerField(default=0)

    class Meta:
        default_permissions = ()
        permissions = tuple((c, c.replace("_", " ")) for c in sorted(KNOWN_PERMISSIONS))


class AccountSecurityState(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    security_version = models.PositiveBigIntegerField(default=0)
    revoked_before = models.DateTimeField(null=True)

    class Meta:
        default_permissions = ()


class AdminSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    django_session = models.OneToOneField("sessions.Session", null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField()
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True)
    mfa_at = models.DateTimeField()
    security_version = models.PositiveBigIntegerField(default=0)
    step_up = models.JSONField(default=dict)

    class Meta:
        default_permissions = ()


class AdminLoginThrottle(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    window_start = models.DateTimeField()
    failures = models.PositiveIntegerField(default=0)

    class Meta:
        default_permissions = ()


class AdminAuditEvent(AppendOnlyModel):
    """P01 events retained in the same table's P02 append-only successor."""
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="cms_security_events")
    target_id = models.PositiveBigIntegerField(null=True)
    action = models.CharField(max_length=48)
    outcome = models.CharField(max_length=16)
    created_at = models.DateTimeField(auto_now_add=True)
    actor_ref = models.CharField(max_length=64, blank=True)
    actor_type = models.CharField(max_length=16, default="user")
    target_kind = models.CharField(max_length=48, blank=True)
    target_key = models.CharField(max_length=64, blank=True)
    base_revision = models.PositiveBigIntegerField(null=True)
    new_revision = models.PositiveBigIntegerField(null=True)
    diff = models.JSONField(default=list)
    reason = models.CharField(max_length=32, blank=True)
    request_id = models.UUIDField(default=uuid.uuid4)
    policy_version = models.PositiveBigIntegerField(null=True)
    error_code = models.CharField(max_length=48, blank=True)

    class Meta:
        default_permissions = ()
        base_manager_name = "retained"
        ordering = ("-id",)
        constraints = [models.CheckConstraint(condition=models.Q(outcome__in=("success", "denied", "failed")), name="ck_cms_audit_outcome")]

    def save(self, *args, **kwargs):
        from .cms_audit import ACTIONS, REASONS, SAFE_FIELDS, TARGET_KINDS, attribution
        if (self.action not in ACTIONS or self.outcome not in {"success", "denied", "failed"}
                or self.reason not in REASONS or not isinstance(self.diff, list)
                or any(type(k) is not str or k not in SAFE_FIELDS for k in self.diff)
                or self.actor_type not in {"user", "system", "anonymous"}
                or self.target_kind not in TARGET_KINDS
                or (self.target_key and not all(c in "0123456789abcdef-" for c in self.target_key))
                or (self.error_code and (not self.error_code.isascii() or not self.error_code.replace("_", "").isalnum() or self.error_code != self.error_code.upper()))):
            raise ValidationError("Invalid audit metadata.")
        self.actor_ref = attribution(self.actor_id)
        if self.actor_id is None and self.actor_type == "user":
            self.actor_type = "anonymous"
        return super().save(*args, **kwargs)
