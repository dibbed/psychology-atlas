"""P09 synthetic evidence: all historical kinds, provenance, chronology, direction."""
import subprocess
import sys
import uuid
from rest_framework.exceptions import ValidationError
from django.test import SimpleTestCase,TestCase,override_settings

from . import cms_content as content, cms_review as review
from .cms_content_models import ContentRevision,ContentState
from .cms_domains import DOMAIN_SPECS,schema_data,validate_snapshot,dependency_snapshot
from .cms_history_domains import FIELDS
from .cms_policy import CMSFailure
from .cms_review_models import ReviewPolicy,ReviewTask
from .models import (
    Psychologist,PsychologistAlias,PsychologistSource,PsychologistTheory,
    PsychologistTheorySource,PsychologistConcept,PsychologistConceptSource,
    PsychologistTherapy,PsychologistTherapySource,PsychologistPsychologist,
    PsychologistPsychologistSource,Theory,TheoryAlias,TheorySource,TheoryConcept,
    TheoryConceptSource,TheoryTherapy,TheoryTherapySource,TheoryTechnique,
    TheoryTechniqueSource,TheoryTheory,TheoryTheorySource,TimelineEvent,
    TimelineEventSource,TimelinePsychologist,TimelinePsychologistSource,
    TimelineTheory,TimelineTheorySource,TimelineTherapy,TimelineTherapySource,
    TimelineTechnique,TimelineTechniqueSource,TimelineConcept,TimelineConceptSource,
    SourceReference,Concept,Technique,Therapy,TherapyFamily
)
from .tests_v100_p01 import SecurityFixture,BASE


class HistoryImportOrderTests(SimpleTestCase):
    def test_history_and_domain_imports_work_in_either_order(self):
        for first, second in (
            ("atlas.cms_history_domains", "atlas.cms_domains"),
            ("atlas.cms_domains", "atlas.cms_history_domains"),
        ):
            with self.subTest(first=first):
                code = (
                    "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); "
                    "import django; django.setup(); "
                    f"import {first}; import {second}; "
                    "from atlas.cms_domains import DOMAIN_SPECS; "
                    "assert len([x for x in DOMAIN_SPECS.values() if x['domain'] == 'history']) == 34"
                )
                result = subprocess.run(
                    [sys.executable, "-c", code],
                    capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class HistoryDomainTests(SecurityFixture,TestCase):
    def setUp(self):
        super().setUp()
        ReviewPolicy.objects.get_or_create(pk=1)
        self.client=self.sign_in(self.owner)
        self.session=self.client.session["cms_session_id"]
        self.source=SourceReference.objects.create(title="P09 NON-SCIENTIFIC archival source",
            citation="NON-SCIENTIFIC synthetic test only; no authorship or claim",
            url="https://p09.invalid/history",verification_status="source_checked")
        self.p=Psychologist.objects.create(slug="p09-person",name_en="P09 NON-SCIENTIFIC person",
            birth_year=1901,death_year=1991)
        self.p2=Psychologist.objects.create(slug="p09-person-other",name_en="P09 NON-SCIENTIFIC person 2",
            birth_year=1902,death_year=1992)
        self.t=Theory.objects.create(slug="p09-theory",name_en="P09 NON-SCIENTIFIC theory")
        self.t2=Theory.objects.create(slug="p09-theory-other",name_en="P09 NON-SCIENTIFIC theory 2")
        self.event=TimelineEvent.objects.create(slug="p09-year-event",title_en="P09 NON-SCIENTIFIC milestone",
            date_precision="year",year_start=1950,event_type="publication")
        self.unknown=TimelineEvent.objects.create(slug="p09-unknown",title_en="P09 NON-SCIENTIFIC undated",
            date_precision="unknown",year_start=None,exact_date=None)
        self.concept=Concept.objects.create(slug="p09-concept",name_en="NON-SCIENTIFIC concept",
            simple_definition="Synthetic")
        self.family=TherapyFamily.objects.create(slug="p09-family",name_en="NON-SCIENTIFIC family")
        self.therapy=Therapy.objects.create(family=self.family,slug="p09-therapy",name_en="NON-SCIENTIFIC therapy")
        self.technique=Technique.objects.create(slug="p09-technique",name_en="NON-SCIENTIFIC technique")
        pt=PsychologistTheory.objects.create(psychologist=self.p,theory=self.t,relationship_type="proposed")
        pc=PsychologistConcept.objects.create(psychologist=self.p,concept=self.concept,relationship_type="associated_with")
        ptr=PsychologistTherapy.objects.create(psychologist=self.p,therapy=self.therapy,relationship_type="associated_with")
        pp=PsychologistPsychologist.objects.create(psychologist=self.p,related_psychologist=self.p2,relationship_type="influenced")
        tc=TheoryConcept.objects.create(theory=self.t,concept=self.concept,relationship_type="informs")
        ttr=TheoryTherapy.objects.create(theory=self.t,therapy=self.therapy,relationship_type="informs")
        ttk=TheoryTechnique.objects.create(theory=self.t,technique=self.technique,relationship_type="informs")
        tt=TheoryTheory.objects.create(theory=self.t,related_theory=self.t2,relationship_type="extends")
        ep=TimelinePsychologist.objects.create(event=self.event,psychologist=self.p,role="related")
        et=TimelineTheory.objects.create(event=self.event,theory=self.t,role="related")
        eth=TimelineTherapy.objects.create(event=self.event,therapy=self.therapy,role="related")
        etk=TimelineTechnique.objects.create(event=self.event,technique=self.technique,role="related")
        ec=TimelineConcept.objects.create(event=self.event,concept=self.concept,role="related")
        self.objects={
          "psychologist":self.p,
          "psychologist-alias":PsychologistAlias.objects.create(psychologist=self.p,text="P09 synthetic alias"),
          "psychologist-source":PsychologistSource.objects.create(psychologist=self.p,source=self.source),
          "psychologist-theory":pt,
          "psychologist-theory-source":PsychologistTheorySource.objects.create(relationship=pt,source=self.source),
          "psychologist-concept":pc,
          "psychologist-concept-source":PsychologistConceptSource.objects.create(relationship=pc,source=self.source),
          "psychologist-therapy":ptr,
          "psychologist-therapy-source":PsychologistTherapySource.objects.create(relationship=ptr,source=self.source),
          "psychologist-psychologist":pp,
          "psychologist-psychologist-source":PsychologistPsychologistSource.objects.create(relationship=pp,source=self.source),
          "theory":self.t,
          "theory-alias":TheoryAlias.objects.create(theory=self.t,text="P09 synthetic theory alias"),
          "theory-source":TheorySource.objects.create(theory=self.t,source=self.source),
          "theory-concept":tc,
          "theory-concept-source":TheoryConceptSource.objects.create(relationship=tc,source=self.source),
          "theory-therapy":ttr,
          "theory-therapy-source":TheoryTherapySource.objects.create(relationship=ttr,source=self.source),
          "theory-technique":ttk,
          "theory-technique-source":TheoryTechniqueSource.objects.create(relationship=ttk,source=self.source),
          "theory-theory":tt,
          "theory-theory-source":TheoryTheorySource.objects.create(relationship=tt,source=self.source),
          "timeline-event":self.event,
          "timeline-event-source":TimelineEventSource.objects.create(event=self.event,source=self.source),
          "timeline-psychologist":ep,
          "timeline-psychologist-source":TimelinePsychologistSource.objects.create(relationship=ep,source=self.source),
          "timeline-theory":et,
          "timeline-theory-source":TimelineTheorySource.objects.create(relationship=et,source=self.source),
          "timeline-therapy":eth,
          "timeline-therapy-source":TimelineTherapySource.objects.create(relationship=eth,source=self.source),
          "timeline-technique":etk,
          "timeline-technique-source":TimelineTechniqueSource.objects.create(relationship=etk,source=self.source),
          "timeline-concept":ec,
          "timeline-concept-source":TimelineConceptSource.objects.create(relationship=ec,source=self.source),
        }

    def anchor(self,kind):
        obj=self.objects[kind]
        state=ContentState.objects.create(kind=kind,canonical_pk=obj.pk,legacy_origin=True,
            canonical_digest=content.digest(content.canonical_snapshot(kind,obj)),publication="current")
        payload=content.editable_snapshot(kind,obj)
        rev=ContentRevision.objects.create(state=state,sequence=0,base_version=0,
            base_digest=state.canonical_digest,payload=payload,payload_digest=content.digest(payload),
            dependency_digest=content.dependencies(kind,obj),status="legacy")
        state.current_revision=rev;state.save(update_fields=("current_revision",))
        return state

    def test_all_34_history_kinds_have_bounded_typed_schemas(self):
        self.assertEqual(set(FIELDS),set(self.objects))
        self.assertEqual({kind for kind,v in DOMAIN_SPECS.items() if v["domain"]=="history"},set(self.objects))
        for kind,obj in self.objects.items():
            with self.subTest(kind=kind):
                self.assertIs(content.kind_entry(kind)[0],type(obj))
                schema=schema_data(kind)
                self.assertEqual(schema["domain"],"history")
                self.assertFalse(any(f["name"] in {"review_status","seed_managed","is_active"}
                    and not f.get("readonly_reason") for f in schema["fields"]))
                self.assertTrue(content.editable_snapshot(kind,obj) is not None)

    def test_34_legacy_proposals_preview_and_modify_without_live_or_graph_changes(self):
        fields={"psychologist":"summary_en","theory":"summary_en","timeline-event":"description_en",
            "psychologist-alias":"text","theory-alias":"text"}
        for kind,obj in self.objects.items():
            with self.subTest(kind=kind):
                before=content.canonical_snapshot(kind,obj)
                state=self.anchor(kind)
                self.assertEqual(state.current_revision.status,"legacy")
                _,inspection=content.inspect_proposal(self.owner.pk,self.session,kind,str(state.pk),0,"preview")
                self.assertTrue(inspection["valid"])
                self.assertFalse(inspection["publication_available"])
                field=fields.get(kind,"note" if kind.endswith("-source") else "explanation_en")
                state=content.propose(self.owner.pk,self.session,kind,str(state.pk),
                    {field:"P09 NON-SCIENTIFIC candidate"},state.version,state.canonical_digest,
                    "CONTENT_UPDATE",uuid.uuid4())
                self.assertEqual(state.current_revision.status,"draft")
                self.assertEqual(content.canonical_snapshot(kind,obj),before)

    def test_timeline_precision_must_not_invent_a_date(self):
        valid={"slug":"p09-candidate","title_en":"P09 NON-SCIENTIFIC",
          "date_precision":"year_range","year_start":1921,"year_end":1932}
        self.assertEqual(validate_snapshot("timeline-event",valid)["year_end"],1932)
        for invalid in (
          {**valid,"year_start":1933},
          {**valid,"year_end":None},
          {**valid,"date_precision":"unknown","exact_date":"1921-01-02"},
          {**valid,"date_precision":"exact_date","exact_date":None},
          {**valid,"date_precision":"year","exact_date":"1921-01-02"},
        ):
            with self.subTest(invalid=invalid),self.assertRaises(ValidationError):
                validate_snapshot("timeline-event",invalid)
        with self.assertRaises(ValidationError):
            validate_snapshot("psychologist",{"slug":"p09-invalid-born","name_en":"Synthetic",
              "birth_year":1990,"death_year":1920})

    def test_directed_attribution_and_self_links_fail_closed(self):
        self.assertNotEqual((self.objects["psychologist-psychologist"].psychologist_id,
            self.objects["psychologist-psychologist"].related_psychologist_id),
            (self.objects["psychologist-psychologist"].related_psychologist_id,
             self.objects["psychologist-psychologist"].psychologist_id))
        for kind,values in (
          ("psychologist-psychologist",{"psychologist":self.p.pk,"related_psychologist":self.p.pk,
            "relationship_type":"influenced"}),
          ("theory-theory",{"theory":self.t.pk,"related_theory":self.t.pk,
            "relationship_type":"extends"}),
        ):
            with self.subTest(kind=kind),self.assertRaises(ValidationError):
                validate_snapshot(kind,values)

    def test_real_private_chronology_and_weak_citation_queue_have_no_autoreview(self):
        path=BASE+"content/history/chronology/"
        response=self.client.get(path)
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()["count"],2)
        rows=response.json()["results"]
        unknown=next(item for item in rows if item["id"]==self.unknown.pk)
        self.assertIsNone(unknown["year_start"])
        self.assertIsNone(unknown["exact_date"])
        self.assertEqual(unknown["date_precision"],"unknown")
        self.assertTrue(unknown["citation_debt"])
        self.assertFalse(next(item for item in rows if item["id"]==self.event.pk)["citation_debt"])
        self.assertEqual(self.client.get(path+"?weak_only=1").json()["count"],1)
        self.assertEqual(self.client.get(path+"?year_min=1950").json()["count"],1)
        self.assertEqual(self.client.get(path+"?year_min=2099&year_max=1900").status_code,400)
        self.assertEqual(self.client.get(path+"?precision=exact_date&year_min=1").json()["count"],0)
        weak=self.client.get(BASE+"content/history/citation-debt/?kind=psychologist")
        self.assertEqual(weak.status_code,200)
        self.assertTrue(all(row["auto_approval"] is False for row in weak.json()["results"]))
        self.assertEqual(self.p.review_status,"unreviewed")
        scoped=self.user("p09-no-history-view",staff=True,caps=("cms_enter","cms_core_view"))
        client=self.sign_in(scoped)
        self.assertEqual(client.get(path).status_code,403)
        self.assertEqual(client.get(BASE+"content/history/citation-debt/?kind=theory").status_code,403)

    def test_history_review_and_source_change_invalidate_without_live_mutation(self):
        state=self.anchor("psychologist-theory")
        original=content.canonical_snapshot(state.kind,self.objects[state.kind])
        state=content.propose(self.owner.pk,self.session,state.kind,str(state.pk),
            {"explanation_en":"P09 NON-SCIENTIFIC proposed attribution"},
            state.version,state.canonical_digest,"CONTENT_UPDATE",uuid.uuid4())
        evidence=[{"source_id":self.source.pk,"locator":"P09 NON-SCIENTIFIC example section",
            "fields":[key for key,value in state.current_revision.payload.items() if value]}]
        state=review.submit_review(self.owner.pk,self.session,state.kind,str(state.pk),state.version,
            evidence,uuid.uuid4())
        for kind in ("source","scientific"):
            task=ReviewTask.objects.get(subject__state=state,review_type=kind)
            state=review.assign_review(self.owner.pk,self.session,state.kind,str(state.pk),state.version,
                task.pk,task.version,self.owner.pk,uuid.uuid4())
            task.refresh_from_db()
            state=review.decide_review(self.owner.pk,self.session,state.kind,str(state.pk),state.version,
                task.pk,task.version,"approve","SOURCE_VERIFIED" if kind=="source" else "SCIENCE_VERIFIED",[],True,uuid.uuid4())
        self.assertTrue(review.approval_eligibility(state,self.objects[state.kind])["eligible"])
        self.assertEqual(content.canonical_snapshot(state.kind,self.objects[state.kind]),original)
        self.source.citation="P09 synthetic evidence revised"
        self.source.save()
        self.assertIn("DEPENDENCY_CHANGED",review.approval_eligibility(state,self.objects[state.kind])["blockers"])
        self.assertEqual(self.objects[state.kind].review_status,"unreviewed")

    def test_archive_is_just_private_intent_no_public_timeline_edit(self):
        state=self.anchor("timeline-event")
        before=list(TimelineEvent.objects.order_by("pk").values())
        state=content.archive_proposal(self.owner.pk,self.session,"timeline-event",str(state.pk),
            state.version,uuid.uuid4())
        self.assertEqual(state.current_revision.intent,"archive")
        self.assertEqual(list(TimelineEvent.objects.order_by("pk").values()),before)
        self.assertTrue(self.event.is_active)
