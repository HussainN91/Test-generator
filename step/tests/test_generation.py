"""Generation must be safe to run repeatedly — it is scheduled, and a retry
after a partial failure must not double up (spec §5.2). Staff must never
accrue obligations (spec §5.6).
"""

from datetime import date
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from step import constants, generation, roles
from step.models import AcademicYear, Educator, Obligation, ObligationType, Region, Term


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
