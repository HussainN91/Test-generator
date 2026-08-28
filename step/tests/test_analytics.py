"""The metric definitions in spec §6.1 are normative — these tests are what
makes them so. In particular "Pending" and "Not started" are REPORTING
categories derived from the due date, and are not the stored `not_started`
status.
"""

from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from step import analytics, constants, workflow
from step.models import (
    Activity, Announcement, AnnouncementResponse, Educator, Obligation, ObligationType,
    Region, Session,
)

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


class ActivityByRegionTests(TestCase):
    """fix step plan.md §6 — the cross-vertical regional chart."""

    def setUp(self):
        self.tashkent = Region.objects.create(name="Tashkent City", code="tashkent-city", is_city=True)
        self.samarkand = Region.objects.create(name="Samarkand", code="samarkand")
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
            requires_review=True,
        )
        self.user = get_user_model().objects.create_user("director", password="x")

    def _educator(self, region, **kwargs):
        return Educator.objects.create(
            full_name=f"Teacher {Educator.objects.count() + 1}", region=region, **kwargs
        )

    def _obligation(self, educator, due=date(2026, 5, 27)):
        return Obligation.objects.create(
            type=self.type, educator=educator, period_kind=constants.PERIOD_MONTH,
            period_start=PERIOD, due_date=due,
        )

    def _publish(self, title, when):
        announcement = Announcement.objects.create(title=title, body="Details.")
        Announcement.objects.filter(pk=announcement.pk).update(published_at=when)
        announcement.refresh_from_db()
        return announcement

    def _session(self, educator, kind, held_on):
        activity = Activity.objects.create(
            educator=educator, kind=kind, title="Group", started_on=date(2026, 4, 1),
        )
        return Session.objects.create(
            activity=activity, scheduled_for=held_on, held_on=held_on,
            status=constants.SESSION_STATUS_HELD,
        )

    def test_counts_all_four_verticals_for_one_region(self):
        educator = self._educator(self.tashkent)
        workflow.submit(self._obligation(educator), user=self.user, evidence=[])

        announcement = self._publish("CPD session", timezone.make_aware(datetime(2026, 5, 10)))
        AnnouncementResponse.objects.create(announcement=announcement, educator=educator, attending=True)

        self._session(educator, constants.ACTIVITY_KIND_ECA, date(2026, 5, 8))
        self._session(educator, constants.ACTIVITY_KIND_CPD_OFFLINE, date(2026, 5, 15))

        rows = analytics.activity_by_region(PERIOD)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["region"], "Tashkent City")
        self.assertEqual(row["monthly_reports"], 1)
        self.assertEqual(row["cpd_online_responses"], 1)
        self.assertEqual(row["eca_sessions"], 1)
        self.assertEqual(row["cpd_offline_sessions"], 1)

    def test_one_row_per_region_with_eligible_educators(self):
        self._educator(self.tashkent)
        self._educator(self.samarkand)
        rows = analytics.activity_by_region(PERIOD)
        self.assertEqual({r["region"] for r in rows}, {"Tashkent City", "Samarkand"})

    def test_inactive_educators_are_excluded_from_every_column(self):
        inactive = self._educator(self.tashkent, is_active=False)
        workflow.submit(self._obligation(inactive), user=self.user, evidence=[])
        announcement = self._publish("CPD session", timezone.make_aware(datetime(2026, 5, 10)))
        AnnouncementResponse.objects.create(announcement=announcement, educator=inactive, attending=True)
        self._session(inactive, constants.ACTIVITY_KIND_ECA, date(2026, 5, 8))

        rows = analytics.activity_by_region(PERIOD)
        self.assertEqual(rows, [])

    def test_response_scoped_by_publish_date_not_response_date(self):
        """A late RSVP does not move the announcement into a different
        period — `responded_at` rewrites on every save, `published_at`
        does not (test-generator-2a's ruling on the §6 gap)."""
        educator = self._educator(self.tashkent)
        announcement = self._publish("July session", timezone.make_aware(datetime(2026, 7, 5)))
        response = AnnouncementResponse.objects.create(
            announcement=announcement, educator=educator, attending=True
        )
        response.attending = False
        response.save(update_fields=["attending"])  # bumps responded_at into a later month

        self.assertEqual(analytics.activity_by_region(PERIOD)[0]["cpd_online_responses"], 0)
        july_rows = analytics.activity_by_region(date(2026, 7, 1))
        self.assertEqual(july_rows[0]["cpd_online_responses"], 1)

    def test_response_on_the_last_day_of_the_month_is_not_dropped(self):
        """The boundary trap: a plain `__range` on a DateTimeField against an
        inclusive `date` upper bound silently loses the last day."""
        educator = self._educator(self.tashkent)
        announcement = self._publish(
            "End of month session", timezone.make_aware(datetime(2026, 5, 31, 23, 0))
        )
        AnnouncementResponse.objects.create(announcement=announcement, educator=educator, attending=True)
        self.assertEqual(analytics.activity_by_region(PERIOD)[0]["cpd_online_responses"], 1)


class SessionsHeldTests(TestCase):
    def test_counts_held_sessions_in_the_period_across_both_kinds(self):
        region = Region.objects.create(name="Tashkent City", code="tashkent-city", is_city=True)
        educator = Educator.objects.create(full_name="Teacher", region=region)
        eca = Activity.objects.create(
            educator=educator, kind=constants.ACTIVITY_KIND_ECA, title="Drama",
            started_on=date(2026, 4, 1),
        )
        offline = Activity.objects.create(
            educator=educator, kind=constants.ACTIVITY_KIND_CPD_OFFLINE, title="Friday CPD",
            started_on=date(2026, 4, 1),
        )
        Session.objects.create(
            activity=eca, scheduled_for=date(2026, 5, 8), held_on=date(2026, 5, 8),
            status=constants.SESSION_STATUS_HELD,
        )
        Session.objects.create(
            activity=offline, scheduled_for=date(2026, 5, 15), held_on=date(2026, 5, 15),
            status=constants.SESSION_STATUS_HELD,
        )
        Session.objects.create(
            activity=eca, scheduled_for=date(2026, 5, 22), held_on=None,
            status=constants.SESSION_STATUS_EXPECTED,
        )
        Session.objects.create(
            activity=eca, scheduled_for=date(2026, 6, 5), held_on=date(2026, 6, 5),
            status=constants.SESSION_STATUS_HELD,
        )
        self.assertEqual(analytics.sessions_held(PERIOD), 2)
