"""The metric definitions in spec §6.1 are normative — these tests are what
makes them so. In particular "Pending" and "Not started" are REPORTING
categories derived from the due date, and are not the stored `not_started`
status.
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from step import analytics, constants, workflow
from step.models import Educator, Obligation, ObligationType, Region

PERIOD = date(2026, 5, 1)


class AnalyticsTests(TestCase):
    def setUp(self):
        self.tashkent = Region.objects.create(name="Tashkent City", code="tashkent-city", is_city=True)
        self.samarkand = Region.objects.create(name="Samarkand", code="samarkand")
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
            requires_review=True,
        )
        self.user = get_user_model().objects.create_user("maria", password="x")

    def make(self, region, due=date(2026, 5, 27)):
        educator = Educator.objects.create(
            full_name=f"Teacher {Educator.objects.count() + 1}", region=region
        )
        return Obligation.objects.create(
            type=self.type, educator=educator, period_kind=constants.PERIOD_MONTH,
            period_start=PERIOD, due_date=due,
        )

    def test_teachers_by_region_counts_active_educators(self):
        self.make(self.tashkent)
        self.make(self.tashkent)
        self.make(self.samarkand)
        rows = analytics.teachers_by_region()
        by_name = {r["region"]: r["count"] for r in rows}
        self.assertEqual(by_name["Tashkent City"], 2)
        self.assertEqual(by_name["Samarkand"], 1)

    def test_teachers_by_region_is_sorted_largest_first(self):
        self.make(self.samarkand)
        self.make(self.tashkent)
        self.make(self.tashkent)
        self.assertEqual(analytics.teachers_by_region()[0]["region"], "Tashkent City")

    def test_submission_status_splits_submitted_pending_and_not_started(self):
        submitted = self.make(self.tashkent)
        workflow.submit(submitted, user=self.user, evidence=[])
        self.make(self.tashkent, due=date(2026, 5, 27))   # pending: due later
        self.make(self.samarkand, due=date(2026, 5, 1))   # not started: due passed

        status = analytics.submission_status(PERIOD, today=date(2026, 5, 20))
        self.assertEqual(status["total"], 3)
        self.assertEqual(status["submitted"], 1)
        self.assertEqual(status["pending"], 1)
        self.assertEqual(status["not_started"], 1)

    def test_submission_status_percentages_are_rounded_and_sum_sensibly(self):
        for _ in range(4):
            self.make(self.tashkent)
        workflow.submit(Obligation.objects.first(), user=self.user, evidence=[])
        status = analytics.submission_status(PERIOD, today=date(2026, 5, 20))
        self.assertEqual(status["submitted_percent"], 25.0)

    def test_submission_status_with_no_obligations_does_not_divide_by_zero(self):
        status = analytics.submission_status(PERIOD, today=date(2026, 5, 20))
        self.assertEqual(status["total"], 0)
        self.assertEqual(status["submitted_percent"], 0.0)

    def test_rating_distribution_is_flagged_self_reported(self):
        obligation = self.make(self.tashkent)
        workflow.submit(
            obligation, user=self.user, evidence=[], evaluation={"director_rating": 5}
        )
        result = analytics.rating_distribution(PERIOD)
        self.assertTrue(result["self_reported"])
        self.assertEqual(result["counts"][5], 1)
        self.assertEqual(result["counts"][3], 0)

    def test_outcome_distribution_is_flagged_self_reported(self):
        obligation = self.make(self.tashkent)
        workflow.submit(
            obligation, user=self.user, evidence=[],
            evaluation={"outcome": constants.OUTCOME_NEEDS_IMPROVEMENT},
        )
        result = analytics.outcome_distribution(PERIOD)
        self.assertTrue(result["self_reported"])
        self.assertEqual(result["counts"][constants.OUTCOME_NEEDS_IMPROVEMENT], 1)

    def test_timeliness_counts_on_time_and_late_by_the_due_date(self):
        early = self.make(self.tashkent, due=date(2030, 1, 1))
        late = self.make(self.samarkand, due=date(2020, 1, 1))
        workflow.submit(early, user=self.user, evidence=[])
        workflow.submit(late, user=self.user, evidence=[])

        result = analytics.timeliness(PERIOD)
        self.assertEqual(result["on_time"], 1)
        self.assertEqual(result["late"], 1)
        self.assertEqual(result["on_time_percent"], 50.0)

    def test_average_submission_time_is_in_days(self):
        obligation = self.make(self.tashkent)
        workflow.submit(obligation, user=self.user, evidence=[])
        result = analytics.timeliness(PERIOD)
        self.assertGreaterEqual(result["average_submission_days"], 0.0)

    def test_status_by_region_returns_one_row_per_region_with_teachers(self):
        self.make(self.tashkent)
        self.make(self.samarkand)
        rows = analytics.status_by_region(PERIOD, today=date(2026, 5, 20))
        self.assertEqual(len(rows), 2)
        self.assertIn("submitted", rows[0])
        self.assertIn("pending", rows[0])
        self.assertIn("not_started", rows[0])

    def test_submission_trend_is_cumulative_and_never_decreases(self):
        for _ in range(3):
            obligation = self.make(self.tashkent)
            workflow.submit(obligation, user=self.user, evidence=[])
        points = analytics.submission_trend(PERIOD)
        values = [p["cumulative_percent"] for p in points]
        self.assertEqual(values, sorted(values))
        self.assertLessEqual(values[-1], 100.0)

    def test_completeness_rate_counts_filled_evidence_slots(self):
        obligation_type = ObligationType.objects.create(
            name_template="With evidence", category=constants.CATEGORY_OTHER,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_LINK,
        )
        educator = Educator.objects.create(full_name="E", region=self.tashkent)
        obligation = Obligation.objects.create(
            type=obligation_type, educator=educator, period_kind=constants.PERIOD_MONTH,
            period_start=PERIOD, due_date=date(2026, 5, 27),
        )
        workflow.submit(
            obligation, user=self.user,
            evidence=[{"kind": constants.EVIDENCE_LINK_KIND, "url": "https://x.example"}],
        )
        self.assertEqual(analytics.completeness_rate(PERIOD), 100.0)

    def test_completeness_rate_with_no_submissions_is_zero(self):
        self.assertEqual(analytics.completeness_rate(PERIOD), 0.0)
