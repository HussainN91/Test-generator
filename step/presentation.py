"""Turning model state into words a person can act on.

The spine spec (§7.0) forbids showing model vocabulary to users: nobody should
ever read "status: not_started" or "evidence_spec: both". This module is the
single place where stored state becomes English, so the wording cannot drift
between the dashboard, the obligation page and the submissions list.

Two rules it exists to enforce:

* **Deadlines are relative, then absolute.** "Due in 3 days" is something a
  tired person can act on; "27/05/2026" is arithmetic homework. The exact date
  is still shown alongside, because relative-only is ambiguous.
* **Status is always a word.** Colour reinforces it and never carries it alone.
  The CSS class returned here only picks the reinforcing colour.
"""

from datetime import date

from step import constants, urgency as urgency_module

#: Reinforcing colour key -> the word the user actually reads.
URGENCY_LABELS = {
    constants.URGENCY_OVERDUE: "Late",
    constants.URGENCY_DUE_TODAY: "Due today",
    constants.URGENCY_DUE_SOON: "Due soon",
    constants.URGENCY_SCHEDULED: "Scheduled",
    constants.URGENCY_DONE: "Done",
}


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def due_phrase(obligation, today: date | None = None) -> str:
    """A whole sentence fragment about when this is due, in plain words."""
    today = today or date.today()

    if obligation.status == constants.STATUS_ACCEPTED:
        return "Accepted"
    if obligation.status in constants.AWAITING_REVIEW_STATUSES:
        return "Sent — waiting to be checked"

    days = (obligation.due_date - today).days
    if days < 0:
        return f"{_plural(abs(days), 'day')} late"
    if days == 0:
        return "Due today"
    if days == 1:
        return "Due tomorrow"
    return f"Due in {_plural(days, 'day')}"


def decorate(obligation, today: date | None = None) -> dict:
    """Everything a template needs about one obligation, precomputed.

    Templates stay dumb on purpose: the moment wording logic leaks into a
    template it stops being testable and starts drifting between pages.
    """
    today = today or date.today()

    if obligation.status == constants.STATUS_ACCEPTED:
        key, label = constants.URGENCY_DONE, "Accepted"
    elif obligation.status in constants.AWAITING_REVIEW_STATUSES:
        key, label = "review", "With reviewer"
    else:
        key = urgency_module.urgency_of(obligation, today)
        label = URGENCY_LABELS[key]
        # A returned submission is genuinely back with the teacher, and saying
        # so is more useful than repeating the deadline.
        if obligation.status == constants.STATUS_RETURNED:
            label = "Needs correction"

    return {
        "obligation": obligation,
        "urgency": key,
        "urgency_label": label,
        "due_phrase": due_phrase(obligation, today),
        "needs_action": obligation.status in {
            constants.STATUS_NOT_STARTED, constants.STATUS_RETURNED
        },
    }


def decorate_all(obligations, today: date | None = None) -> list[dict]:
    today = today or date.today()
    return [decorate(o, today) for o in obligations]


def evidence_instruction(obligation_type) -> str:
    """What the teacher must attach, said as an instruction rather than a spec."""
    minimum = obligation_type.min_count
    spec = obligation_type.evidence_spec

    if spec == constants.EVIDENCE_NONE:
        return "You do not need to attach anything."
    if spec == constants.EVIDENCE_LINK:
        return f"Add {_plural(minimum, 'link')} to your work."
    if spec == constants.EVIDENCE_FILE:
        return f"Attach {_plural(minimum, 'file')} — a photo or a PDF is fine."
    if spec == constants.EVIDENCE_EITHER:
        return "Add a link to your work, or attach a file. Either is fine."
    if spec == constants.EVIDENCE_BOTH:
        return "Add a link to your work and attach a file. Both are needed."
    return ""


def initials(name: str) -> str:
    """Two letters for the avatar. Falls back rather than showing nothing."""
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()
