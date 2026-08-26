"""Due dates come from a rule on the obligation type (spec §5.4).

Month-end is the classic trap: "day 31 of the month" must not explode in
February, and "five days before term end" must land inside the term.
"""

from datetime import date

from django.test import SimpleTestCase

from step import constants, scheduling


class MonthPeriodTests(SimpleTestCase):
    def test_month_start_normalises_to_the_first(self):
        self.assertEqual(scheduling.period_start_for(date(2026, 5, 17), constants.PERIOD_MONTH), date(2026, 5, 1))

    def test_month_end(self):
        self.assertEqual(scheduling.period_end(date(2026, 5, 1), constants.PERIOD_MONTH), date(2026, 5, 31))

    def test_february_end_in_a_leap_year(self):
        self.assertEqual(scheduling.period_end(date(2028, 2, 1), constants.PERIOD_MONTH), date(2028, 2, 29))

    def test_next_month_rolls_the_year(self):
        self.assertEqual(scheduling.next_period_start(date(2026, 12, 1), constants.PERIOD_MONTH), date(2027, 1, 1))


class DueDateRuleTests(SimpleTestCase):
    def test_day_of_month(self):
        rule = {"kind": "day_of_month", "day": 27}
        due = scheduling.due_date_for(rule, date(2026, 5, 1), date(2026, 5, 31))
        self.assertEqual(due, date(2026, 5, 27))

    def test_day_of_month_is_clamped_to_the_last_day(self):
        rule = {"kind": "day_of_month", "day": 31}
        due = scheduling.due_date_for(rule, date(2026, 2, 1), date(2026, 2, 28))
        self.assertEqual(due, date(2026, 2, 28))

    def test_days_before_period_end(self):
        rule = {"kind": "days_before_period_end", "days": 5}
        due = scheduling.due_date_for(rule, date(2025, 9, 1), date(2025, 11, 30))
        self.assertEqual(due, date(2025, 11, 25))

    def test_days_before_period_end_never_precedes_the_start(self):
        rule = {"kind": "days_before_period_end", "days": 500}
        due = scheduling.due_date_for(rule, date(2026, 5, 1), date(2026, 5, 31))
        self.assertEqual(due, date(2026, 5, 1))

    def test_days_after_period_start(self):
        rule = {"kind": "days_after_period_start", "days": 10}
        due = scheduling.due_date_for(rule, date(2026, 5, 1), date(2026, 5, 31))
        self.assertEqual(due, date(2026, 5, 11))

    def test_fixed_date(self):
        rule = {"kind": "fixed", "date": "2026-06-15"}
        due = scheduling.due_date_for(rule, date(2026, 5, 1), date(2026, 5, 31))
        self.assertEqual(due, date(2026, 6, 15))

    def test_an_unknown_rule_kind_raises_rather_than_defaulting(self):
        with self.assertRaises(ValueError):
            scheduling.due_date_for({"kind": "whenever"}, date(2026, 5, 1), date(2026, 5, 31))

    def test_an_empty_rule_defaults_to_the_period_end(self):
        due = scheduling.due_date_for({}, date(2026, 5, 1), date(2026, 5, 31))
        self.assertEqual(due, date(2026, 5, 31))
