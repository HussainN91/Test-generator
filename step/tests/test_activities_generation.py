"""Session materialisation and ECA monthly-plan obligations (fix step plan
§2-§3, phase 2). Mirrors step/tests/test_generation.py's style.
"""

from datetime import date

from django.test import TestCase

from step import constants, generation
from step.models import Activity, Educator, Obligation, ObligationType, Region, School, Session


class GenerateSessionsTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.school = School.objects.create(name="School 42")
        self.maria = Educator.objects.create(full_name="Maria Santos", region=self.region)

    def _activity(self, **kwargs):
        defaults = dict(
            educator=self.maria, kind=constants.ACTIVITY_KIND_ECA, title="Chess Club",
            school=self.school, schedule_rule={"weekdays": [4]}, started_on=date(2026, 5, 1),
        )
        defaults.update(kwargs)
        return Activity.objects.create(**defaults)

    def test_creates_one_session_per_matching_weekday_in_range(self):
        activity = self._activity()
        created = generation.generate_sessions(activity, through=date(2026, 5, 31))
        # Fridays in May 2026: 1, 8, 15, 22, 29.
        self.assertEqual(created, 5)
        self.assertEqual(Session.objects.filter(activity=activity).count(), 5)
        self.assertEqual(
            list(Session.objects.filter(activity=activity).values_list("scheduled_for", flat=True)),
            [date(2026, 5, 1), date(2026, 5, 8), date(2026, 5, 15), date(2026, 5, 22), date(2026, 5, 29)],
        )

    def test_running_twice_creates_nothing_new(self):
        activity = self._activity()
        generation.generate_sessions(activity, through=date(2026, 5, 31))
        created = generation.generate_sessions(activity, through=date(2026, 5, 31))
        self.assertEqual(created, 0)
        self.assertEqual(Session.objects.filter(activity=activity).count(), 5)

    def test_respects_started_on_as_a_floor(self):
        # started_on is a Wednesday; the first Friday on/after it is the 15th.
        activity = self._activity(started_on=date(2026, 5, 13))
        generation.generate_sessions(activity, through=date(2026, 5, 31))
        dates = list(Session.objects.filter(activity=activity).values_list("scheduled_for", flat=True))
        self.assertEqual(dates, [date(2026, 5, 15), date(2026, 5, 22), date(2026, 5, 29)])

    def test_respects_archived_on_as_a_ceiling(self):
        activity = self._activity(archived_on=date(2026, 5, 20))
        generation.generate_sessions(activity, through=date(2026, 5, 31))
        dates = list(Session.objects.filter(activity=activity).values_list("scheduled_for", flat=True))
        self.assertEqual(dates, [date(2026, 5, 1), date(2026, 5, 8), date(2026, 5, 15)])

    def test_a_second_call_with_a_later_through_only_creates_the_new_dates(self):
        activity = self._activity()
        first = generation.generate_sessions(activity, through=date(2026, 5, 15))
        self.assertEqual(first, 3)  # May 1, 8, 15 (through is inclusive)
        second = generation.generate_sessions(activity, through=date(2026, 5, 31))
        self.assertEqual(second, 2)  # May 22, 29
        self.assertEqual(Session.objects.filter(activity=activity).count(), 5)

    def test_created_sessions_are_expected_status(self):
        activity = self._activity()
        generation.generate_sessions(activity, through=date(2026, 5, 1))
        session = Session.objects.get(activity=activity)
        self.assertEqual(session.status, constants.SESSION_STATUS_EXPECTED)


class FirstEligiblePlanPeriodTests(TestCase):
    """Late-month grace: a group started in the last 7 days of a month isn't
    born already owing that month's plan."""

    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.maria = Educator.objects.create(full_name="Maria Santos", region=self.region)

    def _activity(self, started_on):
        return Activity.objects.create(
            educator=self.maria, kind=constants.ACTIVITY_KIND_ECA, title="Chess Club",
            schedule_rule={"weekdays": [4]}, started_on=started_on,
        )

    def test_started_early_in_the_month_is_eligible_for_that_month(self):
        # May 2026 has 31 days; May 23 is 8 days before month-end (not "within
        # the last 7 days" per the inclusive boundary at exactly 7 days).
        activity = self._activity(date(2026, 5, 23))
        self.assertEqual(generation._first_eligible_plan_period(activity), date(2026, 5, 1))

    def test_started_exactly_seven_days_before_month_end_is_deferred(self):
        # May 31 - 7 days = May 24: the documented inclusive boundary.
        activity = self._activity(date(2026, 5, 24))
        self.assertEqual(generation._first_eligible_plan_period(activity), date(2026, 6, 1))

    def test_started_in_the_last_week_of_the_month_is_deferred_to_next_month(self):
        activity = self._activity(date(2026, 5, 29))
        self.assertEqual(generation._first_eligible_plan_period(activity), date(2026, 6, 1))


class GenerateActivityPlanObligationsTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.school = School.objects.create(name="School 42")
        self.maria = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.john = Educator.objects.create(full_name="John Cruz", region=self.region)
        self.plan_type = ObligationType.objects.create(
            name_template="ECA Monthly Plan", category=constants.CATEGORY_ECA,
            cadence=constants.CADENCE_MONTHLY, form_slug=constants.FORM_SLUG_ECA_MONTHLY_PLAN,
            due_rule={"kind": "day_of_month", "day": 27},
        )

    def _eca(self, educator=None, **kwargs):
        defaults = dict(
            educator=educator or self.maria, kind=constants.ACTIVITY_KIND_ECA, title="Chess Club",
            schedule_rule={"weekdays": [4]}, started_on=date(2026, 4, 1),
        )
        defaults.update(kwargs)
        return Activity.objects.create(**defaults)

    def test_creates_one_obligation_per_eligible_eca_activity(self):
        self._eca(educator=self.maria)
        self._eca(educator=self.john)
        created = generation.generate_activity_plan_obligations(date(2026, 5, 1))
        self.assertEqual(created, 2)
        self.assertEqual(Obligation.objects.filter(type=self.plan_type).count(), 2)

    def test_skips_cpd_offline_activities_entirely(self):
        Activity.objects.create(
            educator=self.maria, kind=constants.ACTIVITY_KIND_CPD_OFFLINE, title="Offline CPD",
            school=self.school, schedule_rule={"weekdays": [2]}, started_on=date(2026, 4, 1),
        )
        created = generation.generate_activity_plan_obligations(date(2026, 5, 1))
        self.assertEqual(created, 0)

    def test_skips_an_activity_archived_before_month_start(self):
        self._eca(archived_on=date(2026, 4, 15))
        created = generation.generate_activity_plan_obligations(date(2026, 5, 1))
        self.assertEqual(created, 0)

    def test_an_activity_archived_during_the_month_still_gets_it(self):
        self._eca(archived_on=date(2026, 5, 15))
        created = generation.generate_activity_plan_obligations(date(2026, 5, 1))
        self.assertEqual(created, 1)

    def test_running_twice_creates_nothing_new(self):
        self._eca()
        generation.generate_activity_plan_obligations(date(2026, 5, 1))
        created = generation.generate_activity_plan_obligations(date(2026, 5, 1))
        self.assertEqual(created, 0)
        self.assertEqual(Obligation.objects.filter(type=self.plan_type).count(), 1)

    def test_an_activity_created_too_late_in_the_month_is_skipped_for_that_month(self):
        self._eca(started_on=date(2026, 5, 24))  # within the last-7-days grace window
        created = generation.generate_activity_plan_obligations(date(2026, 5, 1))
        self.assertEqual(created, 0)
        created_next = generation.generate_activity_plan_obligations(date(2026, 6, 1))
        self.assertEqual(created_next, 1)

    def test_no_active_obligation_type_means_silent_skip(self):
        self.plan_type.is_active = False
        self.plan_type.save()
        self._eca()
        created = generation.generate_activity_plan_obligations(date(2026, 5, 1))
        self.assertEqual(created, 0)

    def test_the_due_date_comes_from_the_types_rule(self):
        self._eca()
        generation.generate_activity_plan_obligations(date(2026, 5, 1))
        obligation = Obligation.objects.get(type=self.plan_type)
        self.assertEqual(obligation.due_date, date(2026, 5, 27))
        self.assertEqual(obligation.period_kind, constants.PERIOD_MONTH)


class OnActivityCreatedTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.school = School.objects.create(name="School 42")
        self.maria = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.plan_type = ObligationType.objects.create(
            name_template="ECA Monthly Plan", category=constants.CATEGORY_ECA,
            cadence=constants.CADENCE_MONTHLY, form_slug=constants.FORM_SLUG_ECA_MONTHLY_PLAN,
            due_rule={"kind": "day_of_month", "day": 27},
        )

    def test_eca_activity_gets_sessions_and_this_months_plan_obligation(self):
        activity = Activity.objects.create(
            educator=self.maria, kind=constants.ACTIVITY_KIND_ECA, title="Chess Club",
            schedule_rule={"weekdays": [4]}, started_on=date(2026, 5, 1),
        )
        generation.on_activity_created(activity, today=date(2026, 5, 4))
        self.assertTrue(Session.objects.filter(activity=activity).exists())
        self.assertTrue(
            Obligation.objects.filter(
                type=self.plan_type, activity=activity, period_start=date(2026, 5, 1)
            ).exists()
        )

    def test_cpd_offline_activity_gets_sessions_but_no_plan_obligation(self):
        activity = Activity.objects.create(
            educator=self.maria, kind=constants.ACTIVITY_KIND_CPD_OFFLINE, title="Offline CPD",
            school=self.school, schedule_rule={"weekdays": [2]}, started_on=date(2026, 5, 1),
        )
        generation.on_activity_created(activity, today=date(2026, 5, 4))
        self.assertTrue(Session.objects.filter(activity=activity).exists())
        self.assertFalse(Obligation.objects.filter(activity=activity).exists())
