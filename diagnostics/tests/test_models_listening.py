from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.test import TestCase

from diagnostics.constants import TaskType
from diagnostics.models import AudioClip, ListeningQuestion


class AudioClipTests(TestCase):
    def test_clip_number_is_unique(self):
        AudioClip.objects.create(number=1, task_type=TaskType.PICTURE)
        with self.assertRaises(IntegrityError):
            AudioClip.objects.create(number=1, task_type=TaskType.MCQ3)

    def test_str_shows_number_and_type(self):
        clip = AudioClip.objects.create(number=3, task_type=TaskType.GAP_FILL)
        self.assertEqual(str(clip), "Clip 3 (Note/form gap-fill)")


class ListeningQuestionTests(TestCase):
    def setUp(self):
        self.clip = AudioClip.objects.create(number=2, task_type=TaskType.MCQ3)

    def test_position_is_unique_within_a_clip(self):
        ListeningQuestion.objects.create(clip=self.clip, position=1, stem="a", answer="A")
        with self.assertRaises(IntegrityError):
            ListeningQuestion.objects.create(clip=self.clip, position=1, stem="b", answer="B")

    def test_position_must_be_one_to_five(self):
        question = ListeningQuestion(clip=self.clip, position=6, stem="x", answer="A")
        with self.assertRaises(ValidationError):
            question.full_clean()

    def test_accepts_alternatives_for_gap_fill(self):
        clip = AudioClip.objects.create(number=3, task_type=TaskType.GAP_FILL)
        question = ListeningQuestion.objects.create(
            clip=clip, position=1, stem="...", answer="twenty",
            acceptable_answers=["20", "twenty"],
        )
        self.assertIn("20", question.acceptable_answers)

    def test_ordering_is_by_clip_then_position(self):
        for position in (3, 1, 2):
            ListeningQuestion.objects.create(
                clip=self.clip, position=position, stem="s", answer="A"
            )
        self.assertEqual(
            [q.position for q in ListeningQuestion.objects.all()], [1, 2, 3]
        )
