"""The nine administration dashboard figures.

Computed live. At roughly 2,012 educators these are trivial aggregates given
the indexes already declared on Obligation, and precomputing them would buy
nothing while introducing a cache-invalidation bug (spec §6).

The metric definitions here are normative — spec §6.1. Note especially that
"pending" and "not started" are REPORTING categories derived from the due date;
they are not the stored `not_started` status.

Every function that returns self-reported data sets `self_reported: True` in
its payload, because these charts reach a ministry and must be labelled
(spec §5.10).
"""

from datetime import date

from django.db.models import Count

from step import constants
from step.models import AnnouncementResponse, Educator, Evidence, Obligation, Region, Session, Submission


def _percent(part: int, whole: int) -> float:
    return round(part * 100 / whole, 1) if whole else 0.0


def teachers_by_region():
    """Counts of active educators per region, largest first."""
    rows = (
        Educator.objects.filter(is_active=True, missing_from_last_import=False)
        .values("region__name")
        .annotate(count=Count("id"))
        .order_by("-count", "region__name")
    )
    return [{"region": r["region__name"], "count": r["count"]} for r in rows]


def _period_obligations(period_start: date):
    return Obligation.objects.filter(period_start=period_start)


def submission_status(period_start: date, today: date | None = None) -> dict:
    today = today or date.today()
    obligations = list(_period_obligations(period_start).only("status", "due_date"))

    total = len(obligations)
    submitted = sum(1 for o in obligations if o.status != constants.STATUS_NOT_STARTED)
    outstanding = [o for o in obligations if o.status == constants.STATUS_NOT_STARTED]
    pending = sum(1 for o in outstanding if o.due_date >= today)
    not_started = sum(1 for o in outstanding if o.due_date < today)

    return {
        "total": total,
        "submitted": submitted,
        "pending": pending,
        "not_started": not_started,
        "submitted_percent": _percent(submitted, total),
        "pending_percent": _percent(pending, total),
        "not_started_percent": _percent(not_started, total),
    }


def _latest_submissions(period_start: date):
    """The current revision of every submitted obligation in the period."""
    return Submission.objects.filter(obligation__period_start=period_start).order_by(
        "obligation_id", "-revision"
    ).distinct("obligation_id") if _supports_distinct_on() else _latest_submissions_portable(period_start)


def _supports_distinct_on() -> bool:
    """DISTINCT ON is Postgres-only; SQLite needs the portable path.

    The project runs SQLite today and Postgres later (spec §8), so both must
    work — otherwise the dashboard breaks on exactly the cutover it was
    designed for.
    """
    from django.db import connection
    return connection.vendor == "postgresql"


def _latest_submissions_portable(period_start: date):
    latest_ids = []
    seen = set()
    for submission in Submission.objects.filter(
        obligation__period_start=period_start
    ).order_by("obligation_id", "-revision").only("id", "obligation_id", "revision"):
        if submission.obligation_id in seen:
            continue
        seen.add(submission.obligation_id)
        latest_ids.append(submission.id)
    return Submission.objects.filter(id__in=latest_ids)


def rating_distribution(period_start: date) -> dict:
    """Director star ratings. SELF-REPORTED — see spec §5.10."""
    counts = {n: 0 for n in range(1, 6)}
    for submission in _latest_submissions(period_start).exclude(director_rating=None):
        counts[submission.director_rating] += 1
    total = sum(counts.values())
    return {
        "counts": counts,
        "percents": {n: _percent(c, total) for n, c in counts.items()},
        "total": total,
        "self_reported": True,
    }


def outcome_distribution(period_start: date) -> dict:
    """The binary outcome radio. SELF-REPORTED — see spec §5.10."""
    counts = {
        constants.OUTCOME_SATISFACTORY_OR_BETTER: 0,
        constants.OUTCOME_NEEDS_IMPROVEMENT: 0,
    }
    for submission in _latest_submissions(period_start).exclude(outcome=""):
        if submission.outcome in counts:
            counts[submission.outcome] += 1
    total = sum(counts.values())
    return {
        "counts": counts,
        "percents": {k: _percent(v, total) for k, v in counts.items()},
        "total": total,
        "self_reported": True,
    }


def timeliness(period_start: date) -> dict:
    """On-time vs late, and the average time taken. Spec §6.1 definitions."""
    on_time = late = 0
    durations = []

    for submission in _latest_submissions(period_start).select_related("obligation"):
        obligation = submission.obligation
        submitted_on = submission.submitted_at.date()
        if submitted_on <= obligation.due_date:
            on_time += 1
        else:
            late += 1
        durations.append((submission.submitted_at - obligation.opened_at).total_seconds() / 86400)

    total = on_time + late
    return {
        "on_time": on_time,
        "late": late,
        "on_time_percent": _percent(on_time, total),
        "late_percent": _percent(late, total),
        "average_submission_days": round(sum(durations) / len(durations), 1) if durations else 0.0,
    }


def status_by_region(period_start: date, today: date | None = None):
    """One row per region that has educators, for the stacked bar chart."""
    today = today or date.today()
    rows = []
    for region in Region.objects.filter(educators__isnull=False).distinct():
        obligations = list(
            _period_obligations(period_start).filter(educator__region=region).only("status", "due_date")
        )
        outstanding = [o for o in obligations if o.status == constants.STATUS_NOT_STARTED]
        rows.append({
            "region": region.name,
            "submitted": sum(1 for o in obligations if o.status != constants.STATUS_NOT_STARTED),
            "pending": sum(1 for o in outstanding if o.due_date >= today),
            "not_started": sum(1 for o in outstanding if o.due_date < today),
        })
    return sorted(rows, key=lambda r: -(r["submitted"] + r["pending"] + r["not_started"]))


def submission_trend(period_start: date):
    """Cumulative submission percentage across the period, one point per day."""
    from step.scheduling import period_end

    finish = period_end(period_start, constants.PERIOD_MONTH)
    total = _period_obligations(period_start).count()

    dates = sorted(
        s.submitted_at.date() for s in _latest_submissions(period_start).only("submitted_at")
    )

    points = []
    cumulative = 0
    index = 0
    day = period_start
    while day <= finish:
        while index < len(dates) and dates[index] <= day:
            cumulative += 1
            index += 1
        points.append({"date": day.isoformat(), "cumulative_percent": _percent(cumulative, total)})
        day = date.fromordinal(day.toordinal() + 1)
    return points


def completeness_rate(period_start: date) -> float:
    """Share of required evidence slots actually filled.

    PROVISIONAL definition — the client mockup does not define this figure and
    it needs confirmation (spec §6.1, open question 3).
    """
    required = filled = 0
    for submission in _latest_submissions(period_start).select_related("obligation__type"):
        obligation_type = submission.obligation.type
        if obligation_type.evidence_spec == constants.EVIDENCE_NONE:
            continue
        need = obligation_type.min_count
        if obligation_type.evidence_spec == constants.EVIDENCE_BOTH:
            need *= 2
        required += need
        filled += min(Evidence.objects.filter(submission=submission).count(), need)
    return _percent(filled, required)


def activity_by_region(period_start: date) -> list[dict]:
    """One row per region with eligible educators, counts spanning all four
    verticals (fix step plan.md §6). Every column is scoped to the same
    `generation.eligible_educators()` predicate `teachers_by_region()` above
    uses, so this chart and the RSVP view can never disagree about who is
    being counted.

    CPD Online responses are scoped by `Announcement.published_at`
    (auto_now_add, immutable), never `AnnouncementResponse.responded_at`
    (auto_now — it rewrites on every RSVP change, so a September edit to a
    July announcement would silently move that answer into September's
    figure). This matches `_period_obligations()` above: a row belongs to
    the period it originated in, not the period someone later acted on it.

    Counts every response regardless of `attending` — this measures
    engagement with the announcement, not turnout. Whether "responses"
    should mean attendees only is an open question put to the client;
    if it comes back that way, only the `.count()` call below changes.
    """
    from step.generation import eligible_educators
    from step.scheduling import period_end

    finish = period_end(period_start, constants.PERIOD_MONTH)
    rows = []
    for region in Region.objects.filter(id__in=eligible_educators().values("region_id")).distinct():
        educators = eligible_educators().filter(region=region)

        monthly_reports = (
            Obligation.objects.filter(
                type__category=constants.CATEGORY_MONTHLY_REPORTING,
                period_start=period_start,
                educator__in=educators,
            )
            .exclude(status=constants.STATUS_NOT_STARTED)
            .count()
        )
        cpd_online_responses = AnnouncementResponse.objects.filter(
            educator__in=educators,
            # __date, not __range, on this DateTimeField: period_end is an
            # inclusive `date`, and a plain __range coerces it to midnight,
            # silently dropping everything published on the month's last day.
            announcement__published_at__date__range=(period_start, finish),
        ).count()
        cpd_offline_sessions = Session.objects.filter(
            activity__kind=constants.ACTIVITY_KIND_CPD_OFFLINE,
            status=constants.SESSION_STATUS_HELD,
            held_on__range=(period_start, finish),
            activity__educator__in=educators,
        ).count()
        eca_sessions = Session.objects.filter(
            activity__kind=constants.ACTIVITY_KIND_ECA,
            status=constants.SESSION_STATUS_HELD,
            held_on__range=(period_start, finish),
            activity__educator__in=educators,
        ).count()

        rows.append({
            "region": region.name,
            "monthly_reports": monthly_reports,
            "cpd_online_responses": cpd_online_responses,
            "cpd_offline_sessions": cpd_offline_sessions,
            "eca_sessions": eca_sessions,
        })
    return sorted(
        rows,
        key=lambda r: -(
            r["monthly_reports"] + r["cpd_online_responses"]
            + r["cpd_offline_sessions"] + r["eca_sessions"]
        ),
    )


def sessions_held(period_start: date) -> int:
    """Total Activity sessions logged as held in the period, across both
    verticals — the headline figure alongside `activity_by_region()`
    (fix step plan.md item 18)."""
    from step.scheduling import period_end

    finish = period_end(period_start, constants.PERIOD_MONTH)
    return Session.objects.filter(
        status=constants.SESSION_STATUS_HELD,
        held_on__range=(period_start, finish),
    ).count()
