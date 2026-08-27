"""Educator-facing screens.

Structured around GOV.UK's "one thing per page" (spine spec §7.0-7.2): the
dashboard answers *what do I do next*, and every obligation opens onto a single
screen with a single job. There are no modals, no multi-purpose screens, and no
place where a teacher is asked two unrelated questions at once.

Views stay thin. Wording lives in `step.presentation`, state changes live in
`step.workflow`, and figures live in `step.urgency` — so none of it can drift
between here and the administration screens.
"""

from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from step import constants, presentation, urgency, workflow
from step.models import AcademicYear, Educator, Obligation, Submission


def _educator(request) -> Educator:
    """The roster row behind the signed-in user.

    A user with no educator row is not an error to swallow: it means signup
    never matched the roster, and the person needs telling, not a blank page.
    """
    educator = Educator.objects.filter(user=request.user).select_related("region", "school").first()
    if educator is None:
        raise Http404("This account is not linked to a teacher record yet.")
    return educator


def _chrome(educator) -> dict:
    """Context every screen's shell needs.

    `file_ref` is a real reference, not decoration: the letterhead (UI contract
    §5.1) shows it the way an official file would, and it is what a teacher
    would quote if they rang someone about their record.
    """
    return {
        "educator": educator,
        "file_ref": presentation.file_reference(educator),
        # The rail renders the category filters on every page, so this cannot
        # live only in the dashboard's context.
        "categories": constants.CATEGORY_CHOICES,
        "returned_count": educator.obligations.filter(
            status=constants.STATUS_RETURNED
        ).count(),
    }


@login_required
def dashboard(request):
    educator = _educator(request)
    today = date.today()

    obligations = (
        educator.obligations.select_related("type").order_by("due_date")
    )

    active_category = request.GET.get("category") or ""
    valid = {key for key, _ in constants.CATEGORY_CHOICES}
    if active_category and active_category not in valid:
        active_category = ""
    if active_category:
        obligations = obligations.filter(type__category=active_category)

    items = presentation.decorate_all(obligations, today)

    # Outstanding first, then by date — a teacher does not care that something
    # finished in September when three things are late today.
    items.sort(key=lambda i: (not i["needs_action"], i["obligation"].due_date))

    next_obligation = urgency.next_action(educator, today=today)
    year = AcademicYear.objects.filter(is_current=True).prefetch_related("terms").first()

    terms = []
    for term in (year.terms.all() if year else []):
        term.is_current = term.start <= today <= term.end
        terms.append(term)

    deadlines = [i for i in items if i["needs_action"]][:4]

    context = {
        "nav": "work",
        "items": items,
        "next_item": presentation.decorate(next_obligation, today) if next_obligation else None,
        "tiles": urgency.teacher_tiles(educator, today=today),
        "this_month": today.strftime("%B %Y"),
        "active_category": active_category,
        "deadlines": deadlines,
        "academic_year": year,
        "terms": terms,
    }
    context.update(_chrome(educator))
    return render(request, "step/dashboard.html", context)


@login_required
def obligation(request, pk: int):
    """One obligation, one screen, one job."""
    educator = _educator(request)
    today = date.today()

    obligation_obj = get_object_or_404(
        Obligation.objects.select_related("type", "educator"),
        pk=pk,
        educator=educator,
    )

    if request.method == "POST":
        return _handle_submit(request, educator, obligation_obj)

    latest = obligation_obj.latest_submission
    history = list(obligation_obj.submissions.select_related("reviewed_by").order_by("-revision"))

    context = {
        "nav": "work",
        "item": presentation.decorate(obligation_obj, today),
        "instruction": presentation.evidence_instruction(obligation_obj.type),
        "spec": obligation_obj.type.evidence_spec,
        "wants_link": obligation_obj.type.evidence_spec in {
            constants.EVIDENCE_LINK, constants.EVIDENCE_EITHER, constants.EVIDENCE_BOTH
        },
        "wants_file": obligation_obj.type.evidence_spec in {
            constants.EVIDENCE_FILE, constants.EVIDENCE_EITHER, constants.EVIDENCE_BOTH
        },
        "is_monthly_report": obligation_obj.type.category == constants.CATEGORY_MONTHLY_REPORTING,
        "rating_choices": constants.DIRECTOR_RATING_CHOICES,
        "outcome_choices": constants.OUTCOME_CHOICES,
        "latest": latest,
        "history": history,
        "can_submit": obligation_obj.status in {
            constants.STATUS_NOT_STARTED, constants.STATUS_RETURNED
        },
    }
    context.update(_chrome(educator))
    return render(request, "step/obligation.html", context)


def _handle_submit(request, educator, obligation_obj):
    """Collect the form into the shape `workflow.submit` expects.

    Validation errors come back as messages written for a person: they say what
    to do next rather than naming the rule that failed.
    """
    evidence = []

    link = (request.POST.get("link") or "").strip()
    if link:
        evidence.append({
            "kind": constants.EVIDENCE_LINK_KIND,
            "url": link,
            "caption": (request.POST.get("link_caption") or "").strip(),
        })

    for uploaded in request.FILES.getlist("file"):
        evidence.append({
            "kind": constants.EVIDENCE_FILE_KIND,
            "file": uploaded,
            "caption": uploaded.name,
        })

    evaluation = {}
    if obligation_obj.type.category == constants.CATEGORY_MONTHLY_REPORTING:
        rating = (request.POST.get("director_rating") or "").strip()
        if rating.isdigit():
            evaluation["director_rating"] = int(rating)
        evaluation["director_name"] = (request.POST.get("director_name") or "").strip()
        evaluation["director_comments"] = (request.POST.get("director_comments") or "").strip()
        outcome = (request.POST.get("outcome") or "").strip()
        if outcome in dict(constants.OUTCOME_CHOICES):
            evaluation["outcome"] = outcome

    try:
        workflow.submit(
            obligation_obj,
            user=request.user,
            evidence=evidence,
            evaluation=evaluation or None,
        )
    except workflow.EvidenceRequired as exc:
        messages.error(request, str(exc))
        return redirect("step:obligation", pk=obligation_obj.pk)
    except workflow.InvalidTransition as exc:
        messages.error(request, str(exc))
        return redirect("step:obligation", pk=obligation_obj.pk)

    obligation_obj.refresh_from_db()
    if obligation_obj.status == constants.STATUS_ACCEPTED:
        messages.success(request, "Thank you — that is complete. Nothing further to do.")
    else:
        messages.success(request, "Thank you — that has been sent for checking.")
    return redirect("step:obligation", pk=obligation_obj.pk)


@login_required
def submissions(request):
    educator = _educator(request)
    rows = (
        Submission.objects.filter(obligation__educator=educator)
        .select_related("obligation", "obligation__type")
        .order_by("-submitted_at")
    )
    context = {"nav": "submissions", "rows": rows}
    context.update(_chrome(educator))
    return render(request, "step/submissions.html", context)


@login_required
def feedback(request):
    """Only what came back and still needs the teacher's attention."""
    educator = _educator(request)
    rows = workflow.feedback_for(educator)
    context = {"nav": "feedback", "rows": rows}
    context.update(_chrome(educator))
    return render(request, "step/feedback.html", context)
