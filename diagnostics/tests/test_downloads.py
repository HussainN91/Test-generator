"""Each file downloads on its own. The ZIP pack is gone.

Management's stated reason: a zip is awkward for teachers. Photos are NOT
downloadable separately - they exist only embedded inside the test document
(Design Revision 2, section 7).
"""

import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from diagnostics.models import (
    AudioClip, GenerationEvent, GenerationWindow, ListeningQuestionSet, Paper,
    ReadingPassage,
)

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class DownloadTests(TestCase):
    """FileField writes (the two audio clips) survive DB transaction
    rollback undone, so MEDIA_ROOT is redirected to a scratch directory for
    the whole class — same pattern as ImportListeningTests in
    test_import_listening.py."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp(prefix="diagnostics_test_media_")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="teacher", password="x", is_staff=True
        )
        self.client.force_login(self.user)

        clip1 = AudioClip.objects.create(number=1, task_type="picture")
        clip1.audio_file.save("clip1.mp3", ContentFile(b"fake mp3 data one"))
        clip2 = AudioClip.objects.create(number=2, task_type="mcq3")
        clip2.audio_file.save("clip2.mp3", ContentFile(b"fake mp3 data two"))
        set1 = ListeningQuestionSet.objects.create(clip=clip1, number=1)
        set2 = ListeningQuestionSet.objects.create(clip=clip2, number=1)
        passage = ReadingPassage.objects.create(
            label="R01", title="T", body="word " * 200
        )
        self.paper = Paper.objects.create(
            grade=9, variant="A", listening_set_1=set1, listening_set_2=set2,
            reading_passage=passage, is_published=True,
        )
        GenerationWindow.load()  # ensure a row exists; is_open defaults True

    def test_each_document_downloads_separately(self):
        for kind, suffix in (
            ("student", "Student.docx"),
            ("answer_key", "AnswerKey.docx"),
            ("examiner", "Examiner.docx"),
        ):
            response = self.client.get(
                reverse("diagnostics:paper_file",
                        args=[self.paper.grade, self.paper.variant, kind])
            )
            self.assertEqual(response.status_code, 200, kind)
            self.assertEqual(response["Content-Type"], DOCX)
            self.assertIn(suffix, response["Content-Disposition"])

    def test_each_recording_downloads_separately(self):
        for kind in ("audio_1", "audio_2"):
            response = self.client.get(
                reverse("diagnostics:paper_file",
                        args=[self.paper.grade, self.paper.variant, kind])
            )
            self.assertEqual(response.status_code, 200, kind)

    def test_every_download_is_recorded(self):
        for kind in ("student", "answer_key", "examiner", "audio_1", "audio_2"):
            self.client.get(reverse(
                "diagnostics:paper_file",
                args=[self.paper.grade, self.paper.variant, kind]))
        self.assertEqual(
            set(GenerationEvent.objects.filter(paper=self.paper).values_list(
                "export_format", flat=True)),
            {"student", "answer_key", "examiner", "audio_1", "audio_2"},
        )

    def test_unknown_file_kind_is_404(self):
        response = self.client.get(
            reverse("diagnostics:paper_file",
                    args=[self.paper.grade, self.paper.variant, "photos"]))
        self.assertEqual(response.status_code, 404)

    def test_downloads_refused_when_generation_is_closed(self):
        window = GenerationWindow.load()
        window.is_open = False
        window.save()
        for kind in ("student", "answer_key", "examiner", "audio_1", "audio_2"):
            response = self.client.get(reverse(
                "diagnostics:paper_file",
                args=[self.paper.grade, self.paper.variant, kind]))
            self.assertEqual(response.status_code, 404, kind)
