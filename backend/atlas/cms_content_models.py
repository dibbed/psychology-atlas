"""Revision anchors and immutable proposals; canonical domain models remain authoritative."""
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Append-only records cannot be updated.")

    def delete(self):
        raise ValidationError("Append-only records cannot be deleted.")

    def bulk_create(self, *args, **kwargs):
        raise ValidationError("Use the audited service to insert records.")

    def bulk_update(self, *args, **kwargs):
        raise ValidationError("Append-only records cannot be updated.")

    def _update(self, values):
        raise ValidationError("Append-only records cannot be updated.")

    def _raw_delete(self, using):
        raise ValidationError("Append-only records cannot be deleted.")


class ActorErasureQuerySet(AppendOnlyQuerySet):
    def update(self, **kwargs):
        # Django's SET_NULL collector must preserve history when its actor is erased.
        if kwargs == {"actor": None} or kwargs == {"actor_id": None}:
            return models.QuerySet.update(self, **kwargs)
        return super().update(**kwargs)


class AppendOnlyModel(models.Model):
    objects = AppendOnlyQuerySet.as_manager()
    retained = ActorErasureQuerySet.as_manager()

    class Meta:
        abstract = True
        default_permissions = ()
        base_manager_name = "retained"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Append-only records cannot be updated.")
        kwargs["force_insert"] = True
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Append-only records cannot be deleted.")


class ContentState(models.Model):
    class Kind(models.TextChoices):
        CATEGORY = "category", "Category"
        DISORDER = "disorder", "Disorder"
        SYMPTOM = "symptom", "Symptom"
        DISORDER_SYMPTOM = "disorder-symptom", "Disorder Symptom"
        DIFFERENTIAL_RELATIONSHIP = "differential-relationship", "Differential Relationship"
        DISORDER_SOURCE = "disorder-source", "Disorder Source"
        CONCEPT = "concept", "Concept"
        CONCEPT_RELATIONSHIP = "concept-relationship", "Concept Relationship"
        CONCEPT_ALIAS = "concept-alias", "Concept Alias"
        CONCEPT_RELATIONSHIP_SOURCE = "concept-relationship-source", "Concept Relationship Source"
        CONCEPT_SYMPTOM = "concept-symptom", "Concept Symptom"
        CONCEPT_SYMPTOM_SOURCE = "concept-symptom-source", "Concept Symptom Source"
        DISORDER_CONCEPT = "disorder-concept", "Disorder Concept"
        CONCEPT_SOURCE = "concept-source", "Concept Source"
        DSM_CORPUS = "dsm-corpus", "Dsm Corpus"
        DSM_RECORD = "dsm-record", "Dsm Record"
        DSM_RECORD_RELATION = "dsm-record-relation", "Dsm Record Relation"
        THERAPY_FAMILY = "therapy-family", "Therapy Family"
        THERAPY_CLASSIFICATION = "therapy-classification", "Therapy Classification"
        THERAPY = "therapy", "Therapy"
        TECHNIQUE = "technique", "Technique"
        THERAPY_CLASSIFICATION_LINK = "therapy-classification-link", "Therapy Classification Link"
        THERAPY_DISORDER = "therapy-disorder", "Therapy Disorder"
        THERAPY_TECHNIQUE = "therapy-technique", "Therapy Technique"
        THERAPY_CONCEPT = "therapy-concept", "Therapy Concept"
        TECHNIQUE_CONCEPT = "technique-concept", "Technique Concept"
        THERAPY_ALIAS = "therapy-alias", "Therapy Alias"
        TECHNIQUE_ALIAS = "technique-alias", "Technique Alias"
        THERAPY_SOURCE = "therapy-source", "Therapy Source"
        TECHNIQUE_SOURCE = "technique-source", "Technique Source"
        THERAPY_TECHNIQUE_SOURCE = "therapy-technique-source", "Therapy Technique Source"
        THERAPY_DISORDER_SOURCE = "therapy-disorder-source", "Therapy Disorder Source"
        THERAPY_CONCEPT_SOURCE = "therapy-concept-source", "Therapy Concept Source"
        TECHNIQUE_CONCEPT_SOURCE = "technique-concept-source", "Technique Concept Source"
        PSYCHOLOGIST = "psychologist", "Psychologist"
        PSYCHOLOGIST_ALIAS = "psychologist-alias", "Psychologist Alias"
        PSYCHOLOGIST_SOURCE = "psychologist-source", "Psychologist Source"
        PSYCHOLOGIST_THEORY = "psychologist-theory", "Psychologist Theory"
        PSYCHOLOGIST_THEORY_SOURCE = "psychologist-theory-source", "Psychologist Theory Source"
        PSYCHOLOGIST_CONCEPT = "psychologist-concept", "Psychologist Concept"
        PSYCHOLOGIST_CONCEPT_SOURCE = "psychologist-concept-source", "Psychologist Concept Source"
        PSYCHOLOGIST_THERAPY = "psychologist-therapy", "Psychologist Therapy"
        PSYCHOLOGIST_THERAPY_SOURCE = "psychologist-therapy-source", "Psychologist Therapy Source"
        PSYCHOLOGIST_PSYCHOLOGIST = "psychologist-psychologist", "Psychologist Psychologist"
        PSYCHOLOGIST_PSYCHOLOGIST_SOURCE = "psychologist-psychologist-source", "Psychologist Psychologist Source"
        THEORY = "theory", "Theory"
        THEORY_ALIAS = "theory-alias", "Theory Alias"
        THEORY_SOURCE = "theory-source", "Theory Source"
        THEORY_CONCEPT = "theory-concept", "Theory Concept"
        THEORY_CONCEPT_SOURCE = "theory-concept-source", "Theory Concept Source"
        THEORY_THERAPY = "theory-therapy", "Theory Therapy"
        THEORY_THERAPY_SOURCE = "theory-therapy-source", "Theory Therapy Source"
        THEORY_TECHNIQUE = "theory-technique", "Theory Technique"
        THEORY_TECHNIQUE_SOURCE = "theory-technique-source", "Theory Technique Source"
        THEORY_THEORY = "theory-theory", "Theory Theory"
        THEORY_THEORY_SOURCE = "theory-theory-source", "Theory Theory Source"
        TIMELINE_EVENT = "timeline-event", "Timeline Event"
        TIMELINE_EVENT_SOURCE = "timeline-event-source", "Timeline Event Source"
        TIMELINE_PSYCHOLOGIST = "timeline-psychologist", "Timeline Psychologist"
        TIMELINE_PSYCHOLOGIST_SOURCE = "timeline-psychologist-source", "Timeline Psychologist Source"
        TIMELINE_THEORY = "timeline-theory", "Timeline Theory"
        TIMELINE_THEORY_SOURCE = "timeline-theory-source", "Timeline Theory Source"
        TIMELINE_THERAPY = "timeline-therapy", "Timeline Therapy"
        TIMELINE_THERAPY_SOURCE = "timeline-therapy-source", "Timeline Therapy Source"
        TIMELINE_TECHNIQUE = "timeline-technique", "Timeline Technique"
        TIMELINE_TECHNIQUE_SOURCE = "timeline-technique-source", "Timeline Technique Source"
        TIMELINE_CONCEPT = "timeline-concept", "Timeline Concept"
        TIMELINE_CONCEPT_SOURCE = "timeline-concept-source", "Timeline Concept Source"
        BRAIN_ANATOMICAL_ENTITY = "brain-anatomical-entity", "Brain Anatomical Entity"
        BRAIN_NETWORK = "brain-network", "Brain Network"
        BRAIN_ANATOMICAL_ALIAS = "brain-anatomical-alias", "Brain Anatomical Alias"
        BRAIN_NETWORK_ALIAS = "brain-network-alias", "Brain Network Alias"
        BRAIN_ANATOMICAL_ENTITY_SOURCE = "brain-anatomical-entity-source", "Brain Anatomical Entity Source"
        BRAIN_NETWORK_SOURCE = "brain-network-source", "Brain Network Source"
        BRAIN_EXTERNAL_IDENTIFIER = "brain-external-identifier", "Brain External Identifier"
        BRAIN_HIERARCHY_LINK = "brain-hierarchy-link", "Brain Hierarchy Link"
        BRAIN_HIERARCHY_LINK_SOURCE = "brain-hierarchy-link-source", "Brain Hierarchy Link Source"
        BRAIN_NETWORK_MEMBERSHIP = "brain-network-membership", "Brain Network Membership"
        BRAIN_FUNCTIONAL_ASSOCIATION = "brain-functional-association", "Brain Functional Association"
        BRAIN_NETWORK_MEMBERSHIP_SOURCE = "brain-network-membership-source", "Brain Network Membership Source"
        BRAIN_FUNCTIONAL_ASSOCIATION_SOURCE = "brain-functional-association-source", "Brain Functional Association Source"
        ASSESSMENT_INSTRUMENT = "assessment-instrument", "Assessment Instrument"
        ASSESSMENT_VERSION = "assessment-version", "Assessment Version"
        ASSESSMENT_LANGUAGE_FORM = "assessment-language-form", "Assessment Language Form"
        ASSESSMENT_VALIDATION_STUDY = "assessment-validation-study", "Assessment Validation Study"
        ASSESSMENT_PSYCHOMETRIC_EVIDENCE = "assessment-psychometric-evidence", "Assessment Psychometric Evidence"
        ASSESSMENT_ALIAS = "assessment-alias", "Assessment Alias"
        ASSESSMENT_ACCESS = "assessment-access", "Assessment Access"
        ASSESSMENT_RELATION = "assessment-relation", "Assessment Relation"
        ASSESSMENT_SOURCE = "assessment-source", "Assessment Source"

    class Publication(models.TextChoices):
        NEVER = "never_published", "Never published"
        CURRENT = "current", "Current"
        PENDING = "pending_update", "Pending update"
        WITHDRAWN = "withdrawn", "Withdrawn"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=48, choices=Kind.choices)
    canonical_pk = models.PositiveBigIntegerField(null=True)
    version = models.PositiveBigIntegerField(default=0)
    canonical_digest = models.CharField(max_length=64)
    current_revision = models.ForeignKey("ContentRevision", null=True, on_delete=models.PROTECT, related_name="current_for")
    publication = models.CharField(max_length=24, choices=Publication.choices, default=Publication.NEVER)
    legacy_origin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=("kind", "canonical_pk"), name="uq_cms_kind_canonical"),
            models.CheckConstraint(condition=models.Q(kind__in=(
                "category", "disorder", "symptom", "disorder-symptom", "differential-relationship", "disorder-source",
                "concept", "concept-relationship", "concept-alias", "concept-relationship-source", "concept-symptom",
                "concept-symptom-source", "disorder-concept", "concept-source", "dsm-corpus", "dsm-record", "dsm-record-relation",
                "therapy-family", "therapy-classification", "therapy", "technique", "therapy-classification-link", "therapy-disorder", "therapy-technique", "therapy-concept", "technique-concept", "therapy-alias", "technique-alias", "therapy-source", "technique-source", "therapy-technique-source", "therapy-disorder-source", "therapy-concept-source", "technique-concept-source",
                "psychologist", "psychologist-alias", "psychologist-source", "psychologist-theory", "psychologist-theory-source", "psychologist-concept", "psychologist-concept-source", "psychologist-therapy", "psychologist-therapy-source", "psychologist-psychologist", "psychologist-psychologist-source", "theory", "theory-alias", "theory-source", "theory-concept", "theory-concept-source", "theory-therapy", "theory-therapy-source", "theory-technique", "theory-technique-source", "theory-theory", "theory-theory-source", "timeline-event", "timeline-event-source", "timeline-psychologist", "timeline-psychologist-source", "timeline-theory", "timeline-theory-source", "timeline-therapy", "timeline-therapy-source", "timeline-technique", "timeline-technique-source", "timeline-concept", "timeline-concept-source", "brain-anatomical-entity", "brain-network", "brain-anatomical-alias", "brain-network-alias", "brain-anatomical-entity-source", "brain-network-source", "brain-external-identifier", "brain-hierarchy-link", "brain-hierarchy-link-source", "brain-network-membership", "brain-functional-association", "brain-network-membership-source", "brain-functional-association-source", "assessment-instrument", "assessment-version", "assessment-language-form", "assessment-validation-study", "assessment-psychometric-evidence", "assessment-alias", "assessment-access", "assessment-relation", "assessment-source")), name="ck_cms_content_kind"),
        ]


class ContentRevision(AppendOnlyModel):
    class Intent(models.TextChoices):
        EDIT = "edit", "Edit"
        ARCHIVE = "archive", "Archive proposal"

    class Status(models.TextChoices):
        LEGACY = "legacy", "Legacy metadata, no review decision"
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        IN_REVIEW = "in_review", "In review"
        CHANGES_REQUESTED = "changes_requested", "Changes requested"
        APPROVED = "approved", "Approved"
        SUPERSEDED = "superseded", "Superseded"
        DISCARDED = "discarded", "Discarded"

    state = models.ForeignKey(ContentState, on_delete=models.PROTECT, related_name="revisions")
    sequence = models.PositiveBigIntegerField()
    base_version = models.PositiveBigIntegerField()
    base_digest = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    payload_digest = models.CharField(max_length=64)
    dependency_digest = models.CharField(max_length=64)
    schema_version = models.PositiveSmallIntegerField(default=1)
    intent = models.CharField(max_length=16, choices=Intent.choices, default=Intent.EDIT)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="cms_revisions")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
        base_manager_name = "retained"
        ordering = ("state_id", "sequence")
        constraints = [models.UniqueConstraint(fields=("state", "sequence"), name="uq_cms_revision_sequence"),
            models.CheckConstraint(condition=models.Q(intent__in=("edit", "archive")), name="ck_cms_revision_intent")]
