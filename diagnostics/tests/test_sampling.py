from collections import Counter

from django.test import TestCase

from diagnostics.constants import REUSE_CAPS, TaskType, VARIANTS
from diagnostics.models import (
    AudioClip, Paper, PaperSpeakingPrompt, PaperWritingQuestion, ReadingPassage,
    SpeakingPrompt, SpeakingTask, WritingQuestion, WritingSubtype,
)
from diagnostics.sampling import (
    SamplingError, sample_speaking_prompts, sample_writing_questions,
)


def make_writing_bank():
    for subtype, count in [
        (WritingSubtype.GRAMMAR, 6), (WritingSubtype.VOCABULARY, 4),
        (WritingSubtype.JUMBLED, 6), (WritingSubtype.FILL_BLANK, 4),
    ]:
        for i in range(count):
            WritingQuestion.objects.create(
                subtype=subtype, stem=f"{subtype}-{i}",
                options=["a", "b", "c", "d"], answer="A",
            )


_clip_counter = [0]


def make_bare_paper(grade, variant, suffix):
    _clip_counter[0] += 1
    base = _clip_counter[0] * 2
    clip1 = AudioClip.objects.create(number=base, task_type=TaskType.MCQ3)
    clip2 = AudioClip.objects.create(number=base + 1, task_type=TaskType.MCQ3)
    return Paper.objects.create(
        grade=grade, variant=variant,
        listening_clip_1=clip1, listening_clip_2=clip2,
        reading_passage=ReadingPassage.objects.create(
            label=f"R{suffix}", title="T", body=" ".join(["word"] * 220)
        ),
    )


class SampleWritingQuestionsTests(TestCase):
    def setUp(self):
        make_writing_bank()

    def test_samples_ten_with_the_required_subtype_mix(self):
        paper = make_bare_paper(9, "A", "01")
        sample_writing_questions(paper)
        slots = list(PaperWritingQuestion.objects.filter(paper=paper).select_related("question"))
        self.assertEqual(len(slots), 10)
        from collections import Counter
        counts = Counter(slot.question.subtype for slot in slots)
        self.assertEqual(
            counts,
            Counter({"grammar": 3, "vocabulary": 2, "jumbled": 3, "fill_blank": 2}),
        )

    def test_positions_are_one_to_ten(self):
        paper = make_bare_paper(9, "A", "01")
        sample_writing_questions(paper)
        positions = sorted(
            PaperWritingQuestion.objects.filter(paper=paper).values_list("position", flat=True)
        )
        self.assertEqual(positions, list(range(1, 11)))

    def test_no_overlap_within_a_grade(self):
        first = make_bare_paper(9, "A", "01")
        sample_writing_questions(first)
        second = make_bare_paper(9, "B", "02")
        sample_writing_questions(second)
        first_ids = set(PaperWritingQuestion.objects.filter(paper=first).values_list("question_id", flat=True))
        second_ids = set(PaperWritingQuestion.objects.filter(paper=second).values_list("question_id", flat=True))
        self.assertEqual(first_ids & second_ids, set())

    def test_overlap_across_grades_is_allowed(self):
        first = make_bare_paper(9, "A", "01")
        sample_writing_questions(first)
        other = make_bare_paper(11, "A", "02")
        sample_writing_questions(other)  # must not raise despite a small pool
        self.assertEqual(
            PaperWritingQuestion.objects.filter(paper=other).count(), 10
        )

    def test_resampling_the_same_paper_replaces_rather_than_duplicates(self):
        paper = make_bare_paper(9, "A", "01")
        sample_writing_questions(paper)
        sample_writing_questions(paper)
        self.assertEqual(PaperWritingQuestion.objects.filter(paper=paper).count(), 10)

    def test_raises_when_pool_is_too_small(self):
        WritingQuestion.objects.filter(subtype=WritingSubtype.VOCABULARY).delete()
        paper = make_bare_paper(9, "A", "01")
        with self.assertRaises(SamplingError):
            sample_writing_questions(paper)


class SampleSpeakingPromptsTests(TestCase):
    def setUp(self):
        from diagnostics.models import SpeakingPrompt, SpeakingTask

        for task in SpeakingTask.values:
            for i in range(3):
                SpeakingPrompt.objects.create(task=task, prompt=f"{task}-{i}")

    def test_samples_one_prompt_per_task_in_order(self):
        from diagnostics.constants import SPEAKING_TASK_ORDER
        from diagnostics.models import PaperSpeakingPrompt
        from diagnostics.sampling import sample_speaking_prompts

        paper = make_bare_paper(9, "A", "01")
        sample_speaking_prompts(paper)
        slots = list(
            PaperSpeakingPrompt.objects.filter(paper=paper)
            .select_related("prompt").order_by("position")
        )
        self.assertEqual(len(slots), 5)
        self.assertEqual([s.position for s in slots], [1, 2, 3, 4, 5])
        self.assertEqual([s.prompt.task for s in slots], list(SPEAKING_TASK_ORDER))

    def test_speaking_prompt_reuse_within_a_grade_stays_within_the_cap(self):
        """Zero overlap is no longer the rule (REUSE_CAPS['speaking_prompt']
        == 2 permits a sibling to reuse a prompt once); what must still hold
        is that no prompt is used more than the cap allows."""
        from diagnostics.models import PaperSpeakingPrompt
        from diagnostics.sampling import sample_speaking_prompts

        first = make_bare_paper(9, "A", "01")
        sample_speaking_prompts(first)
        second = make_bare_paper(9, "B", "02")
        sample_speaking_prompts(second)
        counts = Counter(
            PaperSpeakingPrompt.objects.filter(paper__grade=9)
            .values_list("prompt_id", flat=True)
        )
        self.assertLessEqual(max(counts.values()), REUSE_CAPS["speaking_prompt"])

    def test_raises_when_a_task_pool_is_exhausted(self):
        from diagnostics.models import SpeakingPrompt, SpeakingTask
        from diagnostics.sampling import SamplingError, sample_speaking_prompts

        SpeakingPrompt.objects.filter(task=SpeakingTask.OPINION).delete()
        paper = make_bare_paper(9, "A", "01")
        with self.assertRaises(SamplingError):
            sample_speaking_prompts(paper)


class ReuseCapTests(TestCase):
    """At 16 variants/grade the old zero-sharing rule is unsatisfiable -
    these exercise the cap-based replacement (Design Revision 2, section 2)."""

    def setUp(self):
        self.picture_clip = AudioClip.objects.create(number=1, task_type=TaskType.PICTURE)
        self.rotating_clip = AudioClip.objects.create(number=2, task_type=TaskType.MCQ3)
        self.passage = ReadingPassage.objects.create(
            label="R01", title="T", body=" ".join(["word"] * 220)
        )
        # Full-size pools: 10 speaking prompts per task (50 total), 50
        # writing questions per subtype (200 total) - matches the real bank.
        for task in SpeakingTask.values:
            for i in range(10):
                SpeakingPrompt.objects.create(task=task, prompt=f"{task}-{i}")
        for subtype in WritingSubtype.values:
            for i in range(50):
                WritingQuestion.objects.create(
                    subtype=subtype, stem=f"{subtype}-{i}",
                    options=["a", "b", "c", "d"], answer="A",
                )

    def test_speaking_prompts_may_repeat_up_to_the_cap(self):
        """10 prompts per task against 16 variants means reuse is mandatory.

        The old rule excluded every prompt a grade sibling used, which made a
        16-variant grade unsatisfiable at variant 11. The cap allows each
        prompt twice, giving 20 slots against the 16 needed.
        """
        for variant in VARIANTS:
            paper = Paper.objects.create(
                grade=9, variant=variant,
                listening_clip_1=self.picture_clip,
                listening_clip_2=self.rotating_clip,
                reading_passage=self.passage,
            )
            sample_speaking_prompts(paper)

        counts = Counter(
            PaperSpeakingPrompt.objects.filter(paper__grade=9)
            .values_list("prompt_id", flat=True)
        )
        self.assertLessEqual(max(counts.values()), REUSE_CAPS["speaking_prompt"])
        self.assertEqual(sum(counts.values()), len(VARIANTS) * 5)

    def test_writing_questions_never_repeat_within_a_grade(self):
        """Writing keeps a cap of 1 - its pool of 50 per subtype supports
        genuine zero reuse even at 16 variants (3 x 16 = 48)."""
        for variant in VARIANTS:
            paper = Paper.objects.create(
                grade=9, variant=variant,
                listening_clip_1=self.picture_clip,
                listening_clip_2=self.rotating_clip,
                reading_passage=self.passage,
            )
            sample_writing_questions(paper)

        ids = list(
            PaperWritingQuestion.objects.filter(paper__grade=9)
            .values_list("question_id", flat=True)
        )
        self.assertEqual(len(ids), len(set(ids)), "a writing question repeated")

    def test_raises_when_a_pool_cannot_satisfy_the_cap(self):
        SpeakingPrompt.objects.filter(task="introduction").delete()
        paper = Paper.objects.create(
            grade=9, variant="A",
            listening_clip_1=self.picture_clip,
            listening_clip_2=self.rotating_clip,
            reading_passage=self.passage,
        )
        with self.assertRaises(SamplingError):
            sample_speaking_prompts(paper)
