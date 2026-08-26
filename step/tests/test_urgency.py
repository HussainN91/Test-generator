"""Urgency badges and stat tiles are computed, never stored (spec §5.3).

Storing them means a nightly job has to flip them, and the day it fails the
dashboard lies without anyone noticing.
"""

from datetime import date, timedelta

from django.test import TestCase

from step import constants, urgency
from step.models import Educator, Obligation, ObligationType, Region

TODAY = date(2026, 5, 20)


class UrgencyTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY,
        )

    def make(self, due, status=constants.STATUS_NOT_STARTED, period=date(2026, 5, 1)):
        return Obligation.objects.create(
            type=self.type, educator=self.educator, period_kind=constants.PERIOD_MONTH,
            period_start=period, due_date=due, status=status,
        )

    def test_an_accepted_obligation_is_done_regardless_of_date(self):
        obligation = self.make(TODAY - timedelta(days=30), status=constants.STATUS_ACCEPTED)
        self.assertEqual(urgency.urgency_of(obligation, TODAY), constants.URGENCY_DONE)

    def test_a_submitted_obligation_awaiting_review_is_done_for_the_teacher(self):
        obligation = self.make(TODAY - timedelta(days=1), status=constants.STATUS_SUBMITTED)
        self.assertEqual(urgency.urgency_of(obligation, TODAY), constants.URGENCY_DONE)

    def test_a_returned_obligation_past_its_date_is_overdue_again(self):
        obligation = self.make(TODAY - timedelta(days=1), status=constants.STATUS_RETURNED)
        self.assertEqual(urgency.urgency_of(obligation, TODAY), constants.URGENCY_OVERDUE)

    def test_past_due_is_overdue(self):
        self.assertEqual(urgency.urgency_of(self.make(TODAY - timedelta(days=1)), TODAY), constants.URGENCY_OVERDUE)

    def test_due_today(self):
        self.assertEqual(urgency.urgency_of(self.make(TODAY), TODAY), constants.URGENCY_DUE_TODAY)

    def test_within_the_window_is_due_soon(self):
        self.assertEqual(urgency.urgency_of(self.make(TODAY + timedelta(days=3)), TODAY), constants.URGENCY_DUE_SOON)

    def test_beyond_the_window_is_merely_scheduled(self):
        far = TODAY + timedelta(days=constants.DUE_SOON_DAYS + 1)
        self.assertEqual(urgency.urgency_of(self.make(far), TODAY), constants.URGENCY_SCHEDULED)


class TeacherTilesTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY,
        )

    def make(self, period, due, status=constants.STATUS_NOT_STARTED):
        return Obligation.objects.create(
            type=self.type, educator=self.educator, period_kind=constants.PERIOD_MONTH,
            period_start=period, due_date=due, status=status,
        )

    def test_tiles_count_active_due_this_month_completed_and_progress(self):
        self.make(date(2026, 5, 1), date(2026, 5, 27))
        self.make(date(2026, 4, 1), date(2026, 4, 27), status=constants.STATUS_ACCEPTED)
        self.make(date(2026, 6, 1), date(2026, 6, 27))

        tiles = urgency.teacher_tiles(self.educator, today=TODAY)
        self.assertEqual(tiles["active"], 2)
        self.assertEqual(tiles["due_this_month"], 1)
        self.assertEqual(tiles["completed"], 1)
        self.assertEqual(tiles["progress_percent"], 33)

    def test_progress_is_zero_with_no_obligations_rather_than_dividing_by_zero(self):
        tiles = urgency.teacher_tiles(self.educator, today=TODAY)
        self.assertEqual(tiles["progress_percent"], 0)
        self.assertEqual(tiles["active"], 0)

    def test_next_action_is_the_most_urgent_outstanding_obligation(self):
        self.make(date(2026, 6, 1), date(2026, 6, 27))
        soonest = self.make(date(2026, 5, 1), date(2026, 5, 22))
        self.assertEqual(urgency.next_action(self.educator, today=TODAY), soonest)

    def test_next_action_is_none_when_everything_is_settled(self):
        self.make(date(2026, 5, 1), date(2026, 5, 22), status=constants.STATUS_ACCEPTED)
        self.assertIsNone(urgency.next_action(self.educator, today=TODAY))
