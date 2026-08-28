"""The only place obligation status changes.

Centralised so that no view, admin action or management command can invent its
own transition. Everything that writes `Obligation.status` goes through here.
"""

from django.db import transaction
from django.utils import timezone

from step import constants
from step.models import Evidence, Obligation, ProgressEntry, Submission


class EvidenceRequired(Exception):
    """The submission does not satisfy the type's evidence_spec."""


class InvalidTransition(Exception):
    """The requested change is not legal from the current status."""


def _count(number: int, singular: str, plural: str) -> str:
    """Real pluralisation. "1 file(s)" is the kind of thing that tells a reader
    a machine wrote the sentence, and this service is used by people who are
    already unsure of themselves."""
    if number == 1:
        return f"a {singular}"
    return f"{number} {plural}"


def _check_evidence(obligation_type, evidence_items):
    """Raise EvidenceRequired unless the items satisfy the type.

    Messages are written for a person, not a developer: they say what to do
    next, in the same words the button uses, per spec §7.1.
    """
    spec = obligation_type.evidence_spec
    if spec == constants.EVIDENCE_NONE:
        return

    links = [e for e in evidence_items if e.get("kind") == constants.EVIDENCE_LINK_KIND]
    files = [e for e in evidence_items if e.get("kind") == constants.EVIDENCE_FILE_KIND]
    minimum = obligation_type.min_count

    if spec == constants.EVIDENCE_LINK and len(links) < minimum:
        raise EvidenceRequired(
            f"Please add {_count(minimum, 'link', 'links')} to your work before sending this in."
        )
    if spec == constants.EVIDENCE_FILE and len(files) < minimum:
        raise EvidenceRequired(
            f"Please attach {_count(minimum, 'file', 'files')} before sending this in. "
            "A photo taken on your phone is fine."
        )
    if spec == constants.EVIDENCE_EITHER and len(evidence_items) < minimum:
        raise EvidenceRequired(
            "Please add a link to your work, or attach a file, before sending this in."
        )
    if spec == constants.EVIDENCE_BOTH and (len(links) < minimum or len(files) < minimum):
        raise EvidenceRequired(
            "Please add a link to your work and attach a file. Both are needed before "
            "you can send this in."
        )


@transaction.atomic
def submit(obligation: Obligation, *, user, evidence, evaluation=None) -> Submission:
    """Record a submission, creating a new revision if this is a resubmission."""
    if obligation.status not in {constants.STATUS_NOT_STARTED, constants.STATUS_RETURNED}:
        raise InvalidTransition(
            f"{obligation.display_name} is {obligation.status}; it cannot be submitted again."
        )

    evidence = list(evidence or [])
    _check_evidence(obligation.type, evidence)

    previous = obligation.submissions.order_by("-revision").first()
    revision = (previous.revision + 1) if previous else 1

    fields = {"obligation": obligation, "revision": revision, "submitted_by": user}
    fields.update(evaluation or {})
    submission = Submission.objects.create(**fields)

    for item in evidence:
        Evidence.objects.create(
            submission=submission,
            kind=item.get("kind", constants.EVIDENCE_LINK_KIND),
            url=item.get("url", "") or "",
            file=item.get("file") or None,
            caption=item.get("caption", "") or "",
        )

    if obligation.type.requires_review:
        obligation.status = constants.STATUS_SUBMITTED
    else:
        obligation.status = constants.STATUS_ACCEPTED
    obligation.save(update_fields=["status"])

    return submission


@transaction.atomic
def accept(submission: Submission, *, reviewer) -> Submission:
    obligation = submission.obligation
    if obligation.status not in constants.AWAITING_REVIEW_STATUSES:
        raise InvalidTransition(f"{obligation.display_name} is not awaiting review.")

    submission.reviewed_by = reviewer
    submission.reviewed_at = timezone.now()
    submission.save(update_fields=["reviewed_by", "reviewed_at"])

    obligation.status = constants.STATUS_ACCEPTED
    obligation.save(update_fields=["status"])
    return submission


@transaction.atomic
def return_for_correction(submission: Submission, *, reviewer, comment: str) -> Submission:
    """Send it back. A comment is mandatory — "returned" with no reason is useless."""
    if not comment or not comment.strip():
        raise ValueError("A comment is required when returning a submission.")

    obligation = submission.obligation
    if obligation.status not in constants.AWAITING_REVIEW_STATUSES:
        raise InvalidTransition(f"{obligation.display_name} is not awaiting review.")

    submission.reviewed_by = reviewer
    submission.reviewed_at = timezone.now()
    submission.review_comment = comment.strip()
    submission.save(update_fields=["reviewed_by", "reviewed_at", "review_comment"])

    obligation.status = constants.STATUS_RETURNED
    obligation.save(update_fields=["status"])
    return submission


def review_queue():
    """Submissions waiting for an administrator's decision."""
    return (
        Submission.objects.filter(obligation__status__in=constants.AWAITING_REVIEW_STATUSES)
        .select_related("obligation", "obligation__type", "obligation__educator")
        .order_by("submitted_at")
    )


def feedback_for(educator):
    """Returned submissions the teacher still needs to act on."""
    return (
        Submission.objects.filter(
            obligation__educator=educator, obligation__status=constants.STATUS_RETURNED
        )
        .select_related("obligation", "obligation__type")
        .order_by("-reviewed_at")
    )


def sync_checkpoint(teaching_class, checkpoint: str) -> Obligation | None:
    """Settle a class's checkpoint obligation once every student has a
    structured entry for it.

    Bypasses `submit` deliberately: a checkpoint obligation has no evidence to
    check and nothing for a reviewer to decide (classes/gradebook spec,
    "Auto-completion"). No Submission row is created — callers must not assume
    one exists for these obligations.
    """
    total = teaching_class.students.count()
    if total == 0:
        return None

    scored = (
        ProgressEntry.objects.filter(student__teaching_class=teaching_class, checkpoint=checkpoint)
        .values("student").distinct().count()
    )
    if scored < total:
        return None

    name_template = constants.CHECKPOINT_OBLIGATION_NAME_TEMPLATES[checkpoint]
    obligation = Obligation.objects.filter(
        teaching_class=teaching_class, type__name_template=name_template
    ).first()
    if obligation is None or obligation.status == constants.STATUS_ACCEPTED:
        return obligation

    obligation.status = constants.STATUS_ACCEPTED
    obligation.save(update_fields=["status"])
    return obligation


def sync_activity_plan(activity_plan) -> Obligation | None:
    """Settle an ECA activity's monthly-plan obligation once all three
    fields are filled. Mirrors sync_checkpoint: no evidence to check and
    nothing for a reviewer to decide, so this bypasses submit() entirely.
    """
    fields = (activity_plan.overview, activity_plan.session_outline, activity_plan.intended_outcomes)
    if not all(field and field.strip() for field in fields):
        return None

    obligation = Obligation.objects.filter(
        activity=activity_plan.activity, period_start=activity_plan.period
    ).first()
    if obligation is None or obligation.status == constants.STATUS_ACCEPTED:
        return obligation

    obligation.status = constants.STATUS_ACCEPTED
    obligation.save(update_fields=["status"])
    return obligation
