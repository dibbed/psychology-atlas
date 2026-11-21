"""Offline recovery through trusted host access; no remote recovery adapter is implied."""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django_otp import devices_for_user

from atlas.cms_models import AdminAuditEvent
from atlas.cms_policy import owners, policy_lock
from atlas.cms_sessions import revoke_account


class Command(BaseCommand):
    help = "Revoke an active owner's MFA and all sessions after offline identity verification. Requires trusted host access."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, required=True)
        parser.add_argument("--reason", required=True)
        parser.add_argument("--identity-verified", action="store_true", required=True)

    def handle(self, *args, **options):
        if not options["identity_verified"] or not options["reason"].strip():
            raise CommandError("Offline identity verification and a reason are required.")
        with policy_lock():
            user = owners().filter(pk=options["user_id"]).first()
            if user is None:
                raise CommandError("Target must be an active staff owner.")
            for device in devices_for_user(user, confirmed=None):
                device.delete()
            revoke_account(user)
            # Only the outcome is stored; free text might contain recovery credentials or private data.
            AdminAuditEvent.objects.create(actor=None, actor_type="system", target_id=user.pk, action="mfa.offline_owner_recovery", outcome="success")
        self.stdout.write("Owner MFA and sessions revoked. Existing password is required for enrollment; no credentials are printed.")
