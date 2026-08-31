from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from diagnostics.constants import TaskType
from diagnostics.models import (
    AudioClip, GenerationEvent, GenerationWindow, ListeningQuestionSet, Paper,
    ReadingPassage, TeacherGradeAssignment,
)


class GenerationWindowTests(TestCase):
    def test_defaults_to_open(self):
        self.assertTrue(GenerationWindow.load().is_open)

    def test_load_is_a_singleton(self):
        first = GenerationWindow.load()
        first.is_open = False
        first.save()
        self.assertFalse(GenerationWindow.load().is_open)
        self.assertEqual(GenerationWindow.objects.count(), 1)


class TeacherGradeAssignmentTests(TestCase):
    def test_a_teacher_is_assigned_a_grade_once(self):
        user = get_user_model().objects.create_user("teacher", password="x")
        TeacherGradeAssignment.objects.create(user=user, grade=9)
        self.assertEqual(
            list(TeacherGradeAssignment.grades_for(user)), [9]
        )


class GenerationEventExportFormatTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("teacher", password="x")
        clip1 = AudioClip.objects.create(number=1, task_type=TaskType.PICTURE)
        clip2 = AudioClip.objects.create(number=2, task_type=TaskType.MCQ3)
        self.paper = Paper.objects.create(
            grade=9,
            variant="A",
            listening_set_1=ListeningQuestionSet.objects.create(clip=clip1, number=1),
            listening_set_2=ListeningQuestionSet.objects.create(clip=clip2, number=1),
            reading_passage=ReadingPassage.objects.create(
                label="R01", title="T", body=" ".join(["word"] * 220)
            ),
        )

    def test_export_format_accepts_each_download_kind(self):
        for value in ("student", "answer_key", "examiner", "audio_1", "audio_2"):
            event = GenerationEvent(user=self.user, paper=self.paper,
                                     export_format=value)
            event.full_clean()

    def test_export_format_rejects_an_unknown_kind(self):
        event = GenerationEvent(user=self.user, paper=self.paper,
                                export_format="pdf")
        with self.assertRaises(ValidationError):
            event.full_clean()
