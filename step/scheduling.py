"""Period arithmetic and due-date rules.

Kept free of models on purpose. Date handling is where the quiet bugs are —
"day 31" in February, a term deadline that lands before the term starts — and
pure functions make those cases cheap to pin down in tests.

A due rule is a small JSON object stored on the obligation type:

    {"kind": "day_of_month", "day": 27}
    {"kind": "days_before_period_end", "days": 5}
    {"kind": "days_after_period_start", "days": 10}
    {"kind": "fixed", "date": "2026-06-15"}

An empty rule means "the last day of the period".
"""

import calendar
from datetime import date, timedelta

from step import constants


def period_start_for(day: date, period_kind: str) -> date:
    if period_kind == constants.PERIOD_MONTH:
        return day.replace(day=1)
    return day


def period_end(start: date, period_kind: str) -> date:
    if period_kind == constants.PERIOD_MONTH:
        return start.replace(day=calendar.monthrange(start.year, start.month)[1])
    if period_kind == constants.PERIOD_YEAR:
        return date(start.year, 12, 31)
    return start


def next_period_start(start: date, period_kind: str) -> date:
    if period_kind == constants.PERIOD_MONTH:
        if start.month == 12:
            return date(start.year + 1, 1, 1)
        return date(start.year, start.month + 1, 1)
    if period_kind == constants.PERIOD_YEAR:
        return date(start.year + 1, start.month, start.day)
    return start


def due_date_for(rule, period_start: date, period_finish: date) -> date:
    """Resolve a due rule against a concrete period.

    Always returns a date inside [period_start, period_finish] for the relative
    rules; a "fixed" rule is trusted as given, because an explicit date is an
    explicit decision.
    """
    if not rule:
        return period_finish

    kind = rule.get("kind")

    if kind == "day_of_month":
        day = int(rule["day"])
        last = calendar.monthrange(period_start.year, period_start.month)[1]
        return period_start.replace(day=min(day, last))

    if kind == "days_before_period_end":
        candidate = period_finish - timedelta(days=int(rule["days"]))
        return max(candidate, period_start)

    if kind == "days_after_period_start":
        candidate = period_start + timedelta(days=int(rule["days"]))
        return min(candidate, period_finish)

    if kind == "fixed":
        return date.fromisoformat(rule["date"])

    raise ValueError(f"Unknown due rule kind: {kind!r}")
