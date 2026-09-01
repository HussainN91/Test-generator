from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.test import TestCase

from diagnostics.constants import TaskType
from diagnostics.models import AudioClip, ListeningQuestion, ListeningQuestionSet


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
        self.question_set = ListeningQuestionSet.objects.create(clip=self.clip, number=1)

    def test_position_is_unique_within_a_clip(self):
        ListeningQuestion.objects.create(
            question_set=self.question_set, position=1, stem="a", answer="A"
        )
        with self.assertRaises(IntegrityError):
            ListeningQuestion.objects.create(
                question_set=self.question_set, position=1, stem="b", answer="B"
            )

    def test_position_must_be_one_to_five(self):
        question = ListeningQuestion(
            question_set=self.question_set, position=6, stem="x", answer="A"
        )
        with self.assertRaises(ValidationError):
            question.full_clean()

    def test_accepts_alternatives_for_gap_fill(self):
        clip = AudioClip.objects.create(number=3, task_type=TaskType.GAP_FILL)
        question_set = ListeningQuestionSet.objects.create(clip=clip, number=1)
        question = ListeningQuestion.objects.create(
            question_set=question_set, position=1, stem="...", answer="twenty",
            acceptable_answers=["20", "twenty"],
        )
        self.assertIn("20", question.acceptable_answers)

    def test_ordering_is_by_clip_then_position(self):
        for position in (3, 1, 2):
            ListeningQuestion.objects.create(
                question_set=self.question_set, position=position, stem="s", answer="A"
            )
        self.assertEqual(
            [q.position for q in ListeningQuestion.objects.all()], [1, 2, 3]
        )


class ListeningQuestionSetTests(TestCase):
    def setUp(self):
        self.clip = AudioClip.objects.create(number=1, task_type="picture")

    def test_a_clip_can_carry_two_sets(self):
        first = ListeningQuestionSet.objects.create(clip=self.clip, number=1)
        second = ListeningQuestionSet.objects.create(clip=self.clip, number=2)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(self.clip.question_sets.count(), 2)

    def test_the_same_set_number_cannot_repeat_on_one_clip(self):
        ListeningQuestionSet.objects.create(clip=self.clip, number=1)
        with self.assertRaises(IntegrityError):
            ListeningQuestionSet.objects.create(clip=self.clip, number=1)

    def test_set_number_is_bounded_to_the_two_sets_that_exist(self):
        question_set = ListeningQuestionSet(clip=self.clip, number=3)
        with self.assertRaises(ValidationError):
            question_set.full_clean()

    def test_str_names_the_clip_and_the_set(self):
        question_set = ListeningQuestionSet.objects.create(clip=self.clip, number=2)
        self.assertEqual(str(question_set), "Clip 1 set 2")


class ListeningQuestionParentTests(TestCase):
    """Questions hang off the set, not the clip, so the same recording can
    carry two different papers' questions."""

    def setUp(self):
        self.clip = AudioClip.objects.create(number=1, task_type="picture")
        self.set_one = ListeningQuestionSet.objects.create(clip=self.clip, number=1)
        self.set_two = ListeningQuestionSet.objects.create(clip=self.clip, number=2)

    def test_position_repeats_across_sets_on_the_same_clip(self):
        ListeningQuestion.objects.create(
            question_set=self.set_one, position=1, stem="a", answer="A"
        )
        ListeningQuestion.objects.create(
            question_set=self.set_two, position=1, stem="b", answer="B"
        )
        self.assertEqual(ListeningQuestion.objects.filter(position=1).count(), 2)

    def test_position_still_cannot_repeat_within_one_set(self):
        ListeningQuestion.objects.create(
            question_set=self.set_one, position=1, stem="a", answer="A"
        )
        with self.assertRaises(IntegrityError):
            ListeningQuestion.objects.create(
                question_set=self.set_one, position=1, stem="b", answer="B"
            )

    def test_question_reaches_its_clip_through_the_set(self):
        question = ListeningQuestion.objects.create(
            question_set=self.set_two, position=1, stem="a", answer="A"
        )
        self.assertEqual(question.clip, self.clip)

    def test_str_names_clip_set_and_position(self):
        question = ListeningQuestion.objects.create(
            question_set=self.set_two, position=3, stem="a", answer="A"
        )
        self.assertEqual(str(question), "Clip 1 set 2 Q3")

    def test_deleting_a_set_takes_its_questions(self):
        ListeningQuestion.objects.create(
            question_set=self.set_two, position=1, stem="a", answer="A"
        )
        self.set_two.delete()
        self.assertEqual(ListeningQuestion.objects.count(), 0)


class AudioClipTranscriptTests(TestCase):
    """The transcript lives on the clip because it describes the recording,
    not any one question set - both sets of questions are about the same
    audio and are checked against the same words."""

    def test_a_clip_can_carry_a_transcript(self):
        clip = AudioClip.objects.create(
            number=1, task_type="picture", transcript="Interviewer: Hello."
        )
        clip.refresh_from_db()
        self.assertEqual(clip.transcript, "Interviewer: Hello.")

    def test_transcript_defaults_to_empty_not_null(self):
        """Empty string rather than NULL, so templates and str operations
        never have to special-case None."""
        clip = AudioClip.objects.create(number=2, task_type="mcq3")
        clip.refresh_from_db()
        self.assertEqual(clip.transcript, "")
