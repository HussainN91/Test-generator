import shutil
import tempfile
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings

from diagnostics.constants import CLIP_TASK_TYPES
from diagnostics.models import AudioClip, ListeningQuestion

SOURCE = settings.DIAGNOSTICS_SOURCE_DIR


class ImportListeningTests(TestCase):
    """Import writes real ImageField/FileField files, which DB transaction
    rollback does not undo — so tests must redirect MEDIA_ROOT to a scratch
    directory, or every test run leaks files into the real media folder."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not (SOURCE / "Listening Question Bank -2026 EC.md").exists():
            raise AssertionError(f"Source material missing under {SOURCE}")
        cls._media_root = tempfile.mkdtemp(prefix="diagnostics_test_media_")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def test_imports_twenty_clips_and_one_hundred_questions(self):
        call_command("import_listening", stdout=StringIO())
        self.assertEqual(AudioClip.objects.count(), 20)
        self.assertEqual(ListeningQuestion.objects.count(), 100)

    def test_task_types_match_the_verified_constants(self):
        call_command("import_listening", stdout=StringIO())
        for clip in AudioClip.objects.all():
            self.assertEqual(clip.task_type, CLIP_TASK_TYPES[clip.number])

    def test_letter_clips_have_letter_answers(self):
        call_command("import_listening", stdout=StringIO())
        for clip in AudioClip.objects.filter(number__in=[1, 2, 4]):
            for question in clip.questions.all():
                self.assertIn(question.answer, {"A", "B", "C"})

    def test_picture_clips_have_images_attached(self):
        call_command("import_listening", stdout=StringIO())
        for number in (1, 5, 9, 13, 15):
            clip = AudioClip.objects.get(number=number)
            for question in clip.questions.all():
                self.assertTrue(question.image, f"clip {number} Q{question.position}")

    def test_running_twice_is_idempotent(self):
        call_command("import_listening", stdout=StringIO())
        call_command("import_listening", stdout=StringIO())
        self.assertEqual(AudioClip.objects.count(), 20)
        self.assertEqual(ListeningQuestion.objects.count(), 100)

    def test_known_source_typos_are_corrected_on_import(self):
        from diagnostics.constants import STEM_CORRECTIONS
        call_command("import_listening", stdout=StringIO())
        for (number, position), (wrong, right) in STEM_CORRECTIONS.items():
            question = ListeningQuestion.objects.get(
                clip__number=number, position=position
            )
            self.assertEqual(question.stem, right, f"clip {number} Q{position}")
            self.assertNotEqual(question.stem, wrong)
