"""Which grades and groups sit a given question set.

Derived from stored Paper rows rather than from allocation.py, for the same
reason verification.py re-derives its answers: a paper written by a bulk
update has to be described as it actually is, not as the allocator would
have made it.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from diagnostics.constants import CLIP_TASK_TYPES, TaskType
from diagnostics.listening_bank import set_usage, usage_title
from diagnostics.models import AudioClip, ListeningQuestion, ListeningQuestionSet, Paper
from diagnostics.tests.test_build_papers import seed_content


def seed_listening_questions():
    """Real question content on top of every set seed_content creates.

    seed_content deliberately leaves all 40 ListeningQuestionSets (both
    numbers, for each of the 20 clips) empty of questions - see its own
    docstring. ListeningBankViewTests needs real content to exercise (200
    questions total), so this gives every set 5 questions, positions 1-5.

    Mirrors how test_rendering.py's seed_questions_and_rubrics distinguishes
    MCQ-shaped task types from free-text ones via CLIP_TASK_TYPES, but
    covers set 2 as well as set 1 since the bank page renders both.
    """
    for clip in AudioClip.objects.all():
        task = CLIP_TASK_TYPES[clip.number]
        if task == TaskType.MCQ3:
            options, answer = ["one", "two", "three"], "A"
        elif task == TaskType.TRUE_FALSE:
            options, answer = ["true", "false"], "A"
        else:  # PICTURE, GAP_FILL: free-text answers, no fixed options
            options, answer = [], "word"
        for question_set in clip.question_sets.all():
            for position in range(1, 6):
                ListeningQuestion.objects.create(
                    question_set=question_set, position=position,
                    stem=f"Clip {clip.number} set {question_set.number}, question {position}",
                    options=options, answer=answer,
                )


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
        self.assertEqual(balance["mcq3"], {"letters": {"A": 1, "B": 3, "C": 1}})

    def test_a_task_type_with_no_questions_is_absent_not_zeroed(self):
        from diagnostics.listening_bank import key_balance
        from diagnostics.models import ListeningQuestion

        self.assertEqual(key_balance(ListeningQuestion.objects.none()), {})

    def test_gap_fill_is_counted_not_tallied(self):
        """Free-text answers have no letter to over-pick.

        Tallying them printed one row per distinct answer - forty entries
        each reading "1" - which said nothing about guessability and buried
        the three rows that do.
        """
        from diagnostics.listening_bank import key_balance
        from diagnostics.models import AudioClip, ListeningQuestion

        clip = AudioClip.objects.get(number=3)   # gap_fill
        question_set = clip.question_sets.get(number=1)
        for position, answer in enumerate(
            ["bakery", "family", "the lake", "£185", "sunset"], start=1
        ):
            ListeningQuestion.objects.create(
                question_set=question_set, position=position,
                stem=f"q{position}", options=[], answer=answer,
            )
        balance = key_balance(ListeningQuestion.objects.filter(
            question_set=question_set
        ))
        self.assertEqual(balance["gap_fill"], {"free_text": 5})

    def test_rows_follow_task_type_declaration_order(self):
        """picture, mcq3, gap_fill, true_false - not query arrival order.

        The panel is read top to bottom every time; a stable order means a
        reviewer learns where to look instead of hunting for the row.
        """
        from diagnostics.constants import TaskType
        from diagnostics.listening_bank import key_balance
        from diagnostics.models import AudioClip, ListeningQuestion

        # Created deliberately in reverse, so arrival order cannot be what
        # the assertion below is passing on.
        for number in (20, 3, 2, 1):   # true_false, gap_fill, mcq3, picture
            question_set = AudioClip.objects.get(
                number=number
            ).question_sets.get(number=1)
            ListeningQuestion.objects.create(
                question_set=question_set, position=1, stem="q",
                options=[], answer="A",
            )
        balance = key_balance(ListeningQuestion.objects.all())
        self.assertEqual(
            list(balance), [task.value for task in TaskType]
        )


class TranscriptBoldTests(TestCase):
    """The transcripts are imported as markdown; the page must not show it raw."""

    def test_bold_markers_become_real_bold(self):
        from diagnostics.templatetags.listening_extras import transcript_bold

        self.assertEqual(
            transcript_bold("**1. Which dish?**\nInterviewer: So you won."),
            "<strong>1. Which dish?</strong>\nInterviewer: So you won.",
        )

    def test_transcript_markup_is_escaped_before_substitution(self):
        """A transcript is content, not markup - it must not inject tags."""
        from diagnostics.templatetags.listening_extras import transcript_bold

        rendered = transcript_bold("<script>alert(1)</script> **bold**")
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("<strong>bold</strong>", rendered)

    def test_an_unmatched_marker_stays_literal(self):
        """Non-greedy and single-line, so a stray ** cannot swallow the rest."""
        from diagnostics.templatetags.listening_extras import transcript_bold

        self.assertEqual(
            transcript_bold("**heading**\nstray ** here\nplain"),
            "<strong>heading</strong>\nstray ** here\nplain",
        )

    def test_empty_transcript_renders_nothing(self):
        from diagnostics.templatetags.listening_extras import transcript_bold

        self.assertEqual(transcript_bold(""), "")
        self.assertEqual(transcript_bold(None), "")


class ListeningBankViewTests(TestCase):
    def setUp(self):
        seed_content()
        seed_listening_questions()
        call_command("build_papers", "--resample", stdout=StringIO())
        User = get_user_model()
        self.staff = User.objects.create_user(
            "boss", password="pw", is_staff=True
        )
        self.teacher = User.objects.create_user("teacher", password="pw")
        self.url = reverse("diagnostics:listening_bank")

    def test_staff_can_open_it(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_a_non_staff_user_gets_404_not_403(self):
        """404 rather than 403, matching _get_visible_paper: the page does
        not advertise its own existence to someone who may not have it."""
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_signed_out_users_are_sent_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_unfiltered_shows_every_set(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["entries"]), 40)

    def test_filtering_by_grade_narrows_the_list(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url, {"grade": 9})
        entries = response.context["entries"]
        self.assertLess(len(entries), 40)
        for entry in entries:
            self.assertTrue(
                any(grade == 9 for grade, _ in entry["pairs"]),
                entry["title"],
            )

    def test_an_unknown_grade_falls_back_to_all(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url, {"grade": "banana"})
        self.assertEqual(len(response.context["entries"]), 40)
        self.assertIsNone(response.context["selected_grade"])

    def test_entries_are_ordered_by_clip_then_set(self):
        self.client.force_login(self.staff)
        entries = self.client.get(self.url).context["entries"]
        keys = [(e["clip"].number, e["question_set"].number) for e in entries]
        self.assertEqual(keys, sorted(keys))

    def test_every_question_is_present(self):
        self.client.force_login(self.staff)
        entries = self.client.get(self.url).context["entries"]
        self.assertEqual(sum(len(e["questions"]) for e in entries), 200)

    def test_the_nav_link_shows_for_staff_only(self):
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(self.url), "Listening bank")

        self.client.force_login(self.teacher)
        index = self.client.get(reverse("diagnostics:paper_index"))
        self.assertNotContains(index, "Listening bank")

    def test_each_clip_is_anchored_once_for_the_index(self):
        """Both sets of a clip would otherwise claim the same id.

        The index lists clips, so the anchor belongs on a clip's first set
        only - a duplicate id makes the second one unreachable and is
        invalid HTML besides.
        """
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        anchors = [e["anchor"] for e in response.context["entries"] if e["anchor"]]
        self.assertEqual(anchors, [f"clip-{n}" for n in range(1, 21)])
        self.assertEqual(len(anchors), len(set(anchors)))
        self.assertEqual(response.context["clip_numbers"], list(range(1, 21)))

    def test_the_index_only_lists_clips_the_filter_left(self):
        """A jump link to a clip that is not on the page goes nowhere."""
        self.client.force_login(self.staff)
        response = self.client.get(self.url, {"grade": 9})
        shown = {e["clip"].number for e in response.context["entries"]}
        self.assertEqual(response.context["clip_numbers"], sorted(shown))

    def test_gap_fill_shows_a_count_rather_than_every_answer(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(
            response.context["balance"]["gap_fill"], {"free_text": 50}
        )
        self.assertContains(response, "50 free-text answers")
