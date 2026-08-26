"""Everything the teacher's screen shows that is not stored.

Urgency badges and the four stat tiles are derived at read time. The teacher's
view of "done" is deliberately generous: once they have submitted, the ball is
with an administrator, so a submission awaiting review shows as done rather
than as outstanding work. Only a *returned* submission comes back to them.
"""

from datetime import date

from step import constants


def _outstanding(status: str) -> bool:
    return status in {constants.STATUS_NOT_STARTED, constants.STATUS_RETURNED}


def urgency_of(obligation, today: date | None = None) -> str:
    today = today or date.today()

    if not _outstanding(obligation.status):
        return constants.URGENCY_DONE

    days = (obligation.due_date - today).days
    if days < 0:
        return constants.URGENCY_OVERDUE
    if days == 0:
        return constants.URGENCY_DUE_TODAY
    if days <= constants.DUE_SOON_DAYS:
        return constants.URGENCY_DUE_SOON
    return constants.URGENCY_SCHEDULED


def outstanding_for(educator):
    return educator.obligations.filter(
        status__in=[constants.STATUS_NOT_STARTED, constants.STATUS_RETURNED]
    ).select_related("type")


def next_action(educator, today: date | None = None):
    """The single most urgent thing, for the "what do I do now" panel (spec §7.1)."""
    return outstanding_for(educator).order_by("due_date").first()


def teacher_tiles(educator, today: date | None = None) -> dict:
    """The four figures across the top of the teacher's home."""
    today = today or date.today()
    obligations = list(educator.obligations.all())

    active = sum(1 for o in obligations if _outstanding(o.status))
    completed = sum(1 for o in obligations if o.status in constants.SETTLED_STATUSES)
    due_this_month = sum(
        1 for o in obligations
        if _outstanding(o.status)
        and o.due_date.year == today.year
        and o.due_date.month == today.month
    )
    total = len(obligations)
    progress = round(completed * 100 / total) if total else 0

    return {
        "active": active,
        "due_this_month": due_this_month,
        "completed": completed,
        "progress_percent": progress,
    }
