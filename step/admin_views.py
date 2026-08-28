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
from django.core.paginator import Paginator
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from step import analytics, constants, presentation, roles, workflow
from step.models import Announcement, Educator, Obligation, Region, Submission


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


def programme_admin_required(view):
    """Publishing an announcement is narrower than the other staff screens
    (fix step plan §5.2): only Programme Admin, not the other two staff
    roles, to stop several administrators broadcasting contradictory
    messages to ~2,000 teachers."""
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not roles.can_publish_announcements(request.user):
            return HttpResponseForbidden(
                "Publishing announcements is limited to Programme Admin. If you believe "
                "this is a mistake, contact your System Administrator."
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


def _activity_bars(rows: list[dict]) -> list[dict]:
    """`analytics.activity_by_region()`'s rows, with each of the four columns
    turned into a 0-100 `percent` of THAT COLUMN's own largest region — never
    a shared scale across columns. A monthly-report count and a session
    count are different units (fix step plan §3.6 puts sessions at roughly
    30x reports per teacher per month); one shared scale would render the
    reports column as a hairline next to the session columns and imply a
    comparison that means nothing (`.mini-bar__fill`'s contract, §17.6)."""
    columns = ["monthly_reports", "cpd_online_responses", "cpd_offline_sessions", "eca_sessions"]
    maxima = {column: max((row[column] for row in rows), default=0) for column in columns}
    out = []
    for row in rows:
        entry = dict(row)
        for column in columns:
            entry[f"{column}_percent"] = (
                round(row[column] / maxima[column] * 100, 1) if maxima[column] else 0.0
            )
        out.append(entry)
    return out


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
        "activity_bars": _activity_bars(analytics.activity_by_region(period)),
        "sessions_held": analytics.sessions_held(period),
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


@staff_required
def teacher_directory(request):
    query = (request.GET.get("q") or "").strip()
    # `region` arrives from a URL and may be anything. Passing it straight to
    # `filter(region_id=...)` raised ValueError — a 500 — on any non-numeric
    # value. Junk is dropped rather than 404'd, matching how `?page=` already
    # behaves; `?period=` 404s instead because a silently wrong month under a
    # ministry figure is a different order of harm from a filter that reset.
    region_id = (request.GET.get("region") or "").strip()
    if not region_id.isdigit():
        region_id = ""
    status = request.GET.get("status") or ""
    period = _current_period(request)

    educators = Educator.objects.filter(is_active=True).select_related("region", "school")
    if query:
        educators = educators.filter(full_name__icontains=query)
    if region_id:
        # An unknown-but-numeric id still narrows to nothing, which is honest:
        # the filter was understood and matched no one.
        educators = educators.filter(region_id=int(region_id))
    if status == "outstanding":
        outstanding_ids = Obligation.objects.filter(
            period_start=period, status=constants.STATUS_NOT_STARTED
        ).values_list("educator_id", flat=True)
        educators = educators.filter(id__in=outstanding_ids)

    paginator = Paginator(educators, 50)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "nav": "teachers",
        "page": page,
        "query": query,
        "regions": Region.objects.all(),
        "selected_region": region_id,
        "status": status,
        "period": period,
    }
    context.update(_admin_chrome(request))
    return render(request, "step/admin/teacher_directory.html", context)


@staff_required
def teacher_detail(request, pk: int):
    educator = get_object_or_404(Educator.objects.select_related("region", "school"), pk=pk)
    obligations = educator.obligations.select_related("type").order_by("-due_date")
    context = {
        "nav": "teachers",
        "educator": educator,
        "file_ref": presentation.file_reference(educator),
        "items": presentation.decorate_all(obligations, date.today()),
    }
    context.update(_admin_chrome(request))
    return render(request, "step/admin/teacher_detail.html", context)


@staff_required
def announcement_list(request):
    """The RSVP view (fix step plan item 17): coming / not coming / not yet
    answered, per announcement. "Not yet answered" only means something for
    an announcement that asked for an answer — pure news has no such figure
    (`Announcement.requires_response`, spec §5.3)."""
    from step.generation import eligible_educators

    total_eligible = eligible_educators().count()
    rows = []
    for announcement in Announcement.objects.order_by("-published_at"):
        row = {"announcement": announcement}
        if announcement.requires_response:
            attending = announcement.responses.filter(attending=True).count()
            not_attending = announcement.responses.filter(attending=False).count()
            row["attending"] = attending
            row["not_attending"] = not_attending
            row["not_answered"] = max(total_eligible - attending - not_attending, 0)
        rows.append(row)

    context = {
        "nav": "announcements",
        "rows": rows,
        "can_publish": roles.can_publish_announcements(request.user),
    }
    context.update(_admin_chrome(request))
    return render(request, "step/admin/announcement_list.html", context)


@programme_admin_required
def announcement_create(request):
    context = {"nav": "announcements", "form": {}}

    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        body = (request.POST.get("body") or "").strip()
        requires_response = request.POST.get("requires_response") == "on"
        respond_by_raw = (request.POST.get("respond_by") or "").strip()

        error = None
        respond_by = None

        if not title:
            error = "Enter a title for this announcement."
        elif not body:
            error = "Enter the details teachers will see."
        elif respond_by_raw:
            try:
                respond_by = date.fromisoformat(respond_by_raw)
            except ValueError:
                error = "That date is not valid."

        if error is None:
            Announcement.objects.create(
                created_by=request.user, title=title, body=body,
                requires_response=requires_response, respond_by=respond_by,
            )
            messages.success(request, f'"{title}" has been published.')
            return redirect("step:admin-announcements")

        messages.error(request, error)
        context["form"] = {
            "title": title, "body": body,
            "requires_response": requires_response, "respond_by": respond_by_raw,
        }

    context.update(_admin_chrome(request))
    return render(request, "step/admin/announcement_create.html", context)
