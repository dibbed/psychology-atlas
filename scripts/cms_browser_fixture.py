"""Synthetic-only disposable CMS journey fixture. Never run against a persistent DB."""
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
database = Path(os.environ["SQLITE_PATH"]).resolve()
assert database.is_relative_to(Path(tempfile.gettempdir()).resolve()) and database.name == "cms-journey.sqlite3"
phase = os.environ.get("CMS_QA_PHASE")
artifact_command = sys.argv[1:] if len(sys.argv) > 1 else []
if artifact_command and (phase != "p06" or len(artifact_command) != 3
        or artifact_command[:2] not in (["--p06-artifact", "age"], ["--p06-artifact", "state"])):
    raise RuntimeError("Only explicit P06 artifact age/state commands are supported")
guarded_prefix = {"p05": "atlas-p05-browser-", "p06": "atlas-p06-browser-", "p07": "atlas-p07-browser-", "p08": "atlas-p08-browser-", "p09": "atlas-p09-browser-", "p10": "atlas-p10-browser-", "p11": "atlas-p11-browser-", "p12": "atlas-p12-browser-", "p13": "atlas-p13-browser-", "p14": "atlas-p14-browser-"}.get(phase)
if guarded_prefix and (
        not database.is_relative_to(Path(tempfile.gettempdir()).resolve())
        or database.name != "cms-journey.sqlite3"
        or not database.parent.name.startswith(guarded_prefix)
        or (database.exists() and not artifact_command)):
    raise RuntimeError(f"{phase.upper()} fixture requires a new harness-created temporary database")
if phase in {"p06", "p13"} and Path(os.environ["CMS_ARTIFACT_ROOT"]).resolve() != database.parent / "private":
    raise RuntimeError("Private storage must belong to the disposable harness directory")
if phase == "p06":
    if (database.parent.parent != Path(tempfile.gettempdir()).resolve()
            or not re.fullmatch(r"atlas-p06-browser-[A-Za-z0-9]+", database.parent.name)):
        raise RuntimeError("P06 requires its exact direct TEMP directory prefix")
    token = os.environ.get("CMS_QA_OWNER_TOKEN", "")
    marker = database.parent / ".p06-owner"
    if not re.fullmatch(r"[0-9a-f]{64}", token):
        raise RuntimeError("P06 requires the harness ownership token")
    if artifact_command:
        if not database.is_file() or marker.is_symlink() or marker.read_text() != token:
            raise RuntimeError("P06 artifact commands require this harness's owned existing fixture")
    else:
        with marker.open("x") as stream:
            stream.write(token)
sys.path.insert(0, str(root / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

if guarded_prefix:
    from django.conf import settings
    configured = settings.DATABASES["default"]
    if (configured["ENGINE"] != "django.db.backends.sqlite3"
            or Path(configured["NAME"]).resolve() != database
            or not database.parent.name.startswith(guarded_prefix)):
        raise RuntimeError(f"{phase.upper()} fixture requires the harness's disposable SQLite database")
    if phase in {"p06", "p13", "p14"} and settings.CMS_ARTIFACT_ROOT.resolve() != database.parent / "private":
        raise RuntimeError("Configured private storage escaped the disposable harness directory")

if artifact_command:
    import hashlib
    import stat
    from datetime import timedelta
    from django.utils import timezone
    from atlas.cms_job_models import AdminArtifact, AdminJob

    artifact = AdminArtifact.objects.select_related("owner").get(pk=artifact_command[2])
    if (not artifact.filename.startswith("P06-NON-SCIENTIFIC")
            or artifact.owner is None or artifact.owner.username not in ("qa_owner", "qa_p06_intake")
            or artifact.storage_key != artifact.pk.hex + ".json"):
        raise RuntimeError("Refuse artifact outside the explicitly synthetic P06 fixture")
    private = database.parent / "private"
    if private.is_symlink() or private.resolve() != private:
        raise RuntimeError("Refuse substituted private storage")
    owned_file = private / artifact.storage_key
    exists = owned_file.exists()
    if exists:
        info = owned_file.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or bool(getattr(info, "st_file_attributes", 0) & 0x400)):
            raise RuntimeError("Refuse linked or nonregular synthetic bytes")
        byte_hash = hashlib.sha256(owned_file.read_bytes()).hexdigest()
        if byte_hash != artifact.sha256 or info.st_size != artifact.size:
            raise RuntimeError("Synthetic artifact bytes failed integrity verification")
    else:
        byte_hash = None
    receipt = {}
    job = AdminJob.objects.filter(kind="artifact_cleanup", artifact=artifact).order_by("-created_at").first()
    if job:
        directory = private.stat()
        receipt = {"complete": job.checkpoint.get("complete") is True,
            "directory_identity_matches": job.checkpoint.get("directory_identity") == {"dev": directory.st_dev, "ino": directory.st_ino},
            "file_identity": job.checkpoint.get("file_identity"), "job_status": job.status,
            "error_code": job.error_code}
    native_calls = {}
    native_source_sha256 = None
    coverage = database.parent / "native-cleanup.cover"
    if coverage.exists():
        import inspect
        import pickle
        from atlas.cms_artifacts import _WindowsCleanup
        info_coverage = coverage.lstat()
        if (not stat.S_ISREG(info_coverage.st_mode) or info_coverage.st_nlink != 1
                or info_coverage.st_size > 64 * 1024 * 1024
                or bool(getattr(info_coverage, "st_file_attributes", 0) & 0x400)):
            raise RuntimeError("Refuse unowned native-worker trace")
        # Only this run's stdlib trace output, inside its token-guarded TEMP root.
        with coverage.open("rb") as stream:
            counts, _, _ = pickle.load(stream)
        source, first_line = inspect.getsourcelines(_WindowsCleanup)
        source_file = Path(inspect.getsourcefile(_WindowsCleanup)).resolve()
        native_source_sha256 = hashlib.sha256(source_file.read_bytes()).hexdigest()
        for name in ("CreateFileW", "GetFileInformationByHandle", "ReadFile", "SetFileInformationByHandle", "CloseHandle"):
            lines = {first_line + offset for offset, line in enumerate(source) if f"self.api.{name}(" in line}
            native_calls[name] = sum(count for (file, line), count in counts.items()
                if line in lines and Path(file).resolve() == source_file)
    if artifact_command[1] == "age":
        if not exists or artifact.purged_at is not None:
            raise RuntimeError("Only an intact synthetic artifact can be aged")
        now = timezone.now()
        AdminArtifact.objects.filter(pk=artifact.pk).update(
            created_at=now - timedelta(days=8), expires_at=now - timedelta(days=1))
        artifact.refresh_from_db()
    print(json.dumps({"id": str(artifact.pk), "state": artifact.state, "version": artifact.version,
        "purged_at": artifact.purged_at.isoformat() if artifact.purged_at else None,
        "age_days": (timezone.now() - artifact.created_at).days,
        "expired": artifact.expires_at <= timezone.now(), "bytes_exist": exists,
        "bytes_sha256": byte_hash, "sha256": artifact.sha256, "size": artifact.size,
        "file_identity": {"dev": info.st_dev, "ino": info.st_ino} if exists else None,
        "cleanup_receipt": receipt, "native_calls": native_calls, "native_source_sha256": native_source_sha256}))
    sys.exit(0)

from django.contrib.auth.models import Permission, User
from django.core.management import call_command
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice
from atlas.cms_content import canonical_snapshot, dependencies, digest, editable_snapshot
from atlas.cms_content_models import ContentRevision, ContentState
from atlas.models import Category

call_command("migrate", verbosity=0)
assert not User.objects.exists(), "Fixture requires an empty disposable database"
password = secrets.token_urlsafe(24)
users = {}
for name, caps in (("owner", ["cms_owner"]), ("reader", ["cms_enter", "cms_catalog", "cms_dashboard", "cms_core_view"]), ("scoped", ["cms_enter", "cms_catalog", "cms_brain_view"])):
    user = User.objects.create_user("qa_" + name, password=password, is_staff=True)
    user.user_permissions.add(*Permission.objects.filter(content_type__app_label="atlas", content_type__model="rolepolicy", codename__in=caps))
    TOTPDevice.objects.create(user=user, name="default", confirmed=True)
    backup = StaticDevice.objects.create(user=user, name="backup", confirmed=True)
    tokens = [StaticToken.objects.create(device=backup, token=StaticToken.random_token()).token for _ in range(8)]
    users[name] = {"username": user.username, "password": password, "tokens": tokens}

category = Category.objects.create(slug="cms-journey-category", name_en="P06 NON-SCIENTIFIC .invalid isolated category" if phase == "p06" else "CMS journey category", name_fa="دسته‌بندی آزمون CMS", description="دادهٔ آزمون؛ محتوای علمی نیست.")
state = ContentState.objects.create(kind="category", canonical_pk=category.pk, legacy_origin=True, canonical_digest=digest(canonical_snapshot("category", category)), publication="current")
snapshot = editable_snapshot("category", category)
revision = ContentRevision.objects.create(state=state, sequence=0, base_version=0, base_digest=state.canonical_digest, payload=snapshot, payload_digest=digest(snapshot), dependency_digest=dependencies("category", category), status="legacy")
state.current_revision = revision
state.save(update_fields=["current_revision"])
review_fixture = {}
if os.environ.get("CMS_QA_PHASE") == "p04":
    from atlas.models import Disorder, SourceReference
    user = User.objects.create_user("qa_reviewer", password=password, is_staff=True)
    user.user_permissions.add(*Permission.objects.filter(content_type__app_label="atlas", content_type__model="rolepolicy",
        codename__in=["cms_enter", "cms_catalog", "cms_core_view", "cms_review_decide_core_source", "cms_review_decide_core_scientific"]))
    TOTPDevice.objects.create(user=user, name="default", confirmed=True)
    backup = StaticDevice.objects.create(user=user, name="backup", confirmed=True)
    users["reviewer"] = {"id": user.pk, "username": user.username, "password": password,
        "tokens": [StaticToken.objects.create(device=backup, token=StaticToken.random_token()).token for _ in range(8)]}
    source = SourceReference.objects.create(title="CMS synthetic review source", citation="Synthetic source; not scientific evidence.",
        url="https://example.org/cms-qa", verification_status="source_checked")
    # A real active child exercises Category's actual public list gate.
    disorder = Disorder.objects.create(category=category, slug="cms-qa-disorder", name_en="CMS synthetic disorder", overview="Synthetic original")
    disorder_state = ContentState.objects.create(kind="disorder", canonical_pk=disorder.pk, legacy_origin=True,
        canonical_digest=digest(canonical_snapshot("disorder", disorder)), publication="current")
    snapshot = editable_snapshot("disorder", disorder)
    revision = ContentRevision.objects.create(state=disorder_state, sequence=0, base_version=0, base_digest=disorder_state.canonical_digest,
        payload=snapshot, payload_digest=digest(snapshot), dependency_digest=dependencies("disorder", disorder), status="legacy")
    disorder_state.current_revision = revision
    disorder_state.save(update_fields=["current_revision"])
    review_fixture = {"source": source.pk, "disorder": str(disorder_state.pk), "owner_id": users.get("owner", {}).get("id") or User.objects.get(username="qa_owner").pk}
if os.environ.get("CMS_QA_PHASE") == "p05":
    from atlas.models import Disorder, DisorderSource, SourceReference
    from atlas.assessment_models import AssessmentAccess, AssessmentInstrument, AssessmentLanguageForm, AssessmentSource, AssessmentVersion
    from atlas.cms_governance import resource_binding
    from django.utils import timezone

    reviewer = User.objects.create_user("qa_p05_reviewer", password=password, is_staff=True)
    reviewer_caps = ["cms_enter", "cms_catalog", "cms_core_view", "cms_assessment_view", "cms_source_view",
        "cms_rights_decide", "cms_terminology_decide", "cms_review_decide_core_rights",
        "cms_review_decide_core_terminology", "cms_review_decide_assessment_rights",
        "cms_review_decide_assessment_terminology"]
    reviewer.user_permissions.add(*Permission.objects.filter(content_type__app_label="atlas",
        content_type__model="rolepolicy", codename__in=reviewer_caps))
    TOTPDevice.objects.create(user=reviewer, name="default", confirmed=True)
    backup = StaticDevice.objects.create(user=reviewer, name="backup", confirmed=True)
    users["reviewer"] = {"id": reviewer.pk, "username": reviewer.username, "password": password,
        "tokens": [StaticToken.objects.create(device=backup, token=StaticToken.random_token()).token for _ in range(8)]}
    sources = {}
    for key in ("mutable", "terminology", "assessment"):
        sources[key] = SourceReference.objects.create(title=f"P05 SYNTHETIC NON-SCIENTIFIC {key} source",
            organization="SYNTHETIC QA ORGANIZATION — NOT A RIGHTSHOLDER",
            citation="SYNTHETIC browser fixture; not scientific evidence or permission.",
            url=f"https://p05-qa.invalid/{key}", verification_status="source_checked",
            metadata={"synthetic_qa": True, "not_scientific_evidence": True,
                      "private_fixture_marker": "P05_PRIVATE_HISTORY_SENTINEL"})
    sources["mutable"].doi = "10.5555/p05-synthetic-not-evidence"
    sources["mutable"].save()
    sources["duplicate"] = SourceReference.objects.create(
        title="P05 SYNTHETIC NON-SCIENTIFIC duplicate source", organization=sources["mutable"].organization,
        citation=sources["mutable"].citation, url=sources["mutable"].url,
        verification_status="source_checked")
    disorder = Disorder.objects.create(category=category, slug="cms-p05-synthetic-disorder",
        name_en="P05 SYNTHETIC NON-SCIENTIFIC disorder", name_fa="اختلال مصنوعی آزمون؛ علمی نیست",
        overview="SYNTHETIC QA ONLY. No scientific or diagnostic claim.")
    DisorderSource.objects.create(disorder=disorder, source=sources["mutable"], note="Synthetic dependency, no scientific evidence.")

    # Reviewed flags exercise existing public gates inside this disposable test DB only.
    instrument = AssessmentInstrument.objects.create(slug="p05-synthetic-assessment",
        name_en="P05 SYNTHETIC NON-SCIENTIFIC assessment", name_fa="ابزار مصنوعی آزمون؛ علمی نیست",
        description="SYNTHETIC QA ONLY. Not a questionnaire, scientific claim or permission.",
        rightsholder="SYNTHETIC QA ONLY — NO REAL RIGHTSHOLDER")
    AssessmentSource.objects.create(instrument=instrument, source=sources["assessment"], note="Synthetic identity fixture, not scientific evidence.")
    instrument.review_status = "reviewed"
    instrument.save()
    version = AssessmentVersion.objects.create(instrument=instrument, key="p05-synthetic-version",
        label="SYNTHETIC version; no items or scoring", limitations="SYNTHETIC QA ONLY")
    AssessmentSource.objects.create(version=version, source=sources["assessment"], note="Synthetic edition fixture, not scientific evidence.")
    version.review_status = "reviewed"
    version.save()
    language_form = AssessmentLanguageForm.objects.create(version=version, key="p05-synthetic-fa", language="fa",
        label="فرم فارسی مصنوعی آزمون؛ فاقد مجوز ترجمه", form_kind="translation", authorization_status="unknown")
    access = AssessmentAccess.objects.create(key="p05-synthetic-access", version=version,
        material_type="metadata", use="metadata_listing", terms="SYNTHETIC QA ONLY. Permission unknown.",
        source=sources["assessment"], source_note="Synthetic provenance, no legal permission.")
    review_fixture = {"owner_id": User.objects.get(username="qa_owner").pk, "today": timezone.localdate().isoformat(),
        "sources": {key: source.pk for key, source in sources.items()}, "disorder_pk": disorder.pk,
        "core_binding": resource_binding("disorder", disorder.pk),
        "assessment_binding": resource_binding("assessment_instrument", instrument.pk),
        "assessment_version": version.pk, "assessment_access": access.pk, "assessment_language_form": language_form.pk,
        "assessment_baseline": {"instrument": instrument.review_status, "version": version.review_status,
            "access": access.review_status, "availability": access.availability, "license_status": access.license_status,
            "language_form": language_form.review_status, "form_authorization": language_form.authorization_status,
            "name_en": instrument.name_en, "name_fa": instrument.name_fa}}

if phase == "p06":
    # Both actors have real intake permissions; ownership still separates their data.
    caps = ["cms_enter", "cms_catalog", "cms_dashboard", "cms_research_view", "cms_research_intake",
        "cms_research_map", "cms_research_derive", "cms_research_reject", "cms_research_defer",
        "cms_artifact_upload", "cms_artifact_download"]
    for name in ("intake", "foreign"):
        user = User.objects.create_user("qa_p06_" + name, password=password, is_staff=True)
        user_caps = caps + (["cms_research_raw_read"] if name == "foreign" else [])
        permissions = Permission.objects.filter(content_type__app_label="atlas",
            content_type__model="rolepolicy", codename__in=user_caps)
        assert permissions.count() == len(user_caps), "P06 capabilities are not integrated"
        user.user_permissions.add(*permissions)
        TOTPDevice.objects.create(user=user, name="default", confirmed=True)
        backup = StaticDevice.objects.create(user=user, name="backup", confirmed=True)
        users[name] = {"id": user.pk, "username": user.username, "password": password,
            "tokens": [StaticToken.objects.create(device=backup, token=StaticToken.random_token()).token for _ in range(8)]}
if phase == "p09":
    # Synthetic historical attribution only; not a scientific source or authorship claim.
    from atlas.models import (Psychologist, Theory, TimelineEvent, SourceReference,
        PsychologistSource, PsychologistTheory, PsychologistTheorySource, TimelineEventSource)
    source = SourceReference.objects.create(title="P09 NON-SCIENTIFIC archive",
        citation="NON-SCIENTIFIC browser fixture. No validated historical or legal source.",
        url="https://p09.invalid/non-science", verification_status="source_checked")
    person = Psychologist.objects.create(slug="p09-browser-person",
        name_en="P09 NON-SCIENTIFIC person", birth_year=1901, death_year=1991)
    other_person = Psychologist.objects.create(slug="p09-browser-other-person",
        name_en="P09 NON-SCIENTIFIC other person")
    theory = Theory.objects.create(slug="p09-browser-theory",
        name_en="P09 NON-SCIENTIFIC theory")
    event = TimelineEvent.objects.create(slug="p09-browser-event",
        title_en="P09 NON-SCIENTIFIC event", date_precision="year", year_start=1950)
    unknown = TimelineEvent.objects.create(slug="p09-browser-undated",
        title_en="P09 NON-SCIENTIFIC undated event", date_precision="unknown")
    TimelineEventSource.objects.create(event=event, source=source)
    PsychologistSource.objects.create(psychologist=person, source=source)
    attribution = PsychologistTheory.objects.create(psychologist=person, theory=theory,
        relationship_type="associated_with")
    PsychologistTheorySource.objects.create(relationship=attribution, source=source)
    anchors = {}
    for kind, obj in (("psychologist",person), ("psychologist",other_person),
            ("theory",theory), ("timeline-event",event), ("timeline-event",unknown),
            ("psychologist-theory",attribution)):
        state = ContentState.objects.create(kind=kind, canonical_pk=obj.pk, legacy_origin=True,
            canonical_digest=digest(canonical_snapshot(kind,obj)), publication="current")
        snapshot = editable_snapshot(kind,obj)
        rev = ContentRevision.objects.create(state=state, sequence=0, base_version=0,
            base_digest=state.canonical_digest, payload=snapshot,
            payload_digest=digest(snapshot), dependency_digest=dependencies(kind,obj), status="legacy")
        state.current_revision = rev
        state.save(update_fields=["current_revision"])
        anchors[f"{kind}:{obj.pk}"] = str(state.pk)
    review_fixture = {"p09": {"source":source.pk, "person":person.pk,
        "other_person":other_person.pk, "theory":theory.pk, "event":event.pk,
        "unknown":unknown.pk, "person_state":anchors[f"psychologist:{person.pk}"]}}

if phase == "p08":
    # P08 browser-only records are synthetic; no efficacy or rights assertion.
    from atlas.models import (TherapyFamily, TherapyClassification, Therapy,
        Technique, TherapyTechnique, TherapySource, TechniqueSource, SourceReference, Concept)
    source = SourceReference.objects.create(title="P08 NON-SCIENTIFIC source .invalid",
        citation="NON-SCIENTIFIC SYNTHETIC fixture; not a scientific or legal source.",
        url="https://p08.invalid/synthetic", verification_status="source_checked")
    family = TherapyFamily.objects.create(slug="p08-test-family",
        name_en="P08 NON-SCIENTIFIC family")
    classification = TherapyClassification.objects.create(slug="p08-test-classification",
        name_en="P08 NON-SCIENTIFIC classification")
    treatment = Therapy.objects.create(family=family, slug="p08-test-therapy",
        name_en="P08 NON-SCIENTIFIC therapy", summary="Synthetic browser fixture, not clinical advice.",
        review_status="reviewed")
    other = Therapy.objects.create(family=family, slug="p08-test-other",
        name_en="P08 NON-SCIENTIFIC other", summary="Synthetic browser fixture, not clinical advice.",
        review_status="reviewed")
    technique = Technique.objects.create(slug="p08-test-technique",
        name_en="P08 NON-SCIENTIFIC legacy technique", review_status="reviewed")
    therapy_link = TherapyTechnique.objects.create(therapy=treatment, technique=technique)
    TherapySource.objects.create(therapy=treatment, source=source)
    TechniqueSource.objects.create(technique=technique, source=source)
    anchors = {}
    for kind, obj in (("therapy-family", family), ("therapy-classification", classification),
            ("therapy", treatment), ("therapy", other), ("technique", technique),
            ("therapy-technique", therapy_link)):
        anchor = ContentState.objects.create(kind=kind, canonical_pk=obj.pk, legacy_origin=True,
            canonical_digest=digest(canonical_snapshot(kind,obj)), publication="current")
        snapshot = editable_snapshot(kind,obj)
        revision = ContentRevision.objects.create(state=anchor, sequence=0, base_version=0,
            base_digest=anchor.canonical_digest, payload=snapshot,
            payload_digest=digest(snapshot), dependency_digest=dependencies(kind,obj), status="legacy")
        anchor.current_revision=revision
        anchor.save(update_fields=["current_revision"])
        anchors[f"{kind}:{obj.pk}"]=str(anchor.pk)
    review_fixture={"p08":{"source":source.pk,"therapy":treatment.pk,"other":other.pk,
        "technique":technique.pk,"link":therapy_link.pk,"therapy_anchor":anchors[f"therapy:{treatment.pk}"]}}

if phase == "p10":
    # Disposable NON-SCIENTIFIC Brain fixture, never a real source claim.
    from atlas.models import (BrainAnatomicalEntity, BrainAnatomicalEntitySource,
        BrainHierarchyLink, BrainHierarchyLinkSource, SourceReference)
    source = SourceReference.objects.create(title="P10 NON-SCIENTIFIC fixture",
        citation="P10 synthetic data. Not scientific evidence or publication permission.",
        url="https://p10.invalid/fixture", verification_status="source_checked")
    root_node = BrainAnatomicalEntity.objects.create(slug="p10-browser-root",
        name_en="P10 NON-SCIENTIFIC root", kind="whole_brain", laterality="bilateral")
    left_node = BrainAnatomicalEntity.objects.create(slug="p10-browser-left",
        name_en="P10 NON-SCIENTIFIC left", kind="cortical_region", laterality="left")
    right_node = BrainAnatomicalEntity.objects.create(slug="p10-browser-right",
        name_en="P10 NON-SCIENTIFIC right", kind="cortical_region", laterality="right")
    link = BrainHierarchyLink.objects.create(child=left_node, parent=root_node,
        source_version="P10 SYNTHETIC claim version")
    BrainAnatomicalEntitySource.objects.create(entity=root_node, source=source,
        note="Synthetic non-scientific note")
    BrainHierarchyLinkSource.objects.create(relationship=link, source=source,
        note="Synthetic non-scientific hierarchy attribution")
    states = {}
    for kind, canonical in (("brain-anatomical-entity", root_node),
                            ("brain-anatomical-entity", left_node),
                            ("brain-anatomical-entity", right_node),
                            ("brain-hierarchy-link", link)):
        anchor = ContentState.objects.create(kind=kind, canonical_pk=canonical.pk,
            legacy_origin=True, canonical_digest=digest(canonical_snapshot(kind, canonical)),
            publication="never_published")
        candidate = editable_snapshot(kind, canonical)
        revision = ContentRevision.objects.create(state=anchor, sequence=0, base_version=0,
            base_digest=anchor.canonical_digest, payload=candidate,
            payload_digest=digest(candidate), dependency_digest=dependencies(kind, canonical),
            status="legacy")
        anchor.current_revision = revision
        anchor.save(update_fields=["current_revision"])
        states[f"{kind}:{canonical.pk}"] = str(anchor.pk)
    review_fixture = {"p10": {"source": source.pk, "root": root_node.pk,
        "left": left_node.pk, "right": right_node.pk, "link": link.pk,
        "left_state": states[f"brain-anatomical-entity:{left_node.pk}"],
        "link_state": states[f"brain-hierarchy-link:{link.pk}"]}}

if phase == "p11":
    # Strictly disposable synthetic metadata. Never a psychometric study, real
    # license, published form, copyable questionnaire or scored assessment.
    from atlas.models import (AssessmentInstrument, AssessmentVersion,
        AssessmentLanguageForm, AssessmentValidationStudy, AssessmentPsychometricEvidence,
        AssessmentAlias, AssessmentAccess, AssessmentRelation, AssessmentSource,
        Concept, SourceReference)
    source = SourceReference.objects.create(
        title="P11 NON-SCIENTIFIC fixture source", citation="SYNTHETIC metadata only; no real rights or scientific claims.",
        url="https://p11.invalid/fixture", verification_status="source_checked")
    family = AssessmentInstrument.objects.create(
        slug="p11-browser-instrument", name_en="P11 NON-SCIENTIFIC instrument",
        name_fa="ابزار مصنوعی آزمون P11", description="NON-SCIENTIFIC private metadata only")
    version = AssessmentVersion.objects.create(
        instrument=family, key="p11-unresolved-version", label="P11 synthetic unknown edition",
        form_kind="unknown", population="SYNTHETIC only",
        limitations="Never use clinically; not a real instrument")
    form = AssessmentLanguageForm.objects.create(
        version=version, key="p11-fake-fa", language="fa", label="P11 NON-SCIENTIFIC form",
        form_kind="translation", authorization_status="unknown")
    study = AssessmentValidationStudy.objects.create(
        key="p11-not-a-study", version=version, language_form=form, source=source,
        source_note="SYNTHETIC location, no real paper", design="NOT A REAL STUDY",
        population="SYNTHETIC ONLY", sample_context="NO REAL SAMPLE", sample_size=1,
        administration="NO ADMINISTRATION", informant="NO RESPONDENT",
        method="NONE; FIXTURE", limitations="Synthetic fixture; not evidence")
    finding = AssessmentPsychometricEvidence.objects.create(
        key="p11-not-a-finding", study=study, measurement_property="reliability",
        statistic="UNREPORTED", method="NONE", finding="SYNTHETIC ONLY - NOT EVIDENCE",
        limitations="No estimation, no clinical meaning", extraction_locator="N/A fixture")
    alias = AssessmentAlias.objects.create(
        instrument=family, text="P11FAKE", language="en", alias_type="acronym",
        source=source, source_note="SYNTHETIC identity, not an actual alias")
    access = AssessmentAccess.objects.create(
        key="p11-unknown-rights", version=version, language_form=form,
        material_type="metadata", use="metadata_listing", terms="SYNTHETIC ONLY; NO GRANTED LICENSE",
        source=source, source_note="Fixture; neither legal permission nor scientific proof")
    concept = Concept.objects.create(
        slug="p11-fake-concept", name_en="P11 NON-SCIENTIFIC concept",
        simple_definition="SYNTHETIC, not a clinical definition")
    relation = AssessmentRelation.objects.create(
        key="p11-fake-relation", version=version, language_form=form, predicate="measures",
        concept=concept, claim="NO REAL MEASUREMENT CLAIM",
        context="Synthetic only", limitations="No clinical interpretation")
    sources = [
        AssessmentSource.objects.create(instrument=family,source=source,note="Synthetic family identity"),
        AssessmentSource.objects.create(version=version,source=source,note="Synthetic edition identity"),
        AssessmentSource.objects.create(language_form=form,source=source,note="Synthetic form identity"),
        AssessmentSource.objects.create(relation=relation,source=source,note="Synthetic relation claim"),
    ]
    records = [
        ("assessment-instrument", family), ("assessment-version", version),
        ("assessment-language-form", form), ("assessment-validation-study", study),
        ("assessment-psychometric-evidence", finding), ("assessment-alias", alias),
        ("assessment-access", access), ("assessment-relation", relation),
        *[("assessment-source", entry) for entry in sources],
    ]
    anchors = {}
    for kind, canonical in records:
        anchor = ContentState.objects.create(kind=kind, canonical_pk=canonical.pk,
            legacy_origin=True, canonical_digest=digest(canonical_snapshot(kind, canonical)),
            publication="never_published")
        snapshot = editable_snapshot(kind, canonical)
        revision = ContentRevision.objects.create(state=anchor, sequence=0, base_version=0,
            base_digest=anchor.canonical_digest, payload=snapshot,
            payload_digest=digest(snapshot), dependency_digest=dependencies(kind, canonical),
            status="legacy")
        anchor.current_revision = revision
        anchor.save(update_fields=["current_revision"])
        anchors[f"{kind}:{canonical.pk}"] = str(anchor.pk)
    viewer = User.objects.create_user("qa_p11_viewer", password=password, is_staff=True)
    viewer.user_permissions.add(*Permission.objects.filter(content_type__app_label="atlas",
        content_type__model="rolepolicy", codename__in=["cms_enter","cms_catalog","cms_assessment_view"]))
    TOTPDevice.objects.create(user=viewer,name="default",confirmed=True)
    backup = StaticDevice.objects.create(user=viewer,name="backup",confirmed=True)
    users["assessment_reader"] = {"username":viewer.username, "password":password,
        "tokens":[StaticToken.objects.create(device=backup,token=StaticToken.random_token()).token for _ in range(8)]}
    review_fixture = {"p11":{"source":source.pk, "family":family.pk, "version":version.pk,
        "form":form.pk, "study":study.pk, "finding":finding.pk, "access":access.pk,
        "family_state":anchors[f"assessment-instrument:{family.pk}"],
        "version_state":anchors[f"assessment-version:{version.pk}"],
        "form_state":anchors[f"assessment-language-form:{form.pk}"],
        "access_state":anchors[f"assessment-access:{access.pk}"]}}

if phase == "p07":
    # Synthetic-only reference and DSM rows for actual P07 browser navigation.
    from atlas.models import Concept, DSMCorpus, DSMRecord, SourceReference
    source = SourceReference.objects.create(title="P07 NON-SCIENTIFIC browser source",
        citation="P07 fixture ONLY; neither scientific nor legal evidence",
        url="https://p07.invalid/test", verification_status="source_checked")
    concept = Concept.objects.create(slug="p07-non-scientific-concept",
        name_en="P07 NON-SCIENTIFIC concept", simple_definition="NON-SCIENTIFIC fixture definition")
    corpus = DSMCorpus.objects.create(key="p07-non-scientific-left",
        title="P07 NON-SCIENTIFIC corpus left", source_filename="fixture.invalid.json",
        source_sha256="a" * 64, source_registry={"TEST": {"title": "NON-SCIENTIFIC"}})
    second = DSMCorpus.objects.create(key="p07-non-scientific-right",
        title="P07 NON-SCIENTIFIC corpus right", source_filename="fixture2.invalid.json",
        source_sha256="b" * 64)
    record = DSMRecord.objects.create(corpus=corpus, master_id="P07-ROOT",
        name_en="P07 NON-SCIENTIFIC parent", summary="NON-SCIENTIFIC sample only",
        source_keys=["TEST"], source_payload={"fixture": "PRIVATE-NON-SCIENTIFIC"})
    child = DSMRecord.objects.create(corpus=corpus, master_id="P07-CHILD",
        name_en="P07 NON-SCIENTIFIC child", parent=record)
    DSMRecord.objects.create(corpus=second, master_id="P07-ROOT",
        name_en="P07 NON-SCIENTIFIC changed")
    p07_anchors = {}
    for kind, canonical in (("concept", concept), ("dsm-corpus", corpus), ("dsm-corpus", second), ("dsm-record", record)):
        anchor = ContentState.objects.create(kind=kind, canonical_pk=canonical.pk, legacy_origin=True,
            canonical_digest=digest(canonical_snapshot(kind, canonical)), publication="never_published")
        snapshot = editable_snapshot(kind, canonical)
        revision = ContentRevision.objects.create(state=anchor, sequence=0, base_version=0,
            base_digest=anchor.canonical_digest, payload=snapshot,
            payload_digest=digest(snapshot), dependency_digest=dependencies(kind, canonical), status="legacy")
        anchor.current_revision = revision
        anchor.save(update_fields=["current_revision"])
        p07_anchors[f"{kind}:{canonical.pk}"] = str(anchor.pk)
    review_fixture = {"p07": {"source": source.pk, "concept": p07_anchors[f"concept:{concept.pk}"],
        "corpus": corpus.pk, "other_corpus": second.pk, "record": record.pk,
        "dsm_anchor": p07_anchors[f"dsm-record:{record.pk}"]}}

if phase == "p12":
    # Disposable, entirely fictional branching content. No real patient data or
    # reviewer sign-off, and no production publication or external side effects.
    from atlas.models import (ClinicalCase, CaseRevision, CaseStep, CaseTransition, SourceReference,
                              CaseScoringDimension, CaseQuestion, CaseChoice, Quiz, QuizQuestion, QuizChoice, Flashcard)
    case = ClinicalCase.objects.create(
        slug="p12-fake-browser-case", title="P12 synthetic published fixture",
        patient_summary="Fictional narrative, not a patient",
        educational_objective="Synthetic branching UI test",
        structure_mode=ClinicalCase.StructureMode.BRANCHING, is_active=True,
    )
    revision = CaseRevision.objects.create(
        case=case, version=1, status=CaseRevision.Status.PUBLISHED,
        title="Synthetic v1", patient_summary="Fictional narrative only", rubric_version=1,
    )
    start = CaseStep.objects.create(
        case=case, revision=revision, stable_key="start",
        node_kind=CaseStep.NodeKind.INFORMATION,
        title="Fictional start", narrative="Synthetic start", sort_order=0,
    )
    end = CaseStep.objects.create(
        case=case, revision=revision, stable_key="end",
        node_kind=CaseStep.NodeKind.TERMINAL,
        title="Fictional finish", narrative="Synthetic finish", sort_order=2,
    )
    decision = CaseStep.objects.create(case=case, revision=revision, stable_key="decision",
        node_kind=CaseStep.NodeKind.DECISION, title="Fictional decision", narrative="Synthetic decision", sort_order=1)
    dimension = CaseScoringDimension.objects.create(revision=revision, stable_key="reasoning", label="Synthetic reasoning")
    question = CaseQuestion.objects.create(step=decision, scoring_dimension=dimension, prompt="Fictional question?")
    choice = CaseChoice.objects.create(question=question, text="Synthetic scored choice", score_value=3)
    CaseTransition.objects.create(
        revision=revision, source_step=start, target_step=decision,
        outcome=CaseTransition.Outcome.CONTINUE,
    )
    CaseTransition.objects.create(revision=revision, source_step=decision, choice=choice,
        target_step=end, outcome=CaseTransition.Outcome.CONTINUE)
    revision.entry_step = start
    revision.save(update_fields=["entry_step"])
    case.current_revision = revision
    case.save(update_fields=["current_revision"])
    from atlas.services import start_or_resume_case_attempt, advance_case_attempt, submit_quiz
    from atlas.learning import review_flashcard
    from atlas.cms_review_models import ReviewPolicy
    ReviewPolicy.objects.update_or_create(pk=1, defaults={"mode": "two_person", "version": 1})
    attempt, _ = start_or_resume_case_attempt(user=User.objects.get(username="qa_owner"), clinical_case=case)
    attempt, _, _ = advance_case_attempt(user=attempt.user, attempt=attempt, step_id=start.pk,
                                        choice_id=None, state_version=0)
    advance_case_attempt(user=attempt.user, attempt=attempt, step_id=decision.pk,
                         choice_id=choice.pk, state_version=1)
    quiz = Quiz.objects.create(slug="p12-synthetic-history-quiz", title="Synthetic history quiz")
    quiz_question = QuizQuestion.objects.create(quiz=quiz, prompt="Synthetic quiz question?")
    quiz_choice = QuizChoice.objects.create(question=quiz_question, text="Synthetic correct answer", is_correct=True)
    submit_quiz(user=attempt.user, quiz=quiz, answers=[{"question_id": quiz_question.pk, "choice_id": quiz_choice.pk}])
    card = Flashcard.objects.create(slug="p12-synthetic-history-card", front="Synthetic front", back="Synthetic back")
    review_flashcard(user=attempt.user, flashcard=card, rating="good")
    for name, caps in (
        ("case_reviewer", ["cms_review_decide_cases_source", "cms_review_decide_cases_rights", "cms_rights_decide"]),
        ("case_approver", ["cms_review_decide_cases_scientific", "cms_publication_approve_cases", "cms_publication_verify_cases"]),
    ):
        user = User.objects.create_user("qa_p12_" + name, password=password, is_staff=True)
        user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="atlas", content_type__model="rolepolicy",
            codename__in=["cms_enter", "cms_catalog", "cms_cases_view", "cms_cases_preview", "cms_cases_validate", *caps],
        ))
        TOTPDevice.objects.create(user=user, name="default", confirmed=True)
        backup = StaticDevice.objects.create(user=user, name="backup", confirmed=True)
        users[name] = {"username": user.username, "password": password,
            "tokens": [StaticToken.objects.create(device=backup, token=StaticToken.random_token()).token
                       for _ in range(8)]}
    viewer = User.objects.create_user("qa_p12_case_reader", password=password, is_staff=True)
    viewer.user_permissions.add(*Permission.objects.filter(
        content_type__app_label="atlas", content_type__model="rolepolicy",
        codename__in=["cms_enter", "cms_cases_view", "cms_cases_preview"],
    ))
    TOTPDevice.objects.create(user=viewer, name="default", confirmed=True)
    backup = StaticDevice.objects.create(user=viewer, name="backup", confirmed=True)
    users["case_reader"] = {
        "username": viewer.username, "password": password,
        "tokens": [StaticToken.objects.create(device=backup, token=StaticToken.random_token()).token
                   for _ in range(8)],
    }
    source = SourceReference.objects.create(title="P16 synthetic source for isolated QA",
        citation="Fictional test citation, not real scientific evidence.",
        doi="10.1234/synthetic.p16", verification_status="source_checked")
    review_fixture = {"p12": {"case": case.pk, "slug": case.slug, "revision": revision.pk,
                               "first": start.pk, "end": end.pk, "source": source.pk, "attempt": attempt.pk}}

if phase == "p13":
    from atlas.models import (Quiz, QuizQuestion, QuizChoice, Concept, Disorder, Flashcard,
        DailyChallenge, DailyChallengeChoice, CognitiveDistortionPracticeItem, CognitiveDistortionPracticeChoice)
    from atlas.services import submit_quiz
    from atlas.learning import review_flashcard
    viewer = User.objects.create_user("qa_p13_learning_reader", password=password, is_staff=True)
    viewer.user_permissions.add(*Permission.objects.filter(content_type__app_label="atlas",
        content_type__model="rolepolicy", codename__in=["cms_enter", "cms_learning_view"]))
    TOTPDevice.objects.create(user=viewer, name="default", confirmed=True)
    backup = StaticDevice.objects.create(user=viewer, name="backup", confirmed=True)
    users["learning_reader"] = {"username": viewer.username, "password": password,
        "tokens": [StaticToken.objects.create(device=backup, token=StaticToken.random_token()).token for _ in range(2)]}
    exporter = User.objects.create_user("qa_p13_learning_exporter", password=password, is_staff=True)
    exporter.user_permissions.add(*Permission.objects.filter(content_type__app_label="atlas",
        content_type__model="rolepolicy", codename__in=["cms_enter", "cms_learning_view", "cms_learning_export", "cms_artifact_download"]))
    TOTPDevice.objects.create(user=exporter, name="default", confirmed=True)
    backup = StaticDevice.objects.create(user=exporter, name="backup", confirmed=True)
    users["learning_exporter"] = {"username": exporter.username, "password": password,
        "tokens": [StaticToken.objects.create(device=backup, token=StaticToken.random_token()).token for _ in range(2)]}
    concept = Concept.objects.create(slug="p13-synthetic-concept", name_en="Synthetic fixture concept")
    disorder = Disorder.objects.create(category=category, slug="p13-synthetic-disorder", name_en="Synthetic fixture disorder")
    quiz = Quiz.objects.create(slug="p13-historical-fixture", title="Synthetic historical quiz", disorder=disorder)
    question = QuizQuestion.objects.create(quiz=quiz, prompt="Synthetic historical question")
    choice = QuizChoice.objects.create(question=question, text="Historical correct answer", is_correct=True)
    QuizChoice.objects.create(question=question, text="Historical distractor", is_correct=False)
    submit_quiz(user=User.objects.get(username="qa_owner"), quiz=quiz,
                answers=[{"question_id": question.pk, "choice_id": choice.pk}])
    card = Flashcard.objects.create(slug="p13-historical-card", front="Synthetic historical front", back="Synthetic historical back",
        concept=concept, disorder=disorder)
    review_flashcard(user=User.objects.get(username="qa_owner"), flashcard=card, rating="good")
    public_card = Flashcard.objects.create(slug="p13-public-archive-card", front="Synthetic public archive front",
        back="Synthetic public archive back")
    daily = DailyChallenge.objects.create(prompt="Synthetic archive daily question", explanation="Fictional only",
        concept=concept, disorder=disorder)
    daily_choice = DailyChallengeChoice.objects.create(challenge=daily, text="Synthetic correct", is_correct=True)
    DailyChallengeChoice.objects.create(challenge=daily, text="Synthetic distractor", is_correct=False)
    distortion = Concept.objects.create(slug="p13-synthetic-distortion", name_en="Synthetic fixture distortion",
        subtype=Concept.Subtype.COGNITIVE_DISTORTION)
    other_distortion = Concept.objects.create(slug="p13-synthetic-other-distortion", name_en="Synthetic other distortion",
        subtype=Concept.Subtype.COGNITIVE_DISTORTION)
    practice = CognitiveDistortionPracticeItem.objects.create(slug="p13-archive-practice",
        prompt="Synthetic archive practice question", explanation="Fictional only", target_concept=distortion)
    practice_choice = CognitiveDistortionPracticeChoice.objects.create(item=practice, concept=distortion,
        text="Synthetic correct distortion", is_correct=True)
    CognitiveDistortionPracticeChoice.objects.create(item=practice, concept=other_distortion,
        text="Synthetic other distortion", is_correct=False)
    # Real learner endpoints create only fictional fixture history in the guarded TEMP DB.
    from rest_framework.test import APIClient
    learner = APIClient()
    login_response = learner.post("/api/auth/login/", {"username": "qa_owner", "password": password},
        format="json", HTTP_HOST="127.0.0.1")
    assert login_response.status_code == 200
    learner.credentials(HTTP_AUTHORIZATION="Bearer " + login_response.json()["access"])
    daily_response = learner.post("/api/daily-challenge/", {"choice_id": daily_choice.pk}, format="json", HTTP_HOST="127.0.0.1")
    assert daily_response.status_code == 200, "Synthetic daily history fixture failed"
    practice_response = learner.post("/api/cognitive-distortions/practice/p13-archive-practice/submit/",
        {"choice_id": practice_choice.pk}, format="json", HTTP_HOST="127.0.0.1")
    assert practice_response.status_code == 201, "Synthetic practice history fixture failed"
    fresh_learner = User.objects.create_user("qa_p13_fresh_learner", password=password)
    users["learning_fresh"] = {"username": fresh_learner.username, "password": password}
    review_fixture = {"p13": {"historical_quiz": quiz.pk, "historical_card": card.pk,
        "public_card": public_card.pk, "daily": daily.pk, "practice": practice.pk,
        "concept": concept.pk, "disorder": disorder.pk, "quiz_question": question.pk,
        "quiz_choice": choice.pk, "daily_choice": daily_choice.pk, "practice_choice": practice_choice.pk}}

if phase == "p14":
    from django.contrib.auth.models import Group
    from atlas.models import Disorder, UserNote
    permission = Permission.objects.get(content_type__app_label="atlas", content_type__model="rolepolicy", codename="cms_learning_view")
    for index in range(25):
        group = Group.objects.create(name=f"P14 pagination fixture {index:02}")
        group.permissions.add(permission)
    subject = User.objects.create_user("qa_p14_private_subject", password=password)
    private_disorder = Disorder.objects.create(category=category, slug="p14-private-fixture", name_en="Synthetic private fixture")
    UserNote.objects.create(user=subject, disorder=private_disorder, body="P14-SYNTHETIC-PRIVATE-NOTE <b>literal text</b>")
    UserNote.objects.create(user=User.objects.get(username="qa_scoped"), disorder=private_disorder, body="P14-OTHER-SUBJECT-NOTE")
    operator = User.objects.create_user("qa_p14_privacy_operator", password=password, is_staff=True)
    operator.user_permissions.add(*Permission.objects.filter(content_type__app_label="atlas", content_type__model="rolepolicy",
        codename__in=("cms_enter", "cms_user_view", "cms_privacy_sensitive_read")))
    TOTPDevice.objects.create(user=operator, name="default", confirmed=True)
    backup = StaticDevice.objects.create(user=operator, name="backup", confirmed=True)
    users["privacy_operator"] = {"username": operator.username, "password": password,
        "tokens": [StaticToken.objects.create(device=backup, token=StaticToken.random_token()).token for _ in range(8)]}
    review_fixture["p14"] = {"subject_id": subject.pk, "subject_username": subject.username, "operator_id": operator.pk}
    exporter = User.objects.create_user("qa_p14_privacy_exporter", password=password, is_staff=True)
    exporter.user_permissions.add(*Permission.objects.filter(content_type__app_label="atlas", content_type__model="rolepolicy",
        codename__in=("cms_enter", "cms_user_view", "cms_privacy_export", "cms_artifact_download")))
    TOTPDevice.objects.create(user=exporter, name="default", confirmed=True)
    backup = StaticDevice.objects.create(user=exporter, name="backup", confirmed=True)
    users["privacy_exporter"] = {"username": exporter.username, "password": password,
        "tokens": [StaticToken.objects.create(device=backup, token=StaticToken.random_token()).token for _ in range(4)]}
    from atlas.models import (Concept, Quiz, Flashcard, DailyChallenge, CognitiveDistortionPracticeItem)
    from atlas.services import submit_quiz
    from atlas.learning import review_flashcard
    from rest_framework.test import APIClient
    concept = Concept.objects.create(slug="p14-private-concept", name_en="Synthetic", subtype="cognitive_distortion")
    other = Concept.objects.create(slug="p14-private-other", name_en="Synthetic other", subtype="cognitive_distortion")
    quiz = Quiz.objects.create(slug="p14-private-quiz", title="Synthetic", disorder=private_disorder)
    question = quiz.questions.create(prompt="Synthetic canonical question never exported")
    choice = question.choices.create(text="Synthetic answer key never exported", is_correct=True)
    question.choices.create(text="Synthetic distractor", is_correct=False)
    submit_quiz(user=subject, quiz=quiz, answers=[{"question_id":question.pk,"choice_id":choice.pk}])
    card = Flashcard.objects.create(slug="p14-private-card", front="Synthetic", back="Synthetic", concept=concept, disorder=private_disorder)
    review_flashcard(user=subject, flashcard=card, rating="good")
    daily = DailyChallenge.objects.create(prompt="Synthetic")
    choice = daily.choices.create(text="Synthetic", is_correct=True)
    daily.choices.create(text="Synthetic other", is_correct=False)
    practice = CognitiveDistortionPracticeItem.objects.create(slug="p14-private-practice", prompt="Synthetic", target_concept=concept)
    answer = practice.choices.create(concept=concept, text="Synthetic", is_correct=True)
    practice.choices.create(concept=other, text="Synthetic other", is_correct=False)
    learner = APIClient()
    learner.force_authenticate(subject)
    assert learner.post("/api/daily-challenge/", {"choice_id":choice.pk}, format="json", HTTP_HOST="127.0.0.1").status_code == 200
    assert learner.post("/api/cognitive-distortions/practice/p14-private-practice/submit/", {"choice_id":answer.pk}, format="json", HTTP_HOST="127.0.0.1").status_code == 201
    from atlas.models import StudyPlanScope, StudyBlock
    from django.utils import timezone
    from atlas.study_planning import create_study_plan, transition_study_plan
    from atlas.study_sessions import start_session
    import uuid
    study_operator = User.objects.create_user("qa_p15_study_operator", password=password, is_staff=True)
    study_operator.user_permissions.add(*Permission.objects.filter(content_type__app_label="atlas", content_type__model="rolepolicy",
        codename__in=("cms_enter", "cms_user_view", "cms_study_view", "cms_study_correct", "cms_privacy_sensitive_read")))
    TOTPDevice.objects.create(user=study_operator, name="default", confirmed=True)
    backup = StaticDevice.objects.create(user=study_operator, name="backup", confirmed=True)
    users["study_operator"] = {"username": study_operator.username, "password": password,
        "tokens": [StaticToken.objects.create(device=backup, token=StaticToken.random_token()).token for _ in range(20)]}
    plan = create_study_plan(subject, {"name": "P15 synthetic support plan"})
    scope = StudyPlanScope.objects.create(plan=plan, disorder=private_disorder)
    transition_study_plan(subject, plan.pk, "activate")
    block = StudyBlock.objects.create(plan=plan, scope=scope, block_kind=StudyBlock.Kind.DISORDER_REVIEW,
        scheduled_date=timezone.localdate(), estimated_minutes=10, disorder=private_disorder,
        snapshot_title="P15 synthetic block", locked_by_user=True)
    session_block = StudyBlock.objects.create(plan=plan, scope=scope, block_kind=StudyBlock.Kind.DISORDER_REVIEW,
        scheduled_date=timezone.localdate(), estimated_minutes=10, disorder=private_disorder, snapshot_title="P15 synthetic session block")
    session, _ = start_session(subject, session_block.pk, uuid.uuid4())
    review_fixture["p15"] = {"plan_id": plan.pk, "block_id": block.pk, "session_id": session.pk}

    # P16 Brain/Assessment preflight uses real immutable editorial proposals.
    # These fixtures have no source/rights approval and must never be published.
    from atlas.cms_content import digest as editorial_digest
    from atlas.cms_content_models import ContentRevision, ContentState
    from atlas.models import AssessmentInstrument, BrainAnatomicalEntity, SourceReference
    dependency_source = SourceReference.objects.create(title="P16 synthetic dependency evidence",
        citation="P16 synthetic citation for disposable tests", doi="10.1234/fake.p16.browser",
        verification_status="source_checked")
    dependency_brain = BrainAnatomicalEntity.objects.create(slug="p16-private-parent",
        name_en="Synthetic private parent", kind="region", laterality="not_established", is_active=False)
    dependency_instrument = AssessmentInstrument.objects.create(slug="p16-private-parent",
        name_en="Synthetic private instrument", is_active=False)
    review_fixture["p16_source_id"] = dependency_source.pk
    review_fixture["p16"] = {}
    for domain, kind, parent_field, parent in (
            ("brain", "brain-anatomical-alias", "entity", dependency_brain),
            ("assessment", "assessment-alias", "instrument", dependency_instrument)):
        payload = {parent_field: parent.pk, "source": dependency_source.pk,
            "text": "P16 PRIVATE SYNTHETIC SECRET " + domain, "language": "en", "alias_type": "alternative"}
        initial = editorial_digest({})
        proposal_state = ContentState.objects.create(
            kind=kind, canonical_digest=initial, publication=ContentState.Publication.NEVER,
        )
        rev = ContentRevision.objects.create(
            state=proposal_state, sequence=1, base_version=0, base_digest=initial,
            payload=payload, payload_digest=editorial_digest(payload),
            dependency_digest=initial, status=ContentRevision.Status.DRAFT,
            actor=User.objects.get(username="qa_owner"), schema_version=2,
        )
        proposal_state.current_revision = rev
        proposal_state.version = 1
        proposal_state.save(update_fields=("current_revision", "version"))
        review_fixture["p16"][domain] = str(proposal_state.pk)

    # P17 internal search: deliberately private staging keys, never public.
    from atlas.models import ResearchDataset, ResearchRecord
    from atlas.cms_models import AdminAuditEvent
    dataset = ResearchDataset.objects.create(
        key="p17-browser-dataset", source_filename="PRIVATE P17 original.json",
        source_sha256="9" * 64, is_active=False,
        raw_text="P17 SECRET STUDY RAW PATIENT",
        raw_document={"private": "P17 SECRET STUDY RAW PATIENT"},
    )
    research_record = ResearchRecord.objects.create(
        dataset=dataset, section="concepts", external_id="P17 SECRET external",
        slug="p17-browser-record", canonical_key="concept:p17-browser-record",
        name_en="P17 SECRET candidate", payload={"question": "P17 SECRET ANSWER"},
    )
    audit = AdminAuditEvent.objects.create(
        actor=User.objects.get(username="qa_owner"), action="session.login",
        outcome="success", target_kind="", target_key="", reason="",
    )
    while audit.pk < 10:
        audit = AdminAuditEvent.objects.create(
            actor=User.objects.get(username="qa_owner"), action="session.login",
            outcome="success", target_kind="", target_key="", reason="",
        )
    review_fixture["p17"] = {"dataset_id": dataset.pk,
                              "record_id": research_record.pk, "audit_id": audit.pk}

# Credentials go only to the harness's private pipe, never into reports or logs.
print(json.dumps({"users": users, "category": str(state.pk), **review_fixture}))
