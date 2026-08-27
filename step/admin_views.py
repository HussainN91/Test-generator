"""Administration screens: the action-queue dashboard, the submission review
workflow, and the teacher directory.

This module owns no business logic. Every state change goes through
`step.workflow`; every figure comes from `step.analytics`. A view here is
allowed to query and to shape context for a template, and nothing else.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render

from step import roles


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


@staff_required
def dashboard(request):
    context = {"nav": "dashboard"}
    context.update(_admin_chrome(request))
    return render(request, "step/admin/dashboard.html", context)
