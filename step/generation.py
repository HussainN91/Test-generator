"""Materialising obligation instances.

Rows rather than on-the-fly computation (spec §5.2): submissions, extensions
and history all need something durable to hang off, and 60,000 rows a year is
not a storage problem.

Idempotent through the unique constraint on (type, educator, period_start), so
a scheduled run that is retried after a partial failure cannot double up.
"""

from datetime import date

from django.db import transaction

from step import constants, scheduling
from step.models import Educator, Obligation, ObligationType, TeachingClass


def eligible_educators():
    """Every educator who should accrue obligations.

    Excludes people flagged as missing from the last import — generating work
    for someone who has left the programme creates false overdue figures.
    """
    return Educator.objects.filter(is_active=True, missing_from_last_import=False)


def _create_missing(obligation_type, period_kind, period_start, due, label=""):
    created = 0
    for educator in eligible_educators():
        _, made = Obligation.objects.get_or_create(
            type=obligation_type,
            educator=educator,
            period_start=period_start,
            defaults={
                "period_kind": period_kind,
                "period_label": label,
                "due_date": due,
            },
        )
        if made:
            created += 1
    return created


@transaction.atomic
def generate_for_month(month_start: date) -> int:
    """Create this month's obligations for every monthly type."""
    start = scheduling.period_start_for(month_start, constants.PERIOD_MONTH)
    finish = scheduling.period_end(start, constants.PERIOD_MONTH)

    created = 0
    for obligation_type in ObligationType.objects.filter(
        is_active=True, cadence=constants.CADENCE_MONTHLY
    ):
        due = scheduling.due_date_for(obligation_type.due_rule, start, finish)
        created += _create_missing(obligation_type, constants.PERIOD_MONTH, start, due)
    return created


@transaction.atomic
def generate_for_term(term) -> int:
    """Create this term's obligations for every termly type."""
    created = 0
    for obligation_type in ObligationType.objects.filter(
        is_active=True, cadence=constants.CADENCE_TERMLY
    ):
        due = scheduling.due_date_for(obligation_type.due_rule, term.start, term.end)
        created += _create_missing(
            obligation_type, constants.PERIOD_TERM, term.start, due, label=term.name
        )
    return created


@transaction.atomic
def generate_checkpoint_obligations(year) -> int:
    """Create this year's beginning/mid/end-of-year diagnostic obligations.

    One per TeachingClass, not per educator: a teacher with two classes owes
    two checkpoints, because each class has its own roster and its own
    completion state (classes/gradebook spec, "Generation").
    """
    created = 0
    for obligation_type in ObligationType.objects.filter(
        is_active=True, form_slug=constants.FORM_SLUG_ASSESSMENT_CHECKPOINT
    ):
        due = scheduling.due_date_for(obligation_type.due_rule, year.start, year.end)
        for teaching_class in TeachingClass.objects.select_related("educator"):
            _, made = Obligation.objects.get_or_create(
                type=obligation_type,
                educator=teaching_class.educator,
                teaching_class=teaching_class,
                period_start=year.start,
                defaults={"period_kind": constants.PERIOD_YEAR, "due_date": due},
            )
            if made:
                created += 1
    return created
