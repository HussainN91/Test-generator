"""Materialising obligation instances.

Rows rather than on-the-fly computation (spec §5.2): submissions, extensions
and history all need something durable to hang off, and 60,000 rows a year is
not a storage problem.

Idempotent through the unique constraint on (type, educator, period_start), so
a scheduled run that is retried after a partial failure cannot double up.
"""

from datetime import date, timedelta

from django.db import transaction
from django.db.models import Q

from step import constants, scheduling
from step.models import Activity, Educator, Obligation, ObligationType, Session, TeachingClass

#: How many days ahead to materialise Session rows when an activity is
#: created or touched by the scheduled command. Keeps a teacher's "upcoming
#: sessions" list populated a few weeks out without materialising the
#: activity's entire future.
SESSION_GENERATION_HORIZON_DAYS = 28


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


@transaction.atomic
def generate_sessions(activity, through: date) -> int:
    """Materialise expected Session rows for `activity` up to and including
    `through`.

    Starts the later of `activity.started_on` and the day after the latest
    already-materialised session, so a repeat call only fills in the new
    dates rather than re-walking (and re-checking) the whole history. Never
    generates past `activity.archived_on`, if set. Idempotent via
    get_or_create keyed on (activity, scheduled_for) — see this module's
    docstring on why idempotency matters for a scheduled/retried run.
    """
    start = activity.started_on
    latest = activity.sessions.order_by("-scheduled_for").first()
    if latest is not None:
        start = max(start, latest.scheduled_for + timedelta(days=1))

    finish = through
    if activity.archived_on is not None:
        finish = min(finish, activity.archived_on)

    if start > finish:
        return 0

    created = 0
    for scheduled_for in scheduling.session_dates(activity.schedule_rule, start, finish):
        _, made = Session.objects.get_or_create(
            activity=activity,
            scheduled_for=scheduled_for,
            defaults={"status": constants.SESSION_STATUS_EXPECTED},
        )
        if made:
            created += 1
    return created


def _first_eligible_plan_period(activity) -> date:
    """The first month-start (day=1) for which `activity` owes an ECA
    monthly plan.

    Normally the month containing `activity.started_on`. But a group started
    in the last 7 days of that month should not be born already overdue for
    a month it barely joined, so it skips straight to next month instead.
    The boundary is inclusive: a `started_on` that lands exactly 7 days
    before month-end already counts as "within the last 7 days" and is
    deferred (i.e. the cutoff is `month_end - 7 days`, not `- 6`).
    """
    month_start = scheduling.period_start_for(activity.started_on, constants.PERIOD_MONTH)
    month_finish = scheduling.period_end(month_start, constants.PERIOD_MONTH)
    if activity.started_on >= month_finish - timedelta(days=7):
        return scheduling.next_period_start(month_start, constants.PERIOD_MONTH)
    return month_start


@transaction.atomic
def generate_activity_plan_obligations(month_start: date) -> int:
    """One ECA monthly-plan obligation per active, unarchived ECA Activity whose
    first eligible period has arrived. Mirrors generate_checkpoint_obligations's
    per-class shape, but per-activity."""
    obligation_type = ObligationType.objects.filter(
        is_active=True, form_slug=constants.FORM_SLUG_ECA_MONTHLY_PLAN
    ).first()
    if obligation_type is None:
        # Seed data for this form doesn't exist until a later phase.
        return 0

    finish = scheduling.period_end(month_start, constants.PERIOD_MONTH)
    due = scheduling.due_date_for(obligation_type.due_rule, month_start, finish)

    created = 0
    activities = Activity.objects.filter(kind=constants.ACTIVITY_KIND_ECA).filter(
        Q(archived_on__isnull=True) | Q(archived_on__gte=month_start)
    )
    for activity in activities:
        if _first_eligible_plan_period(activity) > month_start:
            continue
        _, made = Obligation.objects.get_or_create(
            type=obligation_type,
            educator=activity.educator,
            activity=activity,
            period_start=month_start,
            defaults={"period_kind": constants.PERIOD_MONTH, "due_date": due},
        )
        if made:
            created += 1
    return created


def on_activity_created(activity, today: date | None = None) -> None:
    """Call right after an Activity row is saved, so a teacher who starts a
    group mid-month gets sessions and (for ECA) that month's plan obligation
    immediately, rather than waiting for the nightly batch.
    """
    today = today or date.today()
    generate_sessions(activity, through=today + timedelta(days=SESSION_GENERATION_HORIZON_DAYS))
    if activity.kind == constants.ACTIVITY_KIND_ECA:
        generate_activity_plan_obligations(scheduling.period_start_for(today, constants.PERIOD_MONTH))
