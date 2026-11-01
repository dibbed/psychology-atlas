"""P13 flashcard editorial invariants: SRS identity is never reset by CMS."""
from django.test import TestCase, override_settings

from .models import Flashcard, UserFlashcardProgress, StudyActivity
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FlashcardCmsTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.sign_in(self.owner)
        self.card = Flashcard.objects.create(
            slug="p13-synthetic-flashcard", front="Fictional prompt",
            back="Fictional answer", is_active=False, seed_managed=False,
        )

    def path(self, card=None):
        return "learning/flashcards/" + str(card or self.card.pk) + "/"

    def test_new_private_card_and_edit_with_strong_etag(self):
        created = self.post(self.admin, "learning/flashcards/", {
            "slug": "p13-new-card", "front": "Fictional front",
            "back": "Fictional back", "hint": "", "difficulty": "basic",
            "concept_id": None, "disorder_id": None,
        })
        self.assertEqual(created.status_code, 201, created.content[:300])
        card = Flashcard.objects.get(pk=created.json()["flashcard_id"])
        self.assertFalse(card.is_active)
        self.assertFalse(card.seed_managed)
        self.assertEqual(self.admin.get(BASE + "learning/flashcards/").status_code, 200)
        old = self.admin.get(BASE + self.path())
        self.assertEqual(old.status_code, 200)
        tag = old["ETag"]
        edited = self.post(self.admin, self.path() + "metadata/", {"front": "New fictional prompt"}, etag=tag)
        self.assertEqual(edited.status_code, 200, edited.content[:300])
        self.card.refresh_from_db()
        self.assertEqual(self.card.front, "New fictional prompt")
        self.assertEqual(self.post(self.admin, self.path()+"metadata/",
            {"back": "Stale answer"}, etag=tag).status_code, 412)

    def test_existing_progress_blocks_edit_and_preserves_srs(self):
        progress = UserFlashcardProgress.objects.create(
            user=self.normal, flashcard=self.card, state=UserFlashcardProgress.State.REVIEW,
            repetitions=6, lapses=2, interval_days=17, ease_factor=2.2,
        )
        tag = self.admin.get(BASE + self.path())["ETag"]
        blocked = self.post(self.admin, self.path()+"metadata/", {"front":"Tampered"}, etag=tag)
        self.assertEqual(blocked.status_code, 409, blocked.content[:300])
        progress.refresh_from_db()
        self.assertEqual((progress.repetitions, progress.lapses, progress.interval_days, progress.ease_factor),
                         (6, 2, 17, 2.2))
        self.card.refresh_from_db()
        self.assertEqual(self.card.front, "Fictional prompt")
        self.assertEqual(StudyActivity.objects.count(), 0)

    def test_viewer_cannot_create_edit_or_bypass_view_scope(self):
        viewer = self.user("p13-card-viewer", staff=True, caps=("cms_enter", "cms_learning_view"))
        viewer_client = self.sign_in(viewer)
        self.assertEqual(viewer_client.get(BASE + self.path()).status_code, 200)
        self.assertEqual(self.post(viewer_client, self.path()+"metadata/", {"front":"No"}).status_code, 403)
        editor_only = self.user("p13-card-edit-no-view", staff=True,
            caps=("cms_enter", "cms_learning_edit"))
        editor_client = self.sign_in(editor_only)
        self.assertEqual(self.post(editor_client, self.path()+"metadata/", {"front":"No"},
            etag=self.admin.get(BASE+self.path())["ETag"]).status_code, 403)
        self.assertEqual(self.admin.get(BASE + "learning/flashcards/999999/").status_code, 404)
