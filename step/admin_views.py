"""Administration screens: the action-queue dashboard, the submission review
workflow, and the teacher directory.

This module owns no business logic. Every state change goes through
`step.workflow`; every figure comes from `step.analytics`. A view here is
allowed to query and to shape context for a template, and nothing else.
"""

from datetime import date
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import render

from step import analytics, constants, roles, workflow
from step.models import Obligation


def staff_required(view):
    """Only the three staff roles reach anything in this module (spec §5.6).

    A plain 403 with words a confused administrator can act on — not a stack
    trace, not a silent bounce back to their own dashboard.
    """
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not roles.is_staff_role(request.user):
            return HttpResponseForbidden(
                "This area is for programme staff. If you believe this is a mistake, "
                "contact your System Administrator."
            )
        return view(request, *args, **kwargs)
    return wrapped


def _admin_chrome(request) -> dict:
    """Context every admin screen's shell needs — the admin equivalent of
    step/views.py's `_chrome`, kept separate because the two shells show
    different things (a staff member's name and role, not a teacher's school
    and file reference)."""
    return {
        "lh_who": request.user.get_username(),
        "lh_where": "Administration",
    }


def _current_period(request) -> date:
    """The month the dashboard reports on. `?period=YYYY-MM`, defaulting to
    the current month. A malformed value 404s rather than silently showing
    the wrong month — a teacher-facing default (September) sitting under a
    ministry figure is worse than an obvious error page.
    """
    raw = request.GET.get("period")
    if not raw:
        return date.today().replace(day=1)
    try:
        year, month = raw.split("-")
        return date(int(year), int(month), 1)
    except (ValueError, TypeError) as exc:
        raise Http404("That is not a month this dashboard understands.") from exc


@staff_required
def dashboard(request):
    period = _current_period(request)
    headline = analytics.submission_status(period)
    outstanding_count = (
        Obligation.objects.filter(period_start=period, status=constants.STATUS_NOT_STARTED)
        .values("educator_id").distinct().count()
    )
    review_count = workflow.review_queue().count()

    context = {
        "nav": "dashboard",
        "period": period,
        "headline": headline,
        "outstanding_count": outstanding_count,
        "review_count": review_count,
    }
    context.update(_admin_chrome(request))
    return render(request, "step/admin/dashboard.html", context)
