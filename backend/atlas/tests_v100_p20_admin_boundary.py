"""P20: Django admin must never bypass bounded CMS authoring or raw DSM access."""
from django.contrib import admin
from django.test import RequestFactory, TestCase, override_settings

from . import models as m
from .tests_v100_p01 import SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DjangoAdminBoundaryTests(SecurityFixture, TestCase):
    def test_legacy_learner_and_case_writers_have_no_generic_admin_route(self):
        from config import urls  # noqa: F401 - configure_admin is part of URL initialization
        forbidden = (
            m.Bookmark, m.CaseAttempt, m.CaseAttemptEvent, m.CaseChoice,
            m.CaseQuestion, m.CaseScoringDimension, m.CaseStep,
            m.CaseRevision, m.CaseTransition, m.ClinicalCase,
            m.Quiz, m.QuizAttempt, m.QuizChoice, m.QuizQuestion, m.UserProgress,
        )
        for model in forbidden:
            with self.subTest(model=model.__name__):
                self.assertFalse(admin.site.is_registered(model))
        client = self.sign_in(self.owner)
        for path in ("/admin/atlas/quiz/add/", "/admin/atlas/caseattempt/add/",
                     "/admin/atlas/clinicalcase/"):
            response = client.get(path)
            self.assertEqual(response.status_code, 404, (path, response.status_code))

    def test_raw_dsm_json_not_exposed_even_to_authorized_content_viewer(self):
        from config import urls  # noqa: F401
        corpus = m.DSMCorpus.objects.create(
            key="p20-private-raw", title="Synthetic DSM corpus",
            source_filename="synthetic.json", source_sha256="a" * 64,
            raw_document={"secret": "PRIVATE_DSM_RAW_DOCUMENT_MARKER"},
        )
        record = m.DSMRecord.objects.create(
            corpus=corpus, master_id="p20-record", name_en="Synthetic record",
            source_payload={"secret": "PRIVATE_DSM_SOURCE_PAYLOAD_MARKER"},
        )
        request = RequestFactory().get("/admin/")
        request.user = self.owner
        for model, field in ((m.DSMCorpus, "raw_document"), (m.DSMRecord, "source_payload")):
            handler = admin.site._registry[model]
            self.assertFalse(handler.has_change_permission(request))
            self.assertFalse(handler.has_add_permission(request))
            self.assertFalse(handler.has_delete_permission(request))
            self.assertNotIn(field, handler.get_fields(request, corpus if model is m.DSMCorpus else record))
        client = self.sign_in(self.owner)
        for model, obj in ((m.DSMCorpus, corpus), (m.DSMRecord, record)):
            path = f"/admin/atlas/{model._meta.model_name}/{obj.pk}/change/"
            response = client.get(path)
            self.assertEqual(response.status_code, 200, (path, response.status_code))
            self.assertNotIn(b"PRIVATE_DSM_", response.content)
            response = client.post(path, {"raw_document": '{"secret":"OVERWRITTEN"}'})
            self.assertEqual(response.status_code, 403)
        corpus.refresh_from_db()
        record.refresh_from_db()
        self.assertEqual(corpus.raw_document["secret"], "PRIVATE_DSM_RAW_DOCUMENT_MARKER")
        self.assertEqual(record.source_payload["secret"], "PRIVATE_DSM_SOURCE_PAYLOAD_MARKER")

    def test_all_atlas_admin_handlers_are_explicitly_readonly(self):
        from config import urls  # noqa: F401
        from .cms_integration import ReadOnlySecurityAdmin
        request = RequestFactory().get("/admin/")
        request.user = self.owner
        registered = [(model, handler) for model, handler in admin.site._registry.items()
                      if model._meta.app_label == "atlas"]
        self.assertGreaterEqual(len(registered), 90)
        for model, handler in registered:
            with self.subTest(model=model.__name__):
                self.assertIsInstance(handler, ReadOnlySecurityAdmin)
                self.assertFalse(handler.has_add_permission(request))
                self.assertFalse(handler.has_change_permission(request))
                self.assertFalse(handler.has_delete_permission(request))
                self.assertNotIn("delete_selected", handler.get_actions(request))
                self.assertFalse({"raw_document", "source_payload"} &
                                 set(handler.get_fields(request)))

    def test_other_role_cannot_read_raw_dsm_admin(self):
        from config import urls  # noqa: F401
        corpus = m.DSMCorpus.objects.create(
            key="p20-role-denied", title="Synthetic", source_filename="safe.json",
            source_sha256="b" * 64, raw_document={"private": "PRIVATE_DSM_"})
        client = self.sign_in(self.scoped)
        response = client.get(f"/admin/atlas/dsmcorpus/{corpus.pk}/change/")
        self.assertIn(response.status_code, (403, 404))
        self.assertNotIn(b"PRIVATE_DSM_", response.content)
