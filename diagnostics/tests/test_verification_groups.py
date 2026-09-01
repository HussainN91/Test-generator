"""The four things that must be true of every one of the 24 sittings.

These read the database, not the allocator - the same independence
find_reuse_violations has, and for the same reason: a paper written by a bulk
update or a .create() that skipped validation still has to be caught.
"""

from django.core.management import CommandError, call_command
from django.test import TestCase

from diagnostics.constants import GRADES
from diagnostics.models import (
    AudioClip, ListeningQuestionSet, Paper, ReadingPassage, SpeakingPrompt,
)
from diagnostics.navigation import GROUP_NUMBERS, variants_for_group
from diagnostics.verification import find_group_violations


class GroupVerificationTests(TestCase):
    def setUp(self):
        self.clip_a = AudioClip.objects.create(number=1, task_type="picture")
        self.clip_b = AudioClip.objects.create(number=2, task_type="mcq3")
        self.clip_c = AudioClip.objects.create(number=3, task_type="gap_fill")
        self.sets = {
            (clip.number, number): ListeningQuestionSet.objects.create(
                clip=clip, number=number
            )
            for clip in (self.clip_a, self.clip_b, self.clip_c)
            for number in (1, 2)
        }
        self.p1 = ReadingPassage.objects.create(
            label="R01", title="one", body=" ".join(["word"] * 200)
        )
        self.p2 = ReadingPassage.objects.create(
            label="R02", title="two", body=" ".join(["word"] * 200)
        )

    def _paper(self, variant, set_1, set_2, passage):
        return Paper.objects.create(
            grade=9, variant=variant,
            listening_set_1=set_1, listening_set_2=set_2, reading_passage=passage,
        )

    def _good_pair(self):
        a = self._paper("A", self.sets[(1, 1)], self.sets[(2, 1)], self.p1)
        b = self._paper("B", self.sets[(1, 2)], self.sets[(2, 2)], self.p2)
        return a, b

    def test_a_correct_group_reports_nothing(self):
        self._good_pair()
        self.assertEqual(find_group_violations(), [])

    def test_mismatched_audio_is_reported(self):
        self._paper("A", self.sets[(1, 1)], self.sets[(2, 1)], self.p1)
        self._paper("B", self.sets[(1, 2)], self.sets[(3, 2)], self.p2)
        problems = find_group_violations()
        self.assertTrue(any("recording" in p for p in problems), problems)

    def test_identical_question_sets_are_reported(self):
        self._paper("A", self.sets[(1, 1)], self.sets[(2, 1)], self.p1)
        self._paper("B", self.sets[(1, 1)], self.sets[(2, 1)], self.p2)
        problems = find_group_violations()
        self.assertTrue(any("question set" in p for p in problems), problems)

    def test_partial_question_set_overlap_is_reported(self):
        """Same two recordings (so G1 stays silent), but B's first set is
        literally A's row - only the second set correctly differs. A tuple
        comparison of the whole pair would miss this; the check must catch
        any overlap, not just a fully identical pair."""
        self._paper("A", self.sets[(1, 1)], self.sets[(2, 1)], self.p1)
        self._paper("B", self.sets[(1, 1)], self.sets[(2, 2)], self.p2)
        problems = find_group_violations()
        self.assertFalse(any("recording" in p for p in problems), problems)
        self.assertTrue(any("question set" in p for p in problems), problems)

    def test_a_shared_speaking_prompt_is_reported(self):
        a, b = self._good_pair()
        prompt = SpeakingPrompt.objects.create(task="opinion", prompt="shared")
        for paper in (a, b):
            paper.speaking_slots.create(prompt=prompt, position=1)
        problems = find_group_violations()
        self.assertTrue(any("speaking prompt" in p for p in problems), problems)

    def test_a_shared_reading_passage_is_reported(self):
        self._paper("A", self.sets[(1, 1)], self.sets[(2, 1)], self.p1)
        self._paper("B", self.sets[(1, 2)], self.sets[(2, 2)], self.p1)
        problems = find_group_violations()
        self.assertTrue(any("reading passage" in p for p in problems), problems)

    def test_a_half_built_group_is_reported_not_skipped(self):
        """One paper missing is a broken sitting, not a passing one."""
        self._paper("A", self.sets[(1, 1)], self.sets[(2, 1)], self.p1)
        problems = find_group_violations()
        self.assertTrue(any("only 1" in p for p in problems), problems)

    def test_every_problem_names_its_grade_and_group(self):
        self._paper("A", self.sets[(1, 1)], self.sets[(2, 1)], self.p1)
        self._paper("B", self.sets[(1, 1)], self.sets[(3, 1)], self.p1)
        for problem in find_group_violations():
            self.assertIn("Grade 9", problem)
            self.assertIn("group 1", problem)


class GroupVerificationOnTheRealBankTests(TestCase):
    """The end-to-end assertion this whole plan exists to make true."""

    def setUp(self):
        from diagnostics.tests.test_build_papers import seed_content
        seed_content()

    def test_all_twenty_four_groups_pass_after_a_full_build(self):
        call_command("build_papers", "--resample")
        self.assertEqual(find_group_violations(), [])

    def test_check_papers_fails_loudly_on_a_group_violation(self):
        call_command("build_papers", "--resample")
        first = Paper.objects.get(grade=9, variant="A")
        second = Paper.objects.get(grade=9, variant="B")
        second.listening_set_1 = first.listening_set_1
        second.save(update_fields=["listening_set_1"])
        with self.assertRaisesMessage(CommandError, "question set"):
            call_command("check_papers")
