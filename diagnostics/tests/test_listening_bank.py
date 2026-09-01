"""Which grades and groups sit a given question set.

Derived from stored Paper rows rather than from allocation.py, for the same
reason verification.py re-derives its answers: a paper written by a bulk
update has to be described as it actually is, not as the allocator would
have made it.
"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diagnostics.listening_bank import set_usage, usage_title
from diagnostics.models import ListeningQuestionSet, Paper
from diagnostics.tests.test_build_papers import seed_content


class UsageOnABuiltBankTests(TestCase):
    def setUp(self):
        seed_content()
        call_command("build_papers", "--resample", stdout=StringIO())

    def test_every_set_a_paper_uses_is_reported(self):
        usage = set_usage()
        used = set(
            Paper.objects.values_list("listening_set_1_id", flat=True)
        ) | set(Paper.objects.values_list("listening_set_2_id", flat=True))
        self.assertEqual(set(usage) & used, used)

    def test_a_set_maps_to_grade_and_group_pairs(self):
        usage = set_usage()
        paper = Paper.objects.get(grade=9, variant="A")
        self.assertIn((9, 1), usage[paper.listening_set_1_id])

    def test_both_variants_of_a_group_collapse_to_one_pair(self):
        """A and B are one sitting, so a set both papers use is listed once
        for that group, not twice."""
        usage = set_usage()
        paper = Paper.objects.get(grade=9, variant="A")
        pairs = usage[paper.listening_set_1_id]
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_a_set_no_paper_uses_reports_empty(self):
        orphan = ListeningQuestionSet.objects.exclude(
            pk__in=Paper.objects.values_list("listening_set_1_id", flat=True)
        ).exclude(
            pk__in=Paper.objects.values_list("listening_set_2_id", flat=True)
        ).first()
        if orphan is None:
            self.skipTest("every set is allocated in this bank")
        self.assertEqual(set_usage().get(orphan.pk, []), [])


class UsageTitleTests(TestCase):
    def test_groups_are_listed_per_grade(self):
        title = usage_title([(9, 1), (9, 6), (10, 3), (10, 8), (11, 5)])
        self.assertEqual(
            title,
            "Grade 9 groups 1, 6 · Grade 10 groups 3, 8 · Grade 11 group 5",
        )

    def test_a_single_group_is_singular(self):
        self.assertEqual(usage_title([(9, 2)]), "Grade 9 group 2")

    def test_pairs_are_sorted_regardless_of_input_order(self):
        self.assertEqual(
            usage_title([(11, 5), (9, 6), (9, 1)]),
            "Grade 9 groups 1, 6 · Grade 11 group 5",
        )

    def test_an_unused_set_says_so_rather_than_returning_blank(self):
        """A set with no home is exactly what a reviewer needs to see."""
        self.assertEqual(usage_title([]), "Not currently allocated to any paper")


class KeyBalanceTests(TestCase):
    def setUp(self):
        seed_content()

    def test_counts_answers_per_task_type(self):
        from diagnostics.listening_bank import key_balance
        from diagnostics.models import AudioClip, ListeningQuestion

        clip = AudioClip.objects.get(number=2)   # mcq3
        question_set = clip.question_sets.get(number=1)
        for position, answer in enumerate("ABBBC", start=1):
            ListeningQuestion.objects.create(
                question_set=question_set, position=position,
                stem=f"q{position}", options=["x", "y", "z"], answer=answer,
            )
        balance = key_balance(ListeningQuestion.objects.filter(
            question_set=question_set
        ))
        self.assertEqual(balance["mcq3"], {"A": 1, "B": 3, "C": 1})

    def test_a_task_type_with_no_questions_is_absent_not_zeroed(self):
        from diagnostics.listening_bank import key_balance
        from diagnostics.models import ListeningQuestion

        self.assertEqual(key_balance(ListeningQuestion.objects.none()), {})
