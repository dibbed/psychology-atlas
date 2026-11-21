"""A bounded, aggregate DB observation that the CMS worker completed a poll.

Not a process-manager heartbeat or proof of worker availability: an exited
worker can leave a recently written record until the freshness window ends.
"""
from datetime import timedelta

from django.db import models, transaction
from django.db.models import F
from django.utils import timezone


class CmsWorkerPulse(models.Model):
    # Deliberate single row: counts successful polls from all processes without
    # persisting hostnames, PIDs, tokens, queue payloads or individual identities.
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    last_successful_poll_at = models.DateTimeField()
    successful_polls = models.PositiveBigIntegerField(default=0)

    class Meta:
        default_permissions = ()
        constraints = [
            models.CheckConstraint(condition=models.Q(pk=1), name="ck_cms_worker_pulse_single"),
        ]


def record_successful_poll():
    """Only invoke after run_once() returned without raising."""
    with transaction.atomic():
        CmsWorkerPulse.objects.get_or_create(
            pk=1, defaults={"last_successful_poll_at": timezone.now()},
        )
        CmsWorkerPulse.objects.filter(pk=1).update(
            last_successful_poll_at=timezone.now(),
            successful_polls=F("successful_polls") + 1,
        )


def observation(now):
    # Presence/recency of a durable poll is not proof that the process is alive.
    window = 180
    row = CmsWorkerPulse.objects.filter(pk=1).values(
        "last_successful_poll_at", "successful_polls").first()
    when = row["last_successful_poll_at"] if row else None
    elapsed = (now - when).total_seconds() if when else None
    return {
        "last_successful_poll_at": when.isoformat() if when else None,
        "successful_polls_recorded": row["successful_polls"] if row else 0,
        "fresh_window_seconds": window,
        "poll_recently_observed": bool(elapsed is not None and 0 <= elapsed <= window),
        "alive_confirmed": False,
        "notice": "PERSISTED_SUCCESSFUL_POLL_RECENCY_NOT_A_LIVENESS_PROOF",
    }
