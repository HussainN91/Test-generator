from django.core.exceptions import ValidationError
from django.test import TestCase

from diagnostics.models import (
    ReadingPassage, ReadingQuestion, ReadingSubtype,
    SpeakingPrompt, SpeakingRubric, SpeakingTask,
    WritingQuestion, WritingSubtype,
)


class ReadingTests(TestCase):
    def test_word_count_is_derived_on_save(self):
        passage = ReadingPassage.objects.create(
            label="R01", title="T", body="one two three four five"
        )
        self.assertEqual(passage.word_count, 5)

    def test_body_outside_the_valid_range_is_invalid(self):
        passage = ReadingPassage(label="R02", title="T", body="too short")
        with self.assertRaises(ValidationError):
            passage.full_clean()

    def test_body_within_range_is_valid(self):
        passage = ReadingPassage(label="R03", title="T", body=" ".join(["word"] * 165))
        passage.full_clean()

    def test_subtypes_include_the_real_bank_shapes(self):
        values = {s.value for s in ReadingSubtype}
        self.assertEqual(
            values,
            {"true_false_ng", "mcq", "completion", "heading_matching", "paragraph_matching"},
        )


class WritingTests(TestCase):
    def test_subtypes_match_the_pattern(self):
        self.assertEqual(
            [s.value for s in WritingSubtype],
            ["grammar", "vocabulary", "jumbled", "fill_blank"],
        )

    def test_question_is_a_standalone_bank_item(self):
        question = WritingQuestion.objects.create(
            subtype=WritingSubtype.GRAMMAR,
            stem="Maria ___ to work by bus.", options=["go", "goes", "going", "gone"],
            answer="B",
        )
        self.assertIsNotNone(question.pk)


class SpeakingTests(TestCase):
    def test_five_fixed_task_slots(self):
        self.assertEqual(len(SpeakingTask.choices), 5)

    def test_prompt_defaults_to_two_marks(self):
        prompt = SpeakingPrompt.objects.create(
            task=SpeakingTask.INTRODUCTION, prompt="What is your name?",
        )
        self.assertEqual(prompt.marks, 2)

    def test_rubric_is_keyed_by_task_uniquely(self):
        SpeakingRubric.objects.create(task=SpeakingTask.OPINION, marks=2, indicators="x")
        with self.assertRaises(Exception):
            SpeakingRubric.objects.create(task=SpeakingTask.OPINION, marks=2, indicators="y")
