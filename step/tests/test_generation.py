"""Generation must be safe to run repeatedly — it is scheduled, and a retry
after a partial failure must not double up (spec §5.2). Staff must never
accrue obligations (spec §5.6).
"""

from datetime import date, timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from step import constants, generation, roles
from step.models import (
    AcademicYear, Activity, Educator, Obligation, ObligationType, Region, Session, TeachingClass, Term,
)


class GenerateTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.maria = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.john = Educator.objects.create(full_name="John Cruz", region=self.region)
        self.year = AcademicYear.objects.create(
            label="2025-26", start=date(2025, 9, 1), end=date(2026, 5, 31), is_current=True
        )
        self.term1 = Term.objects.create(
            year=self.year, name="Term 1", sequence=1, start=date(2025, 9, 1), end=date(2025, 11, 30)
        )
        self.monthly = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, due_rule={"kind": "day_of_month", "day": 27},
        )

    def test_generates_one_obligation_per_active_educator(self):
        created = generation.generate_for_month(date(2026, 5, 1))
        self.assertEqual(created, 2)
        self.assertEqual(Obligation.objects.count(), 2)

    def test_the_due_date_comes_from_the_rule(self):
        generation.generate_for_month(date(2026, 5, 1))
        self.assertEqual(Obligation.objects.first().due_date, date(2026, 5, 27))

    def test_running_twice_creates_nothing_new(self):
        generation.generate_for_month(date(2026, 5, 1))
        created = generation.generate_for_month(date(2026, 5, 1))
        self.assertEqual(created, 0)
        self.assertEqual(Obligation.objects.count(), 2)

    def test_inactive_educators_are_skipped(self):
        self.john.is_active = False
        self.john.save()
        generation.generate_for_month(date(2026, 5, 1))
        self.assertEqual(Obligation.objects.count(), 1)

    def test_educators_missing_from_the_last_import_are_skipped(self):
        self.john.missing_from_last_import = True
        self.john.save()
        generation.generate_for_month(date(2026, 5, 1))
        self.assertEqual(Obligation.objects.count(), 1)

    def test_inactive_types_are_skipped(self):
        self.monthly.is_active = False
        self.monthly.save()
        self.assertEqual(generation.generate_for_month(date(2026, 5, 1)), 0)

    def test_termly_types_are_not_generated_by_the_monthly_run(self):
        ObligationType.objects.create(
            name_template="ECA Plan", category=constants.CATEGORY_ECA, cadence=constants.CADENCE_TERMLY
        )
        generation.generate_for_month(date(2026, 5, 1))
        self.assertEqual(Obligation.objects.filter(period_kind=constants.PERIOD_TERM).count(), 0)

    def test_termly_generation_uses_the_term_dates_and_label(self):
        ObligationType.objects.create(
            name_template="ECA Programme Plan - {period}", category=constants.CATEGORY_ECA,
            cadence=constants.CADENCE_TERMLY, due_rule={"kind": "days_before_period_end", "days": 5},
        )
        created = generation.generate_for_term(self.term1)
        self.assertEqual(created, 2)
        obligation = Obligation.objects.get(educator=self.maria, period_kind=constants.PERIOD_TERM)
        self.assertEqual(obligation.period_label, "Term 1")
        self.assertEqual(obligation.due_date, date(2025, 11, 25))
        self.assertEqual(obligation.display_name, "ECA Programme Plan - Term 1")

    def test_staff_users_without_an_educator_row_get_nothing(self):
        user = get_user_model().objects.create_user("admin2", password="x")
        call_command("seed_roles", stdout=StringIO())
        roles.assign(user, constants.ROLE_PROGRAMME_ADMIN)
        generation.generate_for_month(date(2026, 5, 1))
        self.assertEqual(Obligation.objects.count(), 2)


class GenerateCommandTests(TestCase):
    def setUp(self):
        region = Region.objects.create(name="Samarkand", code="samarkand")
        Educator.objects.create(full_name="Maria Santos", region=region)
        ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, due_rule={"kind": "day_of_month", "day": 27},
        )

    def test_command_generates_for_an_explicit_month(self):
        out = StringIO()
        call_command("generate_obligations", "--month", "2026-05", stdout=out)
        self.assertEqual(Obligation.objects.count(), 1)
        self.assertIn("1", out.getvalue())

    def test_command_rejects_a_malformed_month(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command("generate_obligations", "--month", "May", stdout=StringIO())

    def test_without_sessions_flag_neither_plan_obligations_nor_sessions_are_touched(self):
        educator = Educator.objects.get(full_name="Maria Santos")
        Activity.objects.create(
            educator=educator, kind=constants.ACTIVITY_KIND_ECA, title="Chess Club",
            schedule_rule={"weekdays": [0, 1, 2, 3, 4, 5, 6]}, started_on=date.today(),
        )
        out = StringIO()
        call_command("generate_obligations", "--month", "2026-05", stdout=out)
        # Existing per-educator monthly generation still runs unchanged; what
        # must NOT happen without --sessions is any per-activity row or Session.
        self.assertEqual(Session.objects.count(), 0)
        self.assertEqual(Obligation.objects.filter(activity__isnull=False).count(), 0)
        self.assertIn("Created 1 obligations.", out.getvalue())
        self.assertNotIn("sessions", out.getvalue())

    def test_sessions_flag_generates_plan_obligations_and_materialises_sessions(self):
        region = Region.objects.get(code="samarkand")
        educator = Educator.objects.get(full_name="Maria Santos")
        ObligationType.objects.create(
            name_template="ECA Monthly Plan", category=constants.CATEGORY_ECA,
            cadence=constants.CADENCE_MONTHLY, form_slug=constants.FORM_SLUG_ECA_MONTHLY_PLAN,
        )
        Activity.objects.create(
            educator=educator, kind=constants.ACTIVITY_KIND_ECA, title="Chess Club",
            schedule_rule={"weekdays": [0, 1, 2, 3, 4, 5, 6]}, started_on=date(2026, 4, 1),
        )
        out = StringIO()
        call_command("generate_obligations", "--month", "2026-05", "--sessions", stdout=out)
        self.assertTrue(Obligation.objects.filter(activity__isnull=False).exists())
        self.assertTrue(Session.objects.exists())
        self.assertIn("sessions", out.getvalue())

    def test_sessions_flag_skips_archived_activities(self):
        region = Region.objects.get(code="samarkand")
        educator = Educator.objects.get(full_name="Maria Santos")
        Activity.objects.create(
            educator=educator, kind=constants.ACTIVITY_KIND_CPD_OFFLINE, title="Offline CPD",
            schedule_rule={"weekdays": [0, 1, 2, 3, 4, 5, 6]}, started_on=date.today() - timedelta(days=60),
            archived_on=date.today() - timedelta(days=1),
        )
        out = StringIO()
        call_command("generate_obligations", "--sessions", stdout=out)
        self.assertEqual(Session.objects.count(), 0)


class GenerateCheckpointObligationsTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.maria = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.john = Educator.objects.create(full_name="John Cruz", region=self.region)
        self.year = AcademicYear.objects.create(
            label="2025-26", start=date(2025, 9, 1), end=date(2026, 5, 31), is_current=True
        )
        self.boy = ObligationType.objects.create(
            name_template="Beginning-of-year diagnostic", category=constants.CATEGORY_ASSESSMENTS,
            cadence=constants.CADENCE_ANNUAL, evidence_spec=constants.EVIDENCE_NONE,
            form_slug=constants.FORM_SLUG_ASSESSMENT_CHECKPOINT,
            due_rule={"kind": "days_after_period_start", "days": 30},
        )

    def test_one_obligation_per_teaching_class_not_per_educator(self):
        TeachingClass.objects.create(educator=self.maria, grade=9, slot=1, display_name="9A")
        TeachingClass.objects.create(educator=self.maria, grade=9, slot=2, display_name="9B")
        created = generation.generate_checkpoint_obligations(self.year)
        self.assertEqual(created, 2)
        self.assertEqual(Obligation.objects.filter(type=self.boy).count(), 2)

    def test_an_educator_with_no_class_gets_nothing(self):
        created = generation.generate_checkpoint_obligations(self.year)
        self.assertEqual(created, 0)

    def test_the_obligation_carries_the_classs_own_educator(self):
        teaching_class = TeachingClass.objects.create(
            educator=self.john, grade=10, slot=1, display_name="10A"
        )
        generation.generate_checkpoint_obligations(self.year)
        obligation = Obligation.objects.get(teaching_class=teaching_class)
        self.assertEqual(obligation.educator, self.john)

    def test_the_due_date_comes_from_the_types_own_rule_against_year_bounds(self):
        TeachingClass.objects.create(educator=self.maria, grade=9, slot=1, display_name="9A")
        generation.generate_checkpoint_obligations(self.year)
        obligation = Obligation.objects.get(type=self.boy)
        self.assertEqual(obligation.due_date, date(2025, 10, 1))
        self.assertEqual(obligation.period_kind, constants.PERIOD_YEAR)
        self.assertEqual(obligation.period_start, self.year.start)

    def test_running_twice_creates_nothing_new(self):
        TeachingClass.objects.create(educator=self.maria, grade=9, slot=1, display_name="9A")
        generation.generate_checkpoint_obligations(self.year)
        created = generation.generate_checkpoint_obligations(self.year)
        self.assertEqual(created, 0)

    def test_non_checkpoint_types_are_not_touched(self):
        ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY,
        )
        TeachingClass.objects.create(educator=self.maria, grade=9, slot=1, display_name="9A")
        generation.generate_checkpoint_obligations(self.year)
        self.assertEqual(Obligation.objects.exclude(type=self.boy).count(), 0)
