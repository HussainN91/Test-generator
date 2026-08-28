"""Settling an ECA activity's monthly-plan obligation. Mirrors
step/tests/test_workflow.py's SyncCheckpointTests style — sync_activity_plan
is the activity-plan sibling of sync_checkpoint.
"""

from datetime import date

from django.test import TestCase

from step import constants, workflow
from step.models import Activity, ActivityPlan, Educator, Obligation, ObligationType, Region


class SyncActivityPlanTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.activity = Activity.objects.create(
            educator=self.educator, kind=constants.ACTIVITY_KIND_ECA, title="Chess Club",
            schedule_rule={"weekdays": [4]}, started_on=date(2026, 5, 1),
        )
        self.plan_type = ObligationType.objects.create(
            name_template="ECA Monthly Plan", category=constants.CATEGORY_ECA,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
            form_slug=constants.FORM_SLUG_ECA_MONTHLY_PLAN,
        )
        self.obligation = Obligation.objects.create(
            type=self.plan_type, educator=self.educator, activity=self.activity,
            period_kind=constants.PERIOD_MONTH, period_start=date(2026, 5, 1), due_date=date(2026, 5, 31),
        )

    def make_plan(self, **kwargs):
        defaults = dict(activity=self.activity, period=date(2026, 5, 1))
        defaults.update(kwargs)
        return ActivityPlan.objects.create(**defaults)

    def test_partially_filled_leaves_it_not_started(self):
        plan = self.make_plan(overview="We meet weekly.")
        workflow.sync_activity_plan(plan)
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_NOT_STARTED)

    def test_all_three_fields_settle_the_obligation(self):
        plan = self.make_plan(
            overview="We meet weekly.", session_outline="Warm up, play, review.",
            intended_outcomes="Improve strategic thinking.",
        )
        workflow.sync_activity_plan(plan)
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_ACCEPTED)

    def test_whitespace_only_does_not_count_as_filled(self):
        plan = self.make_plan(overview="  ", session_outline="  ", intended_outcomes="  ")
        workflow.sync_activity_plan(plan)
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_NOT_STARTED)

    def test_rerunning_after_acceptance_does_not_error(self):
        plan = self.make_plan(overview="A", session_outline="B", intended_outcomes="C")
        workflow.sync_activity_plan(plan)
        result = workflow.sync_activity_plan(plan)
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_ACCEPTED)
        self.assertEqual(result, self.obligation)

    def test_missing_obligation_returns_none_without_crashing(self):
        other_activity = Activity.objects.create(
            educator=self.educator, kind=constants.ACTIVITY_KIND_ECA, title="Debate Club",
            schedule_rule={"weekdays": [2]}, started_on=date(2026, 5, 1),
        )
        plan = ActivityPlan.objects.create(
            activity=other_activity, period=date(2026, 5, 1),
            overview="A", session_outline="B", intended_outcomes="C",
        )
        result = workflow.sync_activity_plan(plan)
        self.assertIsNone(result)
