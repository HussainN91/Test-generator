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


class SessionDatesTests(SimpleTestCase):
    def test_a_single_weekday_rule_returns_every_matching_date_in_range(self):
        # May 2026: Fridays fall on the 1st, 8th, 15th, 22nd, 29th.
        dates = scheduling.session_dates({"weekdays": [4]}, date(2026, 5, 1), date(2026, 5, 31))
        self.assertEqual(
            dates,
            [date(2026, 5, 1), date(2026, 5, 8), date(2026, 5, 15), date(2026, 5, 22), date(2026, 5, 29)],
        )

    def test_a_multi_weekday_rule_returns_both_interleaved_in_order(self):
        # Tue+Thu across one week: 2026-05-05 (Tue) and 2026-05-07 (Thu).
        dates = scheduling.session_dates({"weekdays": [1, 3]}, date(2026, 5, 4), date(2026, 5, 10))
        self.assertEqual(dates, [date(2026, 5, 5), date(2026, 5, 7)])

    def test_start_that_is_itself_a_matching_weekday_is_included(self):
        # 2026-05-01 is a Friday.
        dates = scheduling.session_dates({"weekdays": [4]}, date(2026, 5, 1), date(2026, 5, 1))
        self.assertEqual(dates, [date(2026, 5, 1)])

    def test_finish_that_is_itself_a_matching_weekday_is_included(self):
        # 2026-05-29 is a Friday.
        dates = scheduling.session_dates({"weekdays": [4]}, date(2026, 5, 25), date(2026, 5, 29))
        self.assertEqual(dates, [date(2026, 5, 29)])

    def test_a_range_that_starts_and_ends_mid_week_only_returns_matches_inside_it(self):
        # 2026-05-06 is a Wednesday, 2026-05-12 is a Tuesday. Only the Friday
        # in between (2026-05-08) should be returned for a Friday rule.
        dates = scheduling.session_dates({"weekdays": [4]}, date(2026, 5, 6), date(2026, 5, 12))
        self.assertEqual(dates, [date(2026, 5, 8)])

    def test_crossing_a_month_boundary_returns_dates_from_both_months(self):
        # Fridays late May into early June 2026: 2026-05-29 and 2026-06-05.
        dates = scheduling.session_dates({"weekdays": [4]}, date(2026, 5, 25), date(2026, 6, 5))
        self.assertEqual(dates, [date(2026, 5, 29), date(2026, 6, 5)])

    def test_an_empty_weekdays_list_returns_nothing(self):
        dates = scheduling.session_dates({"weekdays": []}, date(2026, 5, 1), date(2026, 5, 31))
        self.assertEqual(dates, [])

    def test_a_missing_weekdays_key_returns_nothing(self):
        dates = scheduling.session_dates({}, date(2026, 5, 1), date(2026, 5, 31))
        self.assertEqual(dates, [])
