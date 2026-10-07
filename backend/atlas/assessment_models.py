"""Assessment metadata only: family, edition, adaptation, study and finding stay distinct."""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import models, router, transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Lower

from .models import ScientificReviewStatus, SourceReference, TimeStampedModel, lock_brain_curation
from .brain_source_resolution import normalized_text


class AssessmentQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Assessment writes require individual validated saves.")

    def bulk_create(self, *args, **kwargs):
        raise ValidationError("Assessment writes require individual validated saves.")

    def bulk_update(self, *args, **kwargs):
        raise ValidationError("Assessment writes require individual validated saves.")

    def delete(self):
        raise ProtectedError("Assessment history uses deactivation, not deletion.", list(self[:1]))

    def update_or_create(self, *args, **kwargs):
        with transaction.atomic(using=self.db):
            lock_brain_curation(self.db)
            return super().update_or_create(*args, **kwargs)


class AssessmentReviewedBase(TimeStampedModel):
    objects = AssessmentQuerySet.as_manager()
    review_status = models.CharField(max_length=24, choices=ScientificReviewStatus.choices,
                                    default=ScientificReviewStatus.UNREVIEWED, db_index=True)
    is_active = models.BooleanField(default=True)
    seed_managed = models.BooleanField(default=False)
    identity_fields = ()
    parent_fields = ()

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        from .brain_publication import source_is_resolved
        for field in self.parent_fields:
            parent_id = getattr(self, field + "_id")
            parent_model = self._meta.get_field(field).remote_field.model
            parent = parent_model.objects.filter(pk=parent_id).first() if parent_id else None
            if parent is None and (parent_id or not self._meta.get_field(field).null):
                raise ValidationError({field: "An existing exact parent identity is required."})
            setattr(self, field, parent)
            if parent and self.review_status != "unreviewed" and parent.review_status != "reviewed":
                raise ValidationError({field: "Checked content requires a reviewed parent."})
            if parent and self.is_active and not parent.is_active:
                raise ValidationError({field: "Active content requires an active parent."})
        if self.review_status != "unreviewed":
            if hasattr(self, "source_id"):
                self.source = SourceReference.objects.filter(pk=self.source_id).first()
                supported = source_is_resolved(self.source) and bool(self.source_note.strip())
            elif isinstance(self, AssessmentPsychometricEvidence):
                supported = self.study.review_status == "reviewed" and source_is_resolved(self.study.source)
            else:
                supported = self.pk and any(source_is_resolved(link.source) and link.note.strip()
                                           for link in self.source_links.select_related("source"))
            if not supported:
                raise ValidationError({"review_status": "Checked content requires resolved claim-level provenance."})

    def save(self, *args, **kwargs):
        using = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=using):
            # SourceReference uses this same lock; source edits and publication cannot race.
            # ponytail: serialized curator writes; split locks only if registry write throughput requires it.
            lock_brain_curation(using)
            previous = type(self).objects.using(using).select_for_update().filter(pk=self.pk).first() if self.pk else None
            candidate = self
            update_fields = kwargs.get("update_fields")
            if previous is not None and update_fields is not None:
                candidate = type(self).objects.using(using).get(pk=self.pk)
                for name in update_fields:
                    field = self._meta.get_field(name)
                    setattr(candidate, field.attname, getattr(self, field.attname))
            if previous:
                for name in self.identity_fields:
                    if getattr(previous, name) != getattr(candidate, name):
                        raise ValidationError({name: "Published identity keys are immutable."})
                changed = any(getattr(previous, f.attname) != getattr(candidate, f.attname)
                              for f in self._meta.concrete_fields
                              if f.name not in {"id", "created_at", "updated_at", "is_active", "review_status"})
                if changed and previous.review_status == "reviewed" and candidate.review_status != "unreviewed":
                    raise ValidationError("Return reviewed content to unreviewed before changing its claims.")
                if changed:
                    children = {AssessmentInstrument: ("versions", "aliases"),
                                AssessmentVersion: ("language_forms", "validation_studies", "aliases", "access_records", "relations"),
                                AssessmentLanguageForm: ("validation_studies", "access_records", "relations"),
                                AssessmentValidationStudy: ("findings",)}
                    if any(getattr(previous, relation).exclude(review_status="unreviewed").exists()
                           for relation in children.get(type(self), ())):
                        raise ValidationError("Return dependent checked claims to unreviewed before changing their context.")
            for field in candidate._meta.concrete_fields:
                if hasattr(getattr(candidate, field.attname), "resolve_expression"):
                    raise ValidationError("Assessment validation requires concrete values.")
            candidate.full_clean()
            for name in ("normalized_name", "normalized_text"):
                if hasattr(candidate, name):
                    setattr(self, name, getattr(candidate, name))
            return super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        raise ProtectedError("Assessment history uses deactivation, not deletion.", [self])


class AssessmentInstrument(AssessmentReviewedBase):
    slug = models.SlugField(max_length=180, unique=True)
    name_en = models.CharField(max_length=255)
    name_fa = models.CharField(max_length=255, blank=True)
    normalized_name = models.CharField(max_length=255, unique=True, editable=False, blank=True)
    description = models.CharField(max_length=2000, blank=True)
    construct_overview = models.CharField(max_length=1000, blank=True)
    rightsholder = models.CharField(max_length=255, blank=True)
    identity_fields = ("slug",)

    class Meta:
        ordering = ("name_en", "id")
        indexes = [models.Index(fields=("is_active", "review_status", "name_en"))]

    def clean(self):
        self.normalized_name = normalized_text(self.name_en)
        if not self.normalized_name or self.name_en != " ".join(self.name_en.split()):
            raise ValidationError({"name_en": "A canonical name with normalized whitespace is required."})
        if self.slug != self.slug.lower():
            raise ValidationError({"slug": "Stable lowercase identity is required."})
        super().clean()

    def save(self, *args, **kwargs):
        if kwargs.get("update_fields") is not None and "name_en" in kwargs["update_fields"]:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"normalized_name"}
        return super().save(*args, **kwargs)


class AssessmentVersion(AssessmentReviewedBase):
    class Kind(models.TextChoices):
        ORIGINAL = "original", "Original form"
        REVISION = "revision", "Revision"
        SHORT = "short", "Short form"
        UNKNOWN = "unknown", "Edition unresolved"

    class Purpose(models.TextChoices):
        SCREENING = "screening", "Screening"
        RESEARCH = "research", "Research measurement"
        SEVERITY = "severity", "Severity measurement"
        MONITORING = "monitoring", "Monitoring"
        SUPPORT = "diagnostic_support", "Diagnostic support"

    instrument = models.ForeignKey(AssessmentInstrument, on_delete=models.PROTECT, related_name="versions")
    key = models.SlugField(max_length=120)
    label = models.CharField(max_length=255)
    form_kind = models.CharField(max_length=24, choices=Kind.choices, default=Kind.UNKNOWN)
    publication_year = models.PositiveSmallIntegerField(null=True, blank=True)
    derived_from = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="derived_versions")
    construct = models.CharField(max_length=120, blank=True)
    intended_use = models.CharField(max_length=24, choices=Purpose.choices, blank=True)
    administration = models.CharField(max_length=500, blank=True)
    informant = models.CharField(max_length=255, blank=True)
    population = models.CharField(max_length=500, blank=True)
    limitations = models.CharField(max_length=1000, blank=True)
    identity_fields = ("instrument_id", "key")
    parent_fields = ("instrument",)

    class Meta:
        ordering = ("key", "id")
        constraints = [models.UniqueConstraint(Lower("key"), "instrument", name="uq_assessment_version_identity")]

    def clean(self):
        super().clean()
        if self.key != self.key.lower():
            raise ValidationError({"key": "Version keys are lowercase."})
        if self.derived_from_id:
            if self.derived_from.instrument_id != self.instrument_id or self.derived_from_id == self.pk:
                raise ValidationError({"derived_from": "Derivation must be another version of this family."})
            seen = {self.pk}
            current = self.derived_from
            while current:
                if current.pk in seen:
                    raise ValidationError({"derived_from": "Version derivation cannot contain a cycle."})
                seen.add(current.pk)
                current = current.derived_from


class AssessmentLanguageForm(AssessmentReviewedBase):
    class Kind(models.TextChoices):
        ORIGINAL = "original", "Original language form"
        TRANSLATION = "translation", "Translation"
        ADAPTATION = "adaptation", "Adaptation"

    class Authorization(models.TextChoices):
        UNKNOWN = "unknown", "Permission not established"
        AUTHORIZED = "authorized", "Authorization verified for this form"

    version = models.ForeignKey(AssessmentVersion, on_delete=models.PROTECT, related_name="language_forms")
    key = models.SlugField(max_length=120)
    language = models.CharField(max_length=16)
    label = models.CharField(max_length=255)
    form_kind = models.CharField(max_length=24, choices=Kind.choices)
    owner = models.CharField(max_length=255, blank=True)
    authorization_status = models.CharField(max_length=24, choices=Authorization.choices, default=Authorization.UNKNOWN)
    authorization_source = models.ForeignKey("atlas.SourceReference", on_delete=models.PROTECT, null=True, blank=True,
                                            related_name="assessment_authorizations")
    authorization_note = models.CharField(max_length=1000, blank=True)
    identity_fields = ("version_id", "key", "language")
    parent_fields = ("version",)

    class Meta:
        ordering = ("language", "key", "id")
        constraints = [models.UniqueConstraint(fields=("version", "language", "key"), name="uq_assessment_language_identity")]

    def clean(self):
        super().clean()
        import re
        from .brain_publication import source_is_resolved
        if self.authorization_source_id:
            self.authorization_source = SourceReference.objects.get(pk=self.authorization_source_id)
        if not re.fullmatch(r"[a-z]{2,3}(?:-[A-Z]{2})?", self.language):
            raise ValidationError({"language": "An explicit language/locale code is required."})
        if self.key != self.key.lower():
            raise ValidationError({"key": "Form keys are lowercase."})
        if self.authorization_status == "authorized" and (
                not self.authorization_note.strip() or not source_is_resolved(self.authorization_source)):
            raise ValidationError({"authorization_status": "Exact form authorization requires separate rights evidence."})


class AssessmentValidationStudy(AssessmentReviewedBase):
    key = models.SlugField(max_length=180, unique=True)
    version = models.ForeignKey(AssessmentVersion, on_delete=models.PROTECT, related_name="validation_studies")
    language_form = models.ForeignKey(AssessmentLanguageForm, on_delete=models.PROTECT, related_name="validation_studies")
    source = models.ForeignKey("atlas.SourceReference", on_delete=models.PROTECT, related_name="assessment_studies")
    source_note = models.CharField(max_length=1000)
    design = models.CharField(max_length=500)
    population = models.CharField(max_length=500)
    sample_context = models.CharField(max_length=1000)
    sample_size = models.PositiveIntegerField(null=True, blank=True)
    administration = models.CharField(max_length=500)
    informant = models.CharField(max_length=255)
    method = models.CharField(max_length=1000)
    comparator = models.CharField(max_length=500, blank=True)
    limitations = models.CharField(max_length=1000)
    identity_fields = ("key", "version_id", "language_form_id", "source_id")
    parent_fields = ("version", "language_form")

    class Meta:
        ordering = ("key", "id")

    def clean(self):
        super().clean()
        if self.language_form.version_id != self.version_id:
            raise ValidationError({"language_form": "Study form and version must identify the same edition."})
        for name in ("source_note", "design", "population", "sample_context", "administration", "informant", "method", "limitations"):
            if not getattr(self, name).strip():
                raise ValidationError({name: "Explicit study context is required."})
        if self.sample_size == 0:
            raise ValidationError({"sample_size": "A reported sample size must be positive."})


class AssessmentPsychometricEvidence(AssessmentReviewedBase):
    class Property(models.TextChoices):
        RELIABILITY = "reliability", "Reliability"
        VALIDITY = "validity", "Validity"
        RESPONSIVENESS = "responsiveness", "Responsiveness"

    key = models.SlugField(max_length=180, unique=True)
    study = models.ForeignKey(AssessmentValidationStudy, on_delete=models.PROTECT, related_name="findings")
    measurement_property = models.CharField(max_length=24, choices=Property.choices)
    statistic = models.CharField(max_length=120)
    method = models.CharField(max_length=1000)
    value_text = models.CharField(max_length=80, blank=True)
    units = models.CharField(max_length=120, blank=True)
    uncertainty = models.CharField(max_length=500, blank=True)
    finding = models.CharField(max_length=2000)
    limitations = models.CharField(max_length=1000)
    extraction_locator = models.CharField(max_length=500)
    identity_fields = ("key", "study_id")
    parent_fields = ("study",)

    class Meta:
        ordering = ("key", "id")

    def clean(self):
        super().clean()
        for name in ("statistic", "method", "finding", "limitations", "extraction_locator"):
            if not getattr(self, name).strip():
                raise ValidationError({name: "An extracted finding requires method, source locator and limitations."})
        if self.value_text:
            try:
                finite = Decimal(self.value_text).is_finite()
            except InvalidOperation:
                finite = False
            if not finite or self.value_text != self.value_text.strip():
                raise ValidationError({"value_text": "Keep the finite reported number as text with original precision."})
            if self.study.version.form_kind == "unknown":
                raise ValidationError({"value_text": "Numerical publication requires a resolved edition."})


class AssessmentAlias(AssessmentReviewedBase):
    class Kind(models.TextChoices):
        NAME = "name", "Alternative name"
        ACRONYM = "acronym", "Acronym"
        TRANSLATED_TITLE = "translated_title", "Translated display title"

    instrument = models.ForeignKey(AssessmentInstrument, on_delete=models.PROTECT, related_name="aliases")
    version = models.ForeignKey(AssessmentVersion, on_delete=models.PROTECT, null=True, blank=True, related_name="aliases")
    text = models.CharField(max_length=255)
    normalized_text = models.CharField(max_length=255, editable=False, blank=True)
    language = models.CharField(max_length=16)
    alias_type = models.CharField(max_length=24, choices=Kind.choices)
    source = models.ForeignKey("atlas.SourceReference", on_delete=models.PROTECT, related_name="assessment_aliases")
    source_note = models.CharField(max_length=1000)
    parent_fields = ("instrument", "version")

    class Meta:
        ordering = ("language", "text", "id")
        constraints = [
            models.UniqueConstraint(fields=("instrument", "normalized_text", "language"), condition=Q(version__isnull=True), name="uq_assessment_family_alias"),
            models.UniqueConstraint(fields=("version", "normalized_text", "language"), condition=Q(version__isnull=False), name="uq_assessment_version_alias"),
        ]

    def clean(self):
        self.normalized_text = normalized_text(self.text)
        super().clean()
        import re
        if not re.fullmatch(r"[a-z]{2,3}(?:-[A-Z]{2})?", self.language):
            raise ValidationError({"language": "An explicit alias language/locale is required."})
        if not self.normalized_text or not self.source_note.strip():
            raise ValidationError("Aliases require text and sourced identity support.")
        if self.version_id and self.version.instrument_id != self.instrument_id:
            raise ValidationError({"version": "Alias edition must belong to its instrument family."})
        if self.alias_type == "translated_title" and self.version_id:
            raise ValidationError({"version": "A translated display title is family metadata, not a language form."})

    def save(self, *args, **kwargs):
        if kwargs.get("update_fields") is not None and "text" in kwargs["update_fields"]:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"normalized_text"}
        return super().save(*args, **kwargs)


class AssessmentAccess(AssessmentReviewedBase):
    class Availability(models.TextChoices):
        UNKNOWN = "unknown", "Access not established"
        OWNER = "owner_access", "Available through owner"
        PUBLIC = "public_access", "Public access verified"

    class License(models.TextChoices):
        UNKNOWN = "unknown", "Permission not established"
        RESTRICTED = "restricted", "Owner restrictions apply"
        PUBLIC_DOMAIN = "public_domain", "Owner states public domain for this scope"
        PERMISSION = "explicit_permission", "Explicit permission for this scope"

    key = models.SlugField(max_length=180, unique=True)
    version = models.ForeignKey(AssessmentVersion, on_delete=models.PROTECT, related_name="access_records")
    language_form = models.ForeignKey(AssessmentLanguageForm, on_delete=models.PROTECT, null=True, blank=True, related_name="access_records")
    material_type = models.CharField(max_length=24, choices=[("questionnaire", "Questionnaire"), ("manual", "Manual"), ("translation", "Translation"), ("metadata", "Metadata")])
    use = models.CharField(max_length=24, choices=[("owner_access", "Owner access"), ("redistribution", "Redistribution"), ("metadata_listing", "Metadata listing")])
    jurisdiction = models.CharField(max_length=255, default="Not established")
    owner = models.CharField(max_length=255, blank=True)
    availability = models.CharField(max_length=24, choices=Availability.choices, default=Availability.UNKNOWN)
    license_status = models.CharField(max_length=24, choices=License.choices, default=License.UNKNOWN)
    terms = models.CharField(max_length=2000)
    source = models.ForeignKey("atlas.SourceReference", on_delete=models.PROTECT, related_name="assessment_access")
    source_note = models.CharField(max_length=1000)
    verified_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    identity_fields = ("key", "version_id", "language_form_id", "material_type", "use")
    parent_fields = ("version", "language_form")

    class Meta:
        ordering = ("key", "id")

    def clean(self):
        super().clean()
        if self.language_form_id and self.language_form.version_id != self.version_id:
            raise ValidationError({"language_form": "Rights scope must identify the same version."})
        if not self.terms.strip() or not self.source_note.strip():
            raise ValidationError("Access records must describe the exact verified scope and uncertainty.")
        if (self.license_status != "unknown" or self.availability != "unknown") and not self.verified_on:
            raise ValidationError({"verified_on": "Rights/access facts require a verification date."})
        if self.expires_on and (not self.verified_on or self.expires_on < self.verified_on):
            raise ValidationError({"expires_on": "Expiry cannot precede verification."})
        if self.language_form_id and self.language_form.form_kind != "original" and self.license_status in {"public_domain", "explicit_permission"}:
            if self.language_form.authorization_status != "authorized":
                raise ValidationError({"license_status": "Translated content requires separate exact-form authorization."})


class AssessmentRelation(AssessmentReviewedBase):
    class Predicate(models.TextChoices):
        MEASURES = "measures", "Measures a construct"
        RESEARCH = "research_measure_of", "Research measure of a construct"
        SCREENS = "screens_for", "Screens for"
        MONITORS = "monitors", "Monitors severity/change"
        SUPPORT = "diagnostic_support_for", "One input in professional assessment"

    key = models.SlugField(max_length=180, unique=True)
    version = models.ForeignKey(AssessmentVersion, on_delete=models.PROTECT, related_name="relations")
    language_form = models.ForeignKey(AssessmentLanguageForm, on_delete=models.PROTECT, null=True, blank=True, related_name="relations")
    predicate = models.CharField(max_length=32, choices=Predicate.choices)
    concept = models.ForeignKey("atlas.Concept", on_delete=models.PROTECT, null=True, blank=True, related_name="assessment_relations")
    symptom = models.ForeignKey("atlas.Symptom", on_delete=models.PROTECT, null=True, blank=True, related_name="assessment_relations")
    disorder = models.ForeignKey("atlas.Disorder", on_delete=models.PROTECT, null=True, blank=True, related_name="assessment_relations")
    claim = models.CharField(max_length=1000)
    context = models.CharField(max_length=1000)
    limitations = models.CharField(max_length=1000)
    identity_fields = ("key", "version_id", "language_form_id", "predicate", "concept_id", "symptom_id", "disorder_id")
    parent_fields = ("version", "language_form")

    class Meta:
        ordering = ("key", "id")
        constraints = [models.CheckConstraint(condition=(Q(concept__isnull=False, symptom__isnull=True, disorder__isnull=True)
            | Q(concept__isnull=True, symptom__isnull=False, disorder__isnull=True)
            | Q(concept__isnull=True, symptom__isnull=True, disorder__isnull=False)), name="ck_assessment_relation_endpoint")]

    def clean(self):
        super().clean()
        present = [name for name in ("concept", "symptom", "disorder") if getattr(self, name + "_id")]
        allowed = {"measures": {"concept"}, "research_measure_of": {"concept"}, "screens_for": {"symptom", "disorder"},
                   "monitors": {"concept", "symptom", "disorder"}, "diagnostic_support_for": {"disorder"}}
        if len(present) != 1 or present[0] not in allowed.get(self.predicate, set()):
            raise ValidationError("The predicate requires exactly one supported endpoint type; diagnosis is not a predicate.")
        if self.is_active and not getattr(getattr(self, present[0]), "is_active", True):
            raise ValidationError("An active relation requires an active endpoint.")
        if self.language_form_id and self.language_form.version_id != self.version_id:
            raise ValidationError({"language_form": "Relation form must belong to its exact version."})
        if not all(getattr(self, name).strip() for name in ("claim", "context", "limitations")):
            raise ValidationError("Relations require an explicit claim, context and interpretation limitations.")


class AssessmentSource(models.Model):
    """Exactly one Assessment owner; studies/findings retain their explicit study citation."""
    objects = AssessmentQuerySet.as_manager()
    instrument = models.ForeignKey(AssessmentInstrument, on_delete=models.PROTECT, null=True, blank=True, related_name="source_links")
    version = models.ForeignKey(AssessmentVersion, on_delete=models.PROTECT, null=True, blank=True, related_name="source_links")
    language_form = models.ForeignKey(AssessmentLanguageForm, on_delete=models.PROTECT, null=True, blank=True, related_name="source_links")
    relation = models.ForeignKey(AssessmentRelation, on_delete=models.PROTECT, null=True, blank=True, related_name="source_links")
    source = models.ForeignKey("atlas.SourceReference", on_delete=models.PROTECT, related_name="assessment_claims")
    note = models.CharField(max_length=1000)

    class Meta:
        constraints = [models.CheckConstraint(condition=(
            Q(instrument__isnull=False, version__isnull=True, language_form__isnull=True, relation__isnull=True)
            | Q(instrument__isnull=True, version__isnull=False, language_form__isnull=True, relation__isnull=True)
            | Q(instrument__isnull=True, version__isnull=True, language_form__isnull=False, relation__isnull=True)
            | Q(instrument__isnull=True, version__isnull=True, language_form__isnull=True, relation__isnull=False)), name="ck_assessment_source_owner"),
            *[models.UniqueConstraint(fields=(owner, "source"), condition=Q(**{owner + "__isnull": False}),
                                      name="uq_assessment_source_" + owner) for owner in ("instrument", "version", "language_form", "relation")]]

    def clean(self):
        super().clean()
        owners = []
        for name in ("instrument", "version", "language_form", "relation"):
            if getattr(self, name + "_id"):
                owner = self._meta.get_field(name).remote_field.model.objects.get(pk=getattr(self, name + "_id"))
                setattr(self, name, owner)
                owners.append(owner)
        if len(owners) != 1 or not self.note.strip():
            raise ValidationError("Exactly one owner and an explicit supported claim are required.")
        previous = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        changed = not previous or any(getattr(previous, f.attname) != getattr(self, f.attname) for f in self._meta.concrete_fields if not f.primary_key)
        previous_owners = [getattr(previous, name) for name in ("instrument", "version", "language_form", "relation")
                           if previous and getattr(previous, name + "_id")]
        if changed and any(owner.review_status != "unreviewed" for owner in owners + previous_owners):
            raise ValidationError("Return all owners to unreviewed before changing their evidence.")

    def save(self, *args, **kwargs):
        using = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=using):
            lock_brain_curation(using)
            if kwargs.get("update_fields") is not None:
                raise ValidationError("Evidence links require complete validated saves.")
            self.full_clean()
            return super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        raise ProtectedError("Assessment provenance is retained; deactivate its owner.", [self])


def protect_assessment_source(source_id, using):
    """Called by the shared SourceReference mutation boundary under its existing lock."""
    owners = [(AssessmentAlias, "source_id"), (AssessmentAccess, "source_id"),
              (AssessmentValidationStudy, "source_id"), (AssessmentLanguageForm, "authorization_source_id")]
    if any(model.objects.using(using).filter(**{field: source_id}).exclude(review_status="unreviewed").exists()
           for model, field in owners):
        raise ValidationError("Return checked Assessment claims to unreviewed before changing their source.")
    if AssessmentPsychometricEvidence.objects.using(using).filter(study__source_id=source_id).exclude(review_status="unreviewed").exists():
        raise ValidationError("Return checked Assessment findings to unreviewed before changing their study source.")
    links = AssessmentSource.objects.using(using).filter(source_id=source_id)
    if any(links.filter(**{owner + "__review_status__in": ("source_checked", "reviewed")}).exists()
           for owner in ("instrument", "version", "language_form", "relation")):
        raise ValidationError("Return checked Assessment claims to unreviewed before changing their source.")
