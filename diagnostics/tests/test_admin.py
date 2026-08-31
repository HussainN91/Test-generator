"""The admin must make every diagnostics model browsable.

The admin is the review queue (config/urls.py) — if a model is not registered
there is no way to look at what the import commands produced. The change-page
tests exist because inline misconfiguration is the failure that actually
happens, and it only shows up when the page is rendered.
"""

from io import StringIO

from django.apps import apps
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import RequestFactory, TestCase

from diagnostics.models import (
    AudioClip, Paper, ReadingPassage, SpeakingPrompt, WritingQuestion,
)
from diagnostics.tests.test_build_papers import seed_content


class AdminRegistrationTests(TestCase):
    def test_every_diagnostics_model_is_registered(self):
        unregistered = [
            model._meta.label
            for model in apps.get_app_config("diagnostics").get_models()
            if not admin.site.is_registered(model)
        ]
        self.assertEqual(unregistered, [], f"not browsable in the admin: {unregistered}")

    def test_paper_admin_has_both_slot_inlines(self):
        inline_models = {
            inline.model._meta.model_name
            for inline in admin.site._registry[Paper].inlines
        }
        self.assertEqual(inline_models, {"paperwritingquestion", "paperspeakingprompt"})

    def test_audio_clip_admin_shows_its_question_sets_inline(self):
        inline_models = [
            inline.model._meta.model_name
            for inline in admin.site._registry[AudioClip].inlines
        ]
        self.assertEqual(inline_models, ["listeningquestionset"])

    def test_reading_passage_admin_shows_its_questions_inline(self):
        inline_models = [
            inline.model._meta.model_name
            for inline in admin.site._registry[ReadingPassage].inlines
        ]
        self.assertEqual(inline_models, ["readingquestion"])

    def _superuser_request(self):
        """A request from someone with every permission Django can grant.

        The point of the next two tests is that the *admin class* refuses,
        not that the user happens to lack a permission — so the user must be
        one who would otherwise be allowed everything.
        """
        request = RequestFactory().get("/admin/")
        request.user = get_user_model()(
            username="super", is_superuser=True, is_staff=True, is_active=True
        )
        return request

    def test_imported_content_banks_are_not_hand_editable(self):
        """Import commands overwrite these — hand edits would vanish silently."""
        request = self._superuser_request()
        for model in (AudioClip, ReadingPassage, WritingQuestion, SpeakingPrompt):
            model_admin = admin.site._registry[model]
            self.assertFalse(
                model_admin.has_add_permission(request),
                f"{model.__name__} allows adding",
            )
            self.assertFalse(
                model_admin.has_delete_permission(request),
                f"{model.__name__} allows deleting",
            )

    def test_papers_stay_editable(self):
        request = self._superuser_request()
        paper_admin = admin.site._registry[Paper]
        self.assertTrue(paper_admin.has_add_permission(request))
        self.assertTrue(paper_admin.has_delete_permission(request))

    def test_writing_bank_is_filterable_and_searchable(self):
        model_admin = admin.site._registry[WritingQuestion]
        self.assertIn("subtype", model_admin.list_filter)
        self.assertIn("stem", model_admin.search_fields)

    def test_speaking_bank_is_filterable_and_searchable(self):
        model_admin = admin.site._registry[SpeakingPrompt]
        self.assertIn("task", model_admin.list_filter)
        self.assertIn("prompt", model_admin.search_fields)

    def test_paper_list_display_and_filter(self):
        model_admin = admin.site._registry[Paper]
        for field in (
            "grade", "variant", "listening_set_1", "listening_set_2",
            "reading_passage", "is_published",
        ):
            self.assertIn(field, model_admin.list_display)
        self.assertIn("grade", model_admin.list_filter)


class AdminPagesLoadTests(TestCase):
    """A registered model that 500s on its change page is not browsable."""

    def setUp(self):
        seed_content()
        call_command("build_papers", stdout=StringIO())
        self.user = get_user_model().objects.create_superuser(
            username="admin", email="admin@example.com", password="pw"
        )
        self.client.force_login(self.user)

    def test_admin_index_loads(self):
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_paper_changelist_loads(self):
        self.assertEqual(self.client.get("/admin/diagnostics/paper/").status_code, 200)

    def test_paper_change_page_loads(self):
        paper = Paper.objects.get(grade=9, variant="A")
        response = self.client.get(f"/admin/diagnostics/paper/{paper.pk}/change/")
        self.assertEqual(response.status_code, 200)

    def test_every_diagnostics_changelist_loads(self):
        for model in apps.get_app_config("diagnostics").get_models():
            meta = model._meta
            url = f"/admin/diagnostics/{meta.model_name}/"
            with self.subTest(model=meta.model_name):
                self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_audio_clip_change_page_loads(self):
        clip = AudioClip.objects.get(number=1)
        response = self.client.get(f"/admin/diagnostics/audioclip/{clip.pk}/change/")
        self.assertEqual(response.status_code, 200)

    def test_reading_passage_change_page_loads(self):
        passage = ReadingPassage.objects.get(label="R01")
        response = self.client.get(
            f"/admin/diagnostics/readingpassage/{passage.pk}/change/"
        )
        self.assertEqual(response.status_code, 200)
