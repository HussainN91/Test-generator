"""Wording is a correctness concern here, not decoration.

The spine spec (§7.0) forbids model vocabulary reaching a user, and requires
deadlines to be expressed relatively. These tests pin both, because wording is
exactly the kind of thing that silently regresses when someone edits a template
in a hurry.
"""

from datetime import date, timedelta

from django.test import TestCase

from step import constants, presentation
from step.models import Educator, Obligation, ObligationType, Region

TODAY = date(2026, 5, 20)


class DuePhraseTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY,
        )

    def make(self, due, status=constants.STATUS_NOT_STARTED):
        return Obligation.objects.create(
            type=self.type, educator=self.educator, period_kind=constants.PERIOD_MONTH,
            period_start=date(2026, 5, 1), due_date=due, status=status,
        )

    def test_due_today(self):
        self.assertEqual(presentation.due_phrase(self.make(TODAY), TODAY), "Due today")

    def test_due_tomorrow_is_a_word_not_a_count(self):
        due = TODAY + timedelta(days=1)
        self.assertEqual(presentation.due_phrase(self.make(due), TODAY), "Due tomorrow")

    def test_due_in_several_days(self):
        due = TODAY + timedelta(days=4)
        self.assertEqual(presentation.due_phrase(self.make(due), TODAY), "Due in 4 days")

    def test_one_day_late_is_singular(self):
        due = TODAY - timedelta(days=1)
        self.assertEqual(presentation.due_phrase(self.make(due), TODAY), "1 day late")

    def test_several_days_late_is_plural(self):
        due = TODAY - timedelta(days=5)
        self.assertEqual(presentation.due_phrase(self.make(due), TODAY), "5 days late")

    def test_accepted_reports_completion_not_a_deadline(self):
        obligation = self.make(TODAY - timedelta(days=9), status=constants.STATUS_ACCEPTED)
        self.assertEqual(presentation.due_phrase(obligation, TODAY), "Accepted")

    def test_submitted_says_the_ball_is_elsewhere(self):
        obligation = self.make(TODAY, status=constants.STATUS_SUBMITTED)
        self.assertIn("waiting", presentation.due_phrase(obligation, TODAY))

    def test_no_phrase_ever_contains_model_vocabulary(self):
        """The single rule that matters: never show the user the schema."""
        banned = ["not_started", "under_review", "evidence_spec", "obligation_type", "revision"]
        for status, _ in constants.OBLIGATION_STATUS_CHOICES:
            obligation = self.make(TODAY + timedelta(days=2), status=status)
            phrase = presentation.due_phrase(obligation, TODAY)
            label = presentation.decorate(obligation, TODAY)["urgency_label"]
            for term in banned:
                self.assertNotIn(term, phrase.lower())
                self.assertNotIn(term, label.lower())
            obligation.delete()


class DecorateTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY,
        )

    def make(self, due, status=constants.STATUS_NOT_STARTED):
        return Obligation.objects.create(
            type=self.type, educator=self.educator, period_kind=constants.PERIOD_MONTH,
            period_start=date(2026, 5, 1), due_date=due, status=status,
        )

    def test_a_returned_item_reads_as_needing_correction(self):
        item = presentation.decorate(self.make(TODAY, constants.STATUS_RETURNED), TODAY)
        self.assertEqual(item["urgency_label"], "Needs correction")
        self.assertTrue(item["needs_action"])

    def test_accepted_needs_no_action(self):
        item = presentation.decorate(self.make(TODAY, constants.STATUS_ACCEPTED), TODAY)
        self.assertEqual(item["urgency_label"], "Accepted")
        self.assertFalse(item["needs_action"])

    def test_submitted_needs_no_action_from_the_teacher(self):
        item = presentation.decorate(self.make(TODAY, constants.STATUS_SUBMITTED), TODAY)
        self.assertEqual(item["urgency_label"], "With reviewer")
        self.assertFalse(item["needs_action"])

    def test_a_late_item_reads_as_late(self):
        item = presentation.decorate(self.make(TODAY - timedelta(days=3)), TODAY)
        self.assertEqual(item["urgency_label"], "Late")
        self.assertEqual(item["urgency"], constants.URGENCY_OVERDUE)


class EvidenceInstructionTests(TestCase):
    def instruction_for(self, spec, minimum=1):
        obligation_type = ObligationType.objects.create(
            name_template="X", category=constants.CATEGORY_OTHER,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=spec, min_count=minimum,
        )
        return presentation.evidence_instruction(obligation_type)

    def test_none_says_so_plainly(self):
        self.assertIn("do not need", self.instruction_for(constants.EVIDENCE_NONE))

    def test_single_file_is_not_pluralised_with_brackets(self):
        text = self.instruction_for(constants.EVIDENCE_FILE)
        self.assertNotIn("(s)", text)
        self.assertIn("1 file", text)

    def test_multiple_files_pluralise_properly(self):
        self.assertIn("2 files", self.instruction_for(constants.EVIDENCE_FILE, 2))

    def test_both_says_both_are_needed(self):
        self.assertIn("Both", self.instruction_for(constants.EVIDENCE_BOTH))


class InitialsTests(TestCase):
    def test_two_names_give_two_letters(self):
        self.assertEqual(presentation.initials("Maria Santos"), "MS")

    def test_one_name_gives_two_letters(self):
        self.assertEqual(presentation.initials("Maria"), "MA")

    def test_three_names_use_first_and_last(self):
        self.assertEqual(presentation.initials("Maria de la Cruz"), "MC")

    def test_empty_falls_back_rather_than_crashing(self):
        self.assertEqual(presentation.initials(""), "?")
        self.assertEqual(presentation.initials(None), "?")
