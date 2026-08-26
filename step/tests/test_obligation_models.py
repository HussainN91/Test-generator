"""An obligation type is a database row, not a class (spec §5.1).

That is what makes CPD Online, CPD Offline and ECA configuration rather than
three more builds. The test that matters is the last one: creating a new
vertical must take no code.
"""

from datetime import date

from django.db import IntegrityError
from django.test import TestCase

from step import constants
from step.models import AcademicYear, Educator, Obligation, ObligationType, Region, Term


class TermTests(TestCase):
    def setUp(self):
        self.year = AcademicYear.objects.create(
            label="2025-26", start=date(2025, 9, 1), end=date(2026, 5, 31), is_current=True
        )

    def test_terms_order_by_sequence(self):
        Term.objects.create(year=self.year, name="Term 3", sequence=3, start=date(2026, 3, 1), end=date(2026, 5, 31))
        Term.objects.create(year=self.year, name="Term 1", sequence=1, start=date(2025, 9, 1), end=date(2025, 11, 30))
        self.assertEqual([t.name for t in self.year.terms.all()], ["Term 1", "Term 3"])

    def test_only_one_year_can_be_current(self):
        AcademicYear.objects.create(
            label="2026-27", start=date(2026, 9, 1), end=date(2027, 5, 31), is_current=True
        )
        self.assertEqual(AcademicYear.objects.filter(is_current=True).count(), 1)
        self.assertEqual(AcademicYear.objects.get(is_current=True).label, "2026-27")


class ObligationTypeTests(TestCase):
    def test_defaults_are_the_least_surprising_ones(self):
        obligation_type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY,
        )
        self.assertTrue(obligation_type.is_active)
        self.assertEqual(obligation_type.evidence_spec, constants.EVIDENCE_EITHER)
        self.assertEqual(obligation_type.scope_rule, constants.SCOPE_ALL)
        self.assertEqual(obligation_type.min_count, 1)
        self.assertFalse(obligation_type.requires_review)

    def test_period_kind_follows_the_cadence(self):
        monthly = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY,
        )
        termly = ObligationType.objects.create(
            name_template="ECA Plan", category=constants.CATEGORY_ECA,
            cadence=constants.CADENCE_TERMLY,
        )
        self.assertEqual(monthly.period_kind, constants.PERIOD_MONTH)
        self.assertEqual(termly.period_kind, constants.PERIOD_TERM)

    def test_a_new_vertical_needs_no_code(self):
        """The acceptance test for the whole design (spec §2)."""
        ObligationType.objects.create(
            name_template="CPD Offline - {period}", category=constants.CATEGORY_CPD_OFFLINE,
            cadence=constants.CADENCE_TERMLY, evidence_spec=constants.EVIDENCE_FILE,
            requires_review=True,
        )
        self.assertEqual(ObligationType.objects.filter(category=constants.CATEGORY_CPD_OFFLINE).count(), 1)


class ObligationTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY,
        )

    def test_status_starts_not_started(self):
        obligation = Obligation.objects.create(
            type=self.type, educator=self.educator,
            period_kind=constants.PERIOD_MONTH, period_start=date(2026, 5, 1),
            due_date=date(2026, 5, 27),
        )
        self.assertEqual(obligation.status, constants.STATUS_NOT_STARTED)

    def test_one_obligation_per_type_educator_and_period(self):
        for _ in range(1):
            Obligation.objects.create(
                type=self.type, educator=self.educator,
                period_kind=constants.PERIOD_MONTH, period_start=date(2026, 5, 1),
                due_date=date(2026, 5, 27),
            )
        with self.assertRaises(IntegrityError):
            Obligation.objects.create(
                type=self.type, educator=self.educator,
                period_kind=constants.PERIOD_MONTH, period_start=date(2026, 5, 1),
                due_date=date(2026, 5, 27),
            )

    def test_display_name_renders_the_template_with_the_period(self):
        obligation = Obligation.objects.create(
            type=self.type, educator=self.educator,
            period_kind=constants.PERIOD_MONTH, period_start=date(2026, 5, 1),
            due_date=date(2026, 5, 27),
        )
        self.assertEqual(obligation.display_name, "Monthly Report - May 2026")

    def test_a_template_with_an_explicit_period_placeholder_is_honoured(self):
        obligation_type = ObligationType.objects.create(
            name_template="ECA Programme Plan - {period}", category=constants.CATEGORY_ECA,
            cadence=constants.CADENCE_TERMLY,
        )
        obligation = Obligation.objects.create(
            type=obligation_type, educator=self.educator,
            period_kind=constants.PERIOD_TERM, period_start=date(2025, 9, 1),
            period_label="Term 1", due_date=date(2025, 11, 25),
        )
        self.assertEqual(obligation.display_name, "ECA Programme Plan - Term 1")
