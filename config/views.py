"""Cross-app routing that belongs to no single app.

The site is three things behind one sign-in — the Test Generator, diagnostics,
and STEP — so "where does a person go after signing in" is a question none of
those apps can answer on its own. It lives here.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from step import roles
from step.models import Educator


@login_required
def post_login(request):
    """Send each person to the screen their role makes sense on.

    A fixed `LOGIN_REDIRECT_URL` cannot do this: it landed everyone on the
    Test Generator, including programme staff and teachers who have no
    business there. Staff are checked first because a staff account never
    accrues obligations (spec §5.6) and so has no teacher record to show.
    """
    if roles.is_staff_role(request.user):
        return redirect("step:admin-dashboard")

    # The roster importer links an Educator row to a user without assigning
    # the Educator group (only self-signup does), so a roster-imported teacher
    # is recognised by their record, not by their group membership.
    if roles.is_educator(request.user) or Educator.objects.filter(user=request.user).exists():
        return redirect("step:dashboard")

    return redirect("builder")
