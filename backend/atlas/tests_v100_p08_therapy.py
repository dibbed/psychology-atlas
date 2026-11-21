"""P08 synthetic regression: typed therapy/technique drafts never publish."""
import uuid
from unittest.mock import patch

from django.test import TestCase, override_settings

from . import cms_content as content
from .cms_audit import SAFE_FIELDS, TARGET_KINDS
from .cms_content_models import ContentRevision, ContentState
from .cms_domains import DOMAIN_SPECS, SOURCE_LINKS, dependency_snapshot, schema_data
from .cms_policy import CMSFailure
from .cms_review_models import ReviewPolicy
from .cms_therapy_domains import FIELDS
from .models import (Category, Concept, Disorder, SourceReference, Technique, TechniqueAlias, TechniqueConcept,
    TechniqueConceptSource, TechniqueSource, Therapy, TherapyAlias, TherapyClassification,
    TherapyClassificationLink, TherapyConcept, TherapyConceptSource, TherapyDisorder,
    TherapyDisorderSource, TherapyFamily, TherapySource, TherapyTechnique, TherapyTechniqueSource,
    TherapyBookmark, TherapyNote)
from .tests_v100_p01 import SecurityFixture, BASE


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TherapyDomainTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        ReviewPolicy.objects.get_or_create(pk=1)
        self.client = self.sign_in(self.owner)
        self.session = self.client.session["cms_session_id"]
        self.source = SourceReference.objects.create(title="P08 NON-SCIENTIFIC source.invalid",
            citation="NON-SCIENTIFIC synthetic provenance; not an efficacy claim.",
            url="https://p08.invalid/evidence", verification_status="source_checked")
        self.family = TherapyFamily.objects.create(slug="p08-family", name_en="NON-SCIENTIFIC Family")
        self.classification = TherapyClassification.objects.create(slug="p08-classification", name_en="NON-SCIENTIFIC class")
        self.therapy = Therapy.objects.create(family=self.family, slug="p08-therapy", name_en="NON-SCIENTIFIC therapy",
            summary="NON-SCIENTIFIC illustration; no therapeutic effects asserted")
        self.technique = Technique.objects.create(slug="p08-technique", name_en="NON-SCIENTIFIC technique")
        self.category = Category.objects.create(slug="p08-category", name_en="NON-SCIENTIFIC category")
        self.disorder = Disorder.objects.create(slug="p08-disorder", name_en="NON-SCIENTIFIC disorder", category=self.category)
        self.concept = Concept.objects.create(slug="p08-concept", name_en="NON-SCIENTIFIC concept", simple_definition="NON-SCIENTIFIC concept")
        self.link = TherapyTechnique.objects.create(therapy=self.therapy, technique=self.technique)
        self.therapy_disorder = TherapyDisorder.objects.create(therapy=self.therapy, disorder=self.disorder)
        self.therapy_concept = TherapyConcept.objects.create(therapy=self.therapy, concept=self.concept, relationship_type="targets")
        self.technique_concept = TechniqueConcept.objects.create(technique=self.technique, concept=self.concept, relationship_type="targets")
        self.rows = {
            "therapy-family": self.family, "therapy-classification": self.classification,
            "therapy": self.therapy, "technique": self.technique,
            "therapy-classification-link": TherapyClassificationLink.objects.create(therapy=self.therapy, classification=self.classification),
            "therapy-disorder": self.therapy_disorder, "therapy-technique": self.link,
            "therapy-concept": self.therapy_concept, "technique-concept": self.technique_concept,
            "therapy-alias": TherapyAlias.objects.create(therapy=self.therapy, text="NON-SCIENTIFIC alias"),
            "technique-alias": TechniqueAlias.objects.create(technique=self.technique, text="NON-SCIENTIFIC alias"),
            "therapy-source": TherapySource.objects.create(therapy=self.therapy, source=self.source),
            "technique-source": TechniqueSource.objects.create(technique=self.technique, source=self.source),
            "therapy-technique-source": TherapyTechniqueSource.objects.create(relationship=self.link, source=self.source),
            "therapy-disorder-source": TherapyDisorderSource.objects.create(relationship=self.therapy_disorder, source=self.source),
            "therapy-concept-source": TherapyConceptSource.objects.create(relationship=self.therapy_concept, source=self.source),
            "technique-concept-source": TechniqueConceptSource.objects.create(relationship=self.technique_concept, source=self.source),
        }

    def anchor(self, kind):
        obj=self.rows[kind]
        state=ContentState.objects.create(kind=kind, canonical_pk=obj.pk, legacy_origin=True,
            canonical_digest=content.digest(content.canonical_snapshot(kind,obj)), publication="current")
        p=content.editable_snapshot(kind,obj)
        rev=ContentRevision.objects.create(state=state, sequence=0, base_version=0, base_digest=state.canonical_digest,
            payload=p, payload_digest=content.digest(p), dependency_digest=content.dependencies(kind,obj), status="legacy")
        state.current_revision=rev;state.save(update_fields=("current_revision",))
        return state

    def test_exact_seventeen_and_no_user_owned_models(self):
        self.assertEqual(set(FIELDS),set(self.rows))
        self.assertEqual({kind for kind, spec in DOMAIN_SPECS.items() if spec["domain"]=="therapy"}, set(self.rows))
        self.assertNotIn("TherapyBookmark",{spec["model"].__name__ for spec in DOMAIN_SPECS.values()})
        self.assertNotIn("TherapyNote",{spec["model"].__name__ for spec in DOMAIN_SPECS.values()})
        self.assertTrue(all(kind in TARGET_KINDS for kind in self.rows))
        for kind,obj in self.rows.items():
            with self.subTest(kind=kind):
                schema=schema_data(kind)
                self.assertEqual(schema["domain"],"therapy")
                self.assertTrue(all(f["readonly_reason"] for f in schema["fields"] if f["name"] in {"is_active","seed_managed","review_status"}))
                self.assertEqual(content.kind_entry(kind)[0],type(obj))

    def test_seventeen_legacy_editor_digests_and_validation_are_stable(self):
        for kind, obj in self.rows.items():
            with self.subTest(kind=kind):
                original=content.canonical_snapshot(kind,obj)
                state=self.anchor(kind)
                self.assertEqual(state.canonical_digest, content.digest(original))
                self.assertNotIn("review_status",state.current_revision.payload)
                self.assertTrue(content.inspect_proposal(self.owner.pk,self.session,kind,str(state.pk),state.version,"preview")[1]["valid"])
                obj.refresh_from_db()
                self.assertEqual(content.canonical_snapshot(kind,obj),original)


    def test_all_seventeen_create_validate_and_preview_without_canonical_write(self):
        extra_source=SourceReference.objects.create(title="P08 NON-SCIENTIFIC second source",
            citation="Synthetic; not published science",url="https://p08.invalid/second")
        extra_class=TherapyClassification.objects.create(slug="p08-new-classification",name_en="Synthetic second class")
        extra_disorder=Disorder.objects.create(slug="p08-second-disorder",name_en="NON-SCIENTIFIC second disorder",category=self.category)
        extra_tech=Technique.objects.create(slug="p08-other-technique",name_en="NON-SCIENTIFIC second technique")
        extra_concept=Concept.objects.create(slug="p08-other-concept",name_en="NON-SCIENTIFIC second concept",
            simple_definition="Synthetic only")
        drafts={
            "therapy-family":{"slug":"p08-draft-family","name_en":"NON-SCIENTIFIC family draft"},
            "therapy-classification":{"slug":"p08-draft-class","name_en":"NON-SCIENTIFIC class draft"},
            "therapy":{"family":self.family.pk,"slug":"p08-draft-therapy","name_en":"NON-SCIENTIFIC therapy draft"},
            "technique":{"slug":"p08-draft-technique","name_en":"NON-SCIENTIFIC technique draft"},
            "therapy-classification-link":{"therapy":self.therapy.pk,"classification":extra_class.pk},
            "therapy-disorder":{"therapy":self.therapy.pk,"disorder":extra_disorder.pk},
            "therapy-technique":{"therapy":self.therapy.pk,"technique":extra_tech.pk},
            "therapy-concept":{"therapy":self.therapy.pk,"concept":extra_concept.pk,"relationship_type":"targets"},
            "technique-concept":{"technique":self.technique.pk,"concept":extra_concept.pk,"relationship_type":"targets"},
            "therapy-alias":{"therapy":self.therapy.pk,"text":"P08 unique NON-SCIENTIFIC alias therapy"},
            "technique-alias":{"technique":self.technique.pk,"text":"P08 unique NON-SCIENTIFIC alias technique"},
            "therapy-source":{"therapy":self.therapy.pk,"source":extra_source.pk},
            "technique-source":{"technique":self.technique.pk,"source":extra_source.pk},
            "therapy-technique-source":{"relationship":self.link.pk,"source":extra_source.pk},
            "therapy-disorder-source":{"relationship":self.therapy_disorder.pk,"source":extra_source.pk},
            "therapy-concept-source":{"relationship":self.therapy_concept.pk,"source":extra_source.pk},
            "technique-concept-source":{"relationship":self.technique_concept.pk,"source":extra_source.pk},
        }
        self.assertEqual(set(drafts),set(FIELDS))
        for kind,payload in drafts.items():
            with self.subTest(kind=kind):
                model=content.kind_entry(kind)[0]
                original=model.objects.count()
                state=content.propose(self.owner.pk,self.session,kind,None,payload,None,None,
                    "DRAFT_CREATION",uuid.uuid4())
                self.assertEqual(state.current_revision.status,"draft")
                self.assertIsNone(state.canonical_pk)
                self.assertEqual(state.publication,"never_published")
                _,preview=content.inspect_proposal(self.owner.pk,self.session,kind,str(state.pk),
                    state.version,"preview")
                self.assertTrue(preview["valid"])
                self.assertFalse(preview["publication_available"])
                self.assertEqual(model.objects.count(),original)

    def test_unsourced_technique_draft_stays_private_and_unpublished(self):
        before=Technique.objects.count()
        values={"slug":"p08-new-non-scientific","name_en":"P08 NON-SCIENTIFIC draft technique",
                "limitations":"No efficacy asserted; test-only"}
        state=content.propose(self.owner.pk,self.session,"technique",None,values,None,None,"DRAFT_CREATION",uuid.uuid4())
        self.assertEqual(state.current_revision.status,"draft")
        self.assertEqual(state.publication,"never_published")
        self.assertIsNone(state.canonical_pk)
        self.assertEqual(Technique.objects.count(),before)
        _,checked=content.inspect_proposal(self.owner.pk,self.session,"technique",str(state.pk),state.version,"preview")
        self.assertTrue(checked["valid"])
        self.assertFalse(checked["publication_available"])
        self.assertEqual(Technique.objects.count(),before)

    def test_therapy_technique_source_link_and_claim_revisions_do_not_mutate_canonical(self):
        old=content.canonical_snapshot("therapy-technique",self.link)
        state=self.anchor("therapy-technique")
        new=content.propose(self.owner.pk,self.session,"therapy-technique",str(state.pk),
            {"explanation":"NON-SCIENTIFIC candidate; no clinical claim"},state.version,state.canonical_digest,
            "CONTENT_UPDATE",uuid.uuid4())
        self.assertEqual(new.version,1)
        self.assertEqual(content.canonical_snapshot("therapy-technique",self.link),old)
        link=self.anchor("therapy-technique-source")
        self.assertIn("sources",dependency_snapshot("therapy-technique",self.link))
        self.assertEqual(self.client.get(BASE+"content/therapy-technique-source/").status_code,200)
        self.assertEqual(link.current_revision.status,"legacy")

    def test_source_edit_changes_dependency_fingerprint_and_does_not_grant_review(self):
        first=content.dependencies("therapy-technique",self.link)
        self.source.title="P08 NON-SCIENTIFIC changed .invalid"
        self.source.save()
        self.assertNotEqual(content.dependencies("therapy-technique",self.link),first)
        self.assertEqual(self.link.review_status,"unreviewed")
        self.assertFalse(content.kind_entry("therapy-technique")[0].objects.filter(pk=self.link.pk,review_status="reviewed").exists())

    def test_permissions_ref_scope_and_public_read_preserved(self):
        reader=self.user("p08-core-reader",staff=True,caps=("cms_enter","cms_core_view"))
        client=self.sign_in(reader)
        detail=self.client.get(BASE+"content/schema/").json()
        self.assertEqual(len([x for x in detail["kinds"] if x["domain"]=="therapy"]),17)
        denied=client.get(BASE+"content/therapy/")
        self.assertEqual(denied.status_code,403)
        self.assertEqual(client.get(BASE+"content/schema/").status_code,200)
        self.assertFalse(any(x["domain"]=="therapy" for x in client.get(BASE+"content/schema/").json()["kinds"]))
        scoped=self.user("p08-therapy-only",staff=True,caps=("cms_enter","cms_therapy_view","cms_therapy_create","cms_therapy_edit"))
        scoped_client=self.sign_in(scoped)
        source_state=self.anchor("therapy-source")
        self.assertEqual(scoped_client.get(BASE+f"content/therapy-source/{source_state.pk}/").status_code,403)
        self.assertNotIn("cms_therapy_delete_unused",detail)

    def test_protected_fields_and_immutable_identity_refused(self):
        state=self.anchor("therapy")
        for field in ("review_status","is_active","seed_managed","actor","source_payload"):
            with self.subTest(field=field):
                response=self.post(self.client,f"content/therapy/{state.pk}/revisions/",
                    {"payload":{field:"NON-SCIENTIFIC overwrite"},"base_digest":state.canonical_digest,
                     "reason":"CONTENT_UPDATE"},etag='"0"')
                self.assertEqual(response.status_code,400,response.content)
        response=self.post(self.client,f"content/therapy/{state.pk}/revisions/",
            {"payload":{"slug":"p08-renamed"},"base_digest":state.canonical_digest,"reason":"CONTENT_UPDATE"},etag='"0"')
        self.assertEqual(response.status_code,400)


    def test_source_review_and_approval_invalidate_when_reference_changes(self):
        from . import cms_review as review
        from .cms_review_models import ReviewTask
        state=self.anchor("therapy-technique")
        state=content.propose(self.owner.pk,self.session,"therapy-technique",str(state.pk),
            {"explanation":"NON-SCIENTIFIC source-linked explanation"},
            state.version,state.canonical_digest,"CONTENT_UPDATE",uuid.uuid4())
        evidence=[{"source_id":self.source.pk,"locator":"P08 synthetic section 1, not scientific evidence",
            "fields":[key for key,value in state.current_revision.payload.items() if value]}]
        state=review.submit_review(self.owner.pk,self.session,"therapy-technique",str(state.pk),
            state.version,evidence,uuid.uuid4())
        for kind in ("source","scientific"):
            task=ReviewTask.objects.get(subject__state=state,review_type=kind)
            state=review.assign_review(self.owner.pk,self.session,"therapy-technique",str(state.pk),
                state.version,task.pk,task.version,self.owner.pk,uuid.uuid4())
            task.refresh_from_db()
            state=review.decide_review(self.owner.pk,self.session,"therapy-technique",str(state.pk),
                state.version,task.pk,task.version,"approve",
                "SOURCE_VERIFIED" if kind=="source" else "SCIENCE_VERIFIED",[],True,uuid.uuid4())
        self.assertTrue(review.approval_eligibility(state,self.link)["eligible"])
        self.assertEqual(self.link.review_status,"unreviewed")
        self.source.citation="NON-SCIENTIFIC source changed after approval"
        self.source.save()
        self.assertIn("DEPENDENCY_CHANGED",review.approval_eligibility(state,self.link)["blockers"])
        self.assertEqual(self.link.review_status,"unreviewed")


    def test_public_compare_preview_uses_exact_public_projection_and_denies_scoped_read(self):
        other = Therapy.objects.create(family=self.family, slug="p08-other",
            name_en="NON-SCIENTIFIC other therapy", summary="NOT scientific evidence")
        restricted = self.user("p08-no-therapy-compare",staff=True,caps=("cms_enter","cms_core_view"))
        denied = self.sign_in(restricted).get(BASE+f"content/therapy/public-compare-preview/?left={self.therapy.pk}&right={other.pk}")
        self.assertEqual(denied.status_code,403)
        same = self.client.get(BASE+f"content/therapy/public-compare-preview/?left={self.therapy.pk}&right={self.therapy.pk}")
        self.assertEqual(same.status_code,400)
        missing = self.client.get(BASE+f"content/therapy/public-compare-preview/?left={self.therapy.pk}&right=99999999")
        self.assertEqual(missing.status_code,404)
        # No activation is allowed to satisfy the preview. The public selector
        # alone decides whether these currently canonical rows are visible.
        before=list(Therapy.objects.values())
        response=self.client.get(BASE+f"content/therapy/public-compare-preview/?left={self.therapy.pk}&right={other.pk}")
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()["scope"],"current_public_projection_only")
        self.assertFalse(response.json()["publication_available"])
        self.assertEqual([item["slug"] for item in response.json()["items"]],[self.therapy.slug,other.slug])
        public=self.client.get("/api/therapies/compare/?slugs="+self.therapy.slug+","+other.slug)
        self.assertEqual(public.status_code,200,public.content)
        self.assertEqual(response.json()["items"],public.json()["items"])
        self.assertEqual(list(Therapy.objects.values()),before)

    def test_public_compare_respects_scoped_rights_removal_for_both_consumers(self):
        from .cms_public_rights import public_resources
        other = Therapy.objects.create(family=self.family, slug="p08-rights-filter",
            name_en="NON-SCIENTIFIC rights restricted therapy")
        # Assert the existing P05 selector intersection is applied to BOTH the
        # pre-existing public endpoint and CMS public projection.
        with patch("atlas.views.public_resources", side_effect=lambda model: model.objects.exclude(pk=other.pk)):
            public = self.client.get("/api/therapies/compare/?slugs="+self.therapy.slug+","+other.slug)
            cms = self.client.get(BASE+f"content/therapy/public-compare-preview/?left={self.therapy.pk}&right={other.pk}")
        self.assertEqual(public.status_code,404,public.content)
        self.assertEqual(cms.status_code,404,cms.content)

    def test_bookmark_note_and_public_canonical_unchanged_after_draft_and_archive(self):
        old=content.canonical_snapshot("therapy",self.therapy)
        TherapyBookmark.objects.create(user=self.owner,therapy=self.therapy)
        TherapyNote.objects.create(user=self.owner,therapy=self.therapy,body="NON-SCIENTIFIC private note")
        personal_before=(list(TherapyBookmark.objects.values()),list(TherapyNote.objects.values()))
        state=self.anchor("therapy")
        state=content.propose(self.owner.pk,self.session,"therapy",str(state.pk),
            {"evidence_note":"NON-SCIENTIFIC not a claim"},
            state.version,state.canonical_digest,"CONTENT_UPDATE",uuid.uuid4())
        self.assertEqual(content.canonical_snapshot("therapy",self.therapy),old)
        state=content.archive_proposal(self.owner.pk,self.session,"therapy",str(state.pk),state.version,uuid.uuid4())
        self.assertEqual(state.current_revision.intent,"archive")
        self.therapy.refresh_from_db()
        self.assertTrue(self.therapy.is_active)
        self.assertEqual(content.canonical_snapshot("therapy",self.therapy),old)
        self.assertEqual((list(TherapyBookmark.objects.values()),list(TherapyNote.objects.values())),personal_before)
