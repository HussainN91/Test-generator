from django.core.exceptions import ValidationError
from django.test import TestCase

from diagnostics.constants import TaskType
from diagnostics.models import (
    AudioClip, ListeningQuestionSet, Paper, PaperSpeakingPrompt, PaperWritingQuestion,
    ReadingPassage, SpeakingPrompt, SpeakingTask, WritingQuestion, WritingSubtype,
)


def make_writing_questions(n, suffix):
    return [
        WritingQuestion.objects.create(
            subtype=WritingSubtype.GRAMMAR, stem=f"stem-{suffix}-{i}",
            options=["a", "b", "c", "d"], answer="A",
        )
        for i in range(n)
    ]


def make_speaking_prompts(suffix):
    return [
        SpeakingPrompt.objects.create(task=task, prompt=f"prompt-{suffix}-{task}")
        for task in SpeakingTask.values
    ]


def make_paper(grade, variant, set_a, set_b, suffix, writing_questions=None, speaking_prompts=None):
    paper = Paper.objects.create(
        grade=grade,
        variant=variant,
        listening_set_1=set_a,
        listening_set_2=set_b,
        reading_passage=ReadingPassage.objects.create(
            label=f"R{suffix}", title="T", body=" ".join(["word"] * 220)
        ),
    )
    for position, question in enumerate(writing_questions or [], start=1):
        PaperWritingQuestion.objects.create(paper=paper, question=question, position=position)
    for position, prompt in enumerate(speaking_prompts or [], start=1):
        PaperSpeakingPrompt.objects.create(paper=paper, prompt=prompt, position=position)
    return paper


class PaperReuseCapTests(TestCase):
    def setUp(self):
        self.clips = {
            n: AudioClip.objects.create(number=n, task_type=TaskType.MCQ3)
            for n in range(1, 9)
        }
        self.sets = {
            n: ListeningQuestionSet.objects.create(clip=clip, number=1)
            for n, clip in self.clips.items()
        }

    def test_valid_paper_saves(self):
        paper = make_paper(9, "A", self.sets[1], self.sets[2], "01")
        paper.full_clean()
        self.assertEqual(Paper.objects.count(), 1)

    def test_a_paper_cannot_use_the_same_clip_twice(self):
        paper = Paper(
            grade=9, variant="A",
            listening_set_1=self.sets[1], listening_set_2=self.sets[1],
            reading_passage=ReadingPassage.objects.create(
                label="R01", title="T", body=" ".join(["word"] * 220)
            ),
        )
        with self.assertRaises(ValidationError) as ctx:
            paper.full_clean()
        self.assertIn("twice", str(ctx.exception))

    def test_rotating_clip_reuse_up_to_the_cap_is_allowed(self):
        """Rotating (non-picture) clips carry REUSE_CAPS['rotating_clip'] ==
        2: a second variant in the same grade may reuse one without raising.
        Clips 2, 3, 4, 6 are all outside PICTURE_CLIPS (1, 5, 9, 13, 15)."""
        make_paper(9, "A", self.sets[2], self.sets[3], "01")
        second = Paper(
            grade=9, variant="B",
            listening_set_1=self.sets[2], listening_set_2=self.sets[4],
            reading_passage=ReadingPassage.objects.create(
                label="R02", title="T", body=" ".join(["word"] * 220)
            ),
        )
        second.full_clean()  # second use of clip 2 - still within the cap

    def test_rotating_clip_reuse_beyond_the_cap_is_rejected(self):
        make_paper(9, "A", self.sets[2], self.sets[3], "01")
        make_paper(9, "B", self.sets[2], self.sets[4], "02")
        third = Paper(
            grade=9, variant="C",
            listening_set_1=self.sets[2], listening_set_2=self.sets[6],
            reading_passage=ReadingPassage.objects.create(
                label="R03", title="T", body=" ".join(["word"] * 220)
            ),
        )
        with self.assertRaises(ValidationError) as ctx:
            third.full_clean()
        self.assertIn("Grade 9", str(ctx.exception))

    def test_picture_clip_reuse_up_to_the_cap_is_allowed(self):
        """Picture clips carry REUSE_CAPS['picture_clip'] == 4 - only five
        exist against sixteen variants. Clip 1 is a picture clip by number
        (PICTURE_CLIPS) regardless of the task_type given in setUp."""
        picture = self.sets[1]
        for variant, second in zip("ABC", (self.sets[2], self.sets[3], self.sets[4])):
            make_paper(9, variant, picture, second, variant)
        fourth = Paper(
            grade=9, variant="D",
            listening_set_1=picture, listening_set_2=self.sets[6],
            reading_passage=ReadingPassage.objects.create(
                label="R04", title="T", body=" ".join(["word"] * 220)
            ),
        )
        fourth.full_clean()  # fourth use of clip 1 - still within the cap of 4

    def test_picture_clip_reuse_beyond_the_cap_is_rejected(self):
        picture = self.sets[1]
        for variant, second in zip(
            "ABCD", (self.sets[2], self.sets[3], self.sets[4], self.sets[6])
        ):
            make_paper(9, variant, picture, second, variant)
        fifth = Paper(
            grade=9, variant="E",
            listening_set_1=picture, listening_set_2=self.sets[7],
            reading_passage=ReadingPassage.objects.create(
                label="R05", title="T", body=" ".join(["word"] * 220)
            ),
        )
        with self.assertRaises(ValidationError) as ctx:
            fifth.full_clean()
        self.assertIn("Grade 9", str(ctx.exception))

    def test_clip_reuse_across_grades_is_allowed(self):
        make_paper(9, "A", self.sets[1], self.sets[2], "01")
        other = Paper(
            grade=11, variant="C",
            listening_set_1=self.sets[2], listening_set_2=self.sets[3],
            reading_passage=ReadingPassage.objects.create(
                label="R02", title="T", body=" ".join(["word"] * 220)
            ),
        )
        other.full_clean()
        other.save()
        self.assertEqual(Paper.objects.count(), 2)

    def test_reading_passage_reuse_up_to_the_cap_is_allowed(self):
        """REUSE_CAPS['reading_passage'] == 2: a second variant in the same
        grade may reuse a passage without raising."""
        first = make_paper(9, "A", self.sets[2], self.sets[3], "01")
        second = Paper(
            grade=9, variant="B",
            listening_set_1=self.sets[4], listening_set_2=self.sets[6],
            reading_passage=first.reading_passage,
        )
        second.full_clean()  # second use of the passage - still within the cap

    def test_reading_passage_reuse_beyond_the_cap_is_rejected(self):
        first = make_paper(9, "A", self.sets[2], self.sets[3], "01")
        Paper.objects.create(
            grade=9, variant="B",
            listening_set_1=self.sets[4], listening_set_2=self.sets[6],
            reading_passage=first.reading_passage,
        )
        third = Paper(
            grade=9, variant="C",
            listening_set_1=self.sets[7], listening_set_2=self.sets[8],
            reading_passage=first.reading_passage,
        )
        with self.assertRaises(ValidationError) as ctx:
            third.full_clean()
        self.assertIn("Grade 9", str(ctx.exception))

    def test_shared_writing_question_within_a_grade_is_rejected(self):
        """REUSE_CAPS['writing_question'] == 1 - the pool of 50 per subtype
        supports genuine zero reuse, so this cap boundary is unchanged from
        the original rule: a second use in the same grade already raises."""
        questions = make_writing_questions(2, "shared")
        make_paper(9, "A", self.sets[1], self.sets[2], "01", writing_questions=questions[:1])
        clash = make_paper(9, "B", self.sets[3], self.sets[4], "02")
        PaperWritingQuestion.objects.create(paper=clash, question=questions[0], position=1)
        with self.assertRaises(ValidationError) as ctx:
            clash.full_clean()
        self.assertIn("Grade 9", str(ctx.exception))

    def test_shared_writing_question_across_grades_is_allowed(self):
        questions = make_writing_questions(1, "cross-grade")
        make_paper(9, "A", self.sets[1], self.sets[2], "01", writing_questions=questions)
        other = make_paper(11, "A", self.sets[3], self.sets[4], "02")
        PaperWritingQuestion.objects.create(paper=other, question=questions[0], position=1)
        other.full_clean()  # must not raise

    def test_speaking_prompt_reuse_up_to_the_cap_is_allowed(self):
        """REUSE_CAPS['speaking_prompt'] == 2: a second variant in the same
        grade may reuse a prompt without raising."""
        prompts = make_speaking_prompts("shared")
        make_paper(9, "A", self.sets[1], self.sets[2], "01", speaking_prompts=prompts)
        second = make_paper(9, "B", self.sets[3], self.sets[4], "02")
        PaperSpeakingPrompt.objects.create(paper=second, prompt=prompts[0], position=1)
        second.full_clean()  # second use of the prompt - still within the cap

    def test_speaking_prompt_reuse_beyond_the_cap_is_rejected(self):
        prompts = make_speaking_prompts("shared")
        make_paper(9, "A", self.sets[1], self.sets[2], "01", speaking_prompts=prompts)
        second = make_paper(9, "B", self.sets[3], self.sets[4], "02")
        PaperSpeakingPrompt.objects.create(paper=second, prompt=prompts[0], position=1)
        third = make_paper(9, "C", self.sets[6], self.sets[7], "03")
        PaperSpeakingPrompt.objects.create(paper=third, prompt=prompts[0], position=1)
        with self.assertRaises(ValidationError) as ctx:
            third.full_clean()
        self.assertIn("Grade 9", str(ctx.exception))

    def test_str_is_the_paper_code(self):
        paper = make_paper(10, "C", self.sets[1], self.sets[2], "01")
        self.assertEqual(str(paper), "G10-C")


class PaperListeningSetTests(TestCase):
    """A paper points at two question sets. The old listening_clip_1/2 names
    survive as read-only properties, because a dozen call sites, two admin
    columns and the audio download view all only ever want the recording."""

    def setUp(self):
        self.picture = AudioClip.objects.create(number=1, task_type="picture")
        self.rotating = AudioClip.objects.create(number=2, task_type="mcq3")
        self.set_one = ListeningQuestionSet.objects.create(clip=self.picture, number=1)
        self.set_two = ListeningQuestionSet.objects.create(clip=self.rotating, number=2)
        self.passage = ReadingPassage.objects.create(
            label="R01", title="t", body=" ".join(["word"] * 200)
        )
        self.paper = Paper.objects.create(
            grade=9, variant="A",
            listening_set_1=self.set_one,
            listening_set_2=self.set_two,
            reading_passage=self.passage,
        )

    def test_listening_clip_properties_reach_through_the_set(self):
        self.assertEqual(self.paper.listening_clip_1, self.picture)
        self.assertEqual(self.paper.listening_clip_2, self.rotating)

    def test_shared_components_still_counts_the_clips_not_the_sets(self):
        keys = dict(self.paper.shared_components())
        self.assertIn("picture_clip", keys)
        self.assertIn("rotating_clip", keys)
        self.assertEqual(keys["picture_clip"], self.picture.pk)

    def test_two_sets_of_the_same_clip_is_rejected(self):
        other_set = ListeningQuestionSet.objects.create(clip=self.picture, number=2)
        self.paper.listening_set_2 = other_set
        with self.assertRaises(ValidationError):
            self.paper.clean()
