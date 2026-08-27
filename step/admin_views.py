"""Administration screens: the action-queue dashboard, the submission review
workflow, and the teacher directory.

This module owns no business logic. Every state change goes through
`step.workflow`; every figure comes from `step.analytics`. A view here is
allowed to query and to shape context for a template, and nothing else.
"""

from datetime import date
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from step import analytics, constants, roles, workflow
from step.models import Obligation, Submission


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


def _region_bars(rows: list[dict]) -> list[dict]:
    """`analytics.teachers_by_region()`'s rows, with a 0-100 `percent` of the
    largest region added — `.bar__fill`'s width is an inline style per the
    primitive's contract, and that arithmetic belongs here, not in the
    template."""
    maximum = rows[0]["count"] if rows else 0
    return [
        {**row, "percent": round(row["count"] / maximum * 100, 1) if maximum else 0.0}
        for row in rows
    ]


def _status_rows(rows: list[dict]) -> list[dict]:
    """`analytics.status_by_region()`'s rows, with each of the three counts
    turned into a percentage of that row's own total, for `.stack__seg`
    widths."""
    out = []
    for row in rows:
        total = row["submitted"] + row["pending"] + row["not_started"]
        out.append({
            **row,
            "submitted_percent": round(row["submitted"] / total * 100, 1) if total else 0.0,
            "pending_percent": round(row["pending"] / total * 100, 1) if total else 0.0,
            "not_started_percent": round(row["not_started"] / total * 100, 1) if total else 0.0,
        })
    return out


def _donut_segments(parts: list[tuple]) -> list[dict]:
    """`parts` is `[(series_css_class, percent), ...]`. Returns the
    `stroke-dasharray`/`stroke-dashoffset` pairs the `.donut__seg` primitive
    needs. The circle's circumference is exactly 100 (r=15.915), so a segment
    covering `pct` percent of the circle is `dasharray="{pct} {100-pct}"`.
    Offsets start at 25 (12 o'clock) and chain around the circle — this is
    test-generator-16's verified contract for static/css/step.css §17, not an
    independent derivation.
    """
    segments = []
    offset = 25.0
    for series_class, pct in parts:
        segments.append({
            "series": series_class,
            "dasharray": f"{pct} {100 - pct}",
            "dashoffset": round(offset, 2),
        })
        offset = (offset - pct + 100) % 100
    return segments


def _trend_points(points: list[dict]) -> tuple[str, int]:
    """`analytics.submission_trend()`'s points, turned into an SVG
    `points="x,y"` attribute plus the `viewBox` width to pair with it. X is
    the raw day index (0, 1, 2, ...) and y is inverted (100 - percentage);
    `preserveAspectRatio="none"` stretches the box to fit its container, so
    there is no need to scale x to any particular unit.
    """
    coords = " ".join(
        f"{i},{100 - point['cumulative_percent']}" for i, point in enumerate(points)
    )
    width = max(len(points) - 1, 1)
    return coords, width


RATING_SERIES = [(5, "s-violet"), (4, "s-teal"), (3, "s-ochre"), (2, "s-umber"), (1, "s-plum")]


@staff_required
def dashboard(request):
    period = _current_period(request)
    headline = analytics.submission_status(period)
    outstanding_count = (
        Obligation.objects.filter(period_start=period, status=constants.STATUS_NOT_STARTED)
        .values("educator_id").distinct().count()
    )
    review_count = workflow.review_queue().count()

    rating = analytics.rating_distribution(period)
    outcome = analytics.outcome_distribution(period)
    trend_coords, trend_width = _trend_points(analytics.submission_trend(period))

    context = {
        "nav": "dashboard",
        "period": period,
        "headline": headline,
        "outstanding_count": outstanding_count,
        "review_count": review_count,
        "region_bars": _region_bars(analytics.teachers_by_region()),
        "rating_distribution": rating,
        "rating_donut": _donut_segments(
            [(cls, rating["percents"][n]) for n, cls in RATING_SERIES]
        ),
        "outcome_distribution": outcome,
        "outcome_donut": _donut_segments([
            ("s-teal", outcome["percents"][constants.OUTCOME_SATISFACTORY_OR_BETTER]),
            ("s-ochre", outcome["percents"][constants.OUTCOME_NEEDS_IMPROVEMENT]),
        ]),
        "trend_points": trend_coords,
        "trend_width": trend_width,
        "status_rows": _status_rows(analytics.status_by_region(period)),
        "timeliness": analytics.timeliness(period),
        "completeness_rate": analytics.completeness_rate(period),
    }
    context.update(_admin_chrome(request))
    return render(request, "step/admin/dashboard.html", context)


@staff_required
def review_queue(request):
    context = {"nav": "review", "rows": workflow.review_queue()}
    context.update(_admin_chrome(request))
    return render(request, "step/admin/review_queue.html", context)


@staff_required
def review_detail(request, pk: int):
    submission = get_object_or_404(
        Submission.objects.select_related("obligation", "obligation__type", "obligation__educator"),
        pk=pk,
    )

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "accept":
            workflow.accept(submission, reviewer=request.user)
            messages.success(request, "Accepted.")
            return redirect("step:admin-review-queue")
        if action == "return":
            comment = (request.POST.get("comment") or "").strip()
            try:
                workflow.return_for_correction(submission, reviewer=request.user, comment=comment)
            except ValueError:
                messages.error(
                    request, "Please explain what needs correcting before returning this."
                )
                context = {
                    "nav": "review", "submission": submission,
                    "evidence": submission.evidence.all(),
                    "is_monthly_report": (
                        submission.obligation.type.category == constants.CATEGORY_MONTHLY_REPORTING
                    ),
                }
                context.update(_admin_chrome(request))
                return render(request, "step/admin/review_detail.html", context)
            messages.success(request, "Returned to the teacher.")
            return redirect("step:admin-review-queue")

    context = {
        "nav": "review",
        "submission": submission,
        "evidence": submission.evidence.all(),
        "is_monthly_report": submission.obligation.type.category == constants.CATEGORY_MONTHLY_REPORTING,
    }
    context.update(_admin_chrome(request))
    return render(request, "step/admin/review_detail.html", context)
