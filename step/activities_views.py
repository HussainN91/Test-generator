"""Screens for a teacher's own ECA Programme and CPD Offline activities:
building a roster and logging sessions.

Kept out of step/views.py deliberately, mirroring step/classes_views.py's own
precedent — a new vertical's screens live in their own <name>_views.py /
<name>_urls.py pair. `_educator`/`_chrome` are duplicated here rather than
imported from either sibling module: step/views.py and step/classes_views.py
already duplicate this exact two-function pair between themselves, so this
follows that established choice rather than introducing a shared-import
dependency that doesn't otherwise exist in this codebase.

Logging a session (activity_session_log) is the one screen the whole vertical
exists for: a 20-second confirm-everyone-showed-up act, not data entry (fix
step plan design context). Everything else here exists to get a roster in
place so that screen has someone to tick off.
"""

import urllib.request
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from step import constants, generation, presentation, scheduling
from step.models import (
    Activity, ActivityParticipant, Educator, Obligation, School, SchoolStaff, Session,
    SessionAttendance, TeachingClass,
)

#: Monday=0 ... Sunday=6, matching date.weekday() and scheduling.session_dates.
WEEKDAY_CHOICES = [(0, "Mon"), (1, "Tue"), (2, "Wed"), (3, "Thu"), (4, "Fri"), (5, "Sat"), (6, "Sun")]


def _educator(request) -> Educator:
    educator = Educator.objects.filter(user=request.user).select_related("region", "school").first()
    if educator is None:
        raise Http404("This account is not linked to a teacher record yet.")
    return educator


def _chrome(educator) -> dict:
    return {
        "educator": educator,
        "file_ref": presentation.file_reference(educator),
        "categories": constants.CATEGORY_CHOICES,
        "returned_count": educator.obligations.filter(status=constants.STATUS_RETURNED).count(),
    }


def _link_looks_reachable(url: str) -> bool:
    """Best-effort HEAD check. Never allowed to block or crash session
    logging (fix step plan §3.7) — wrapped in a broad except on purpose.

    Uses the standard library rather than `requests`: nothing else in this
    codebase depends on `requests` as an HTTP client (it is only a locked
    transitive dependency), so this doesn't add one just for a single
    non-blocking reachability check.
    """
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=3) as response:
            return 200 <= response.status < 400
    except Exception:
        return False


@login_required
def activity_list(request):
    educator = _educator(request)
    today = date.today()

    rows = []
    for activity in educator.activities.select_related("school").all():
        due_count = activity.sessions.filter(
            status=constants.SESSION_STATUS_EXPECTED, scheduled_for__lte=today
        ).count()
        rows.append({"activity": activity, "due_count": due_count})

    context = {"nav": "activities", "rows": rows}
    context.update(_chrome(educator))
    return render(request, "step/activities/list.html", context)


@login_required
def activity_create(request):
    educator = _educator(request)

    context = {
        "nav": "activities",
        "kind_choices": constants.ACTIVITY_KIND_CHOICES,
        "weekday_choices": WEEKDAY_CHOICES,
        "schools": School.objects.order_by("name"),
        "today_iso": date.today().isoformat(),
        "form": {},
    }

    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        kind = request.POST.get("kind") or ""
        weekdays = sorted({
            int(value) for value in request.POST.getlist("weekdays")
            if value.isdigit() and 0 <= int(value) <= 6
        })
        started_raw = (request.POST.get("started_on") or "").strip()
        school_id = (request.POST.get("school") or "").strip()

        error = None
        started_on = date.today()

        if not title:
            error = "Enter a name for this activity."
        elif kind not in dict(constants.ACTIVITY_KIND_CHOICES):
            error = "Choose ECA Programme or CPD Offline."
        elif not weekdays:
            error = "Choose at least one day of the week this meets."
        elif started_raw:
            try:
                started_on = date.fromisoformat(started_raw)
            except ValueError:
                error = "That start date is not valid."

        school = None
        if error is None and school_id:
            school = School.objects.filter(pk=school_id).first()
            if school is None:
                error = "Choose a real school from the list."

        if error is None and kind == constants.ACTIVITY_KIND_CPD_OFFLINE and school is None:
            error = (
                "CPD Offline needs a school, so its staff list can be shared with "
                "other teachers there."
            )

        if error is None:
            activity = Activity.objects.create(
                educator=educator, kind=kind, title=title, school=school,
                schedule_rule={"weekdays": weekdays}, started_on=started_on,
            )
            generation.on_activity_created(activity)
            messages.success(request, f"{title} has been created. Now add who takes part.")
            return redirect("step:activity_participant_create", pk=activity.pk)

        messages.error(request, error)
        context["form"] = {
            "title": title, "kind": kind, "weekdays": weekdays,
            "started_on": started_raw, "school": school_id,
        }

    context.update(_chrome(educator))
    return render(request, "step/activities/create.html", context)


@login_required
def activity_participant_create(request, pk: int):
    educator = _educator(request)
    activity = get_object_or_404(Activity, pk=pk, educator=educator)

    context = {"nav": "activities", "activity": activity}

    if activity.kind == constants.ACTIVITY_KIND_ECA:
        context["classes"] = educator.classes.prefetch_related("students").all()

        if request.method == "POST":
            added = 0
            class_pk = (request.POST.get("from_class") or "").strip()
            if class_pk:
                teaching_class = TeachingClass.objects.filter(pk=class_pk, educator=educator).first()
                if teaching_class is not None:
                    existing_student_ids = set(
                        activity.participants.exclude(student=None)
                        .values_list("student_id", flat=True)
                    )
                    for student in teaching_class.students.all():
                        if student.pk in existing_student_ids:
                            continue
                        ActivityParticipant.objects.create(
                            activity=activity, full_name=student.full_name, student=student,
                        )
                        added += 1

            typed_name = (request.POST.get("full_name") or "").strip()
            if typed_name:
                ActivityParticipant.objects.create(activity=activity, full_name=typed_name)
                added += 1

            if added:
                messages.success(request, "%d participant(s) added." % added)
            else:
                messages.error(request, "Pick a class to add, or type a name.")
            return redirect("step:activity_detail", pk=activity.pk)

    else:  # CPD Offline
        if activity.school is None:
            context["needs_school"] = True
        else:
            existing_staff_ids = set(
                activity.participants.exclude(staff=None).values_list("staff_id", flat=True)
            )
            context["staff_choices"] = SchoolStaff.objects.filter(school=activity.school).exclude(
                pk__in=existing_staff_ids
            )

            if request.method == "POST":
                added = 0
                for staff_pk in request.POST.getlist("staff"):
                    staff = SchoolStaff.objects.filter(pk=staff_pk, school=activity.school).first()
                    if staff is None:
                        continue
                    if activity.participants.filter(staff=staff).exists():
                        continue
                    ActivityParticipant.objects.create(
                        activity=activity, staff=staff, full_name=staff.full_name,
                    )
                    added += 1

                typed_name = (request.POST.get("full_name") or "").strip()
                if typed_name:
                    # Shared across every teacher at this school (fix step plan
                    # §3.3): created once here, then offered as a pick next time.
                    staff = SchoolStaff.objects.create(school=activity.school, full_name=typed_name)
                    ActivityParticipant.objects.create(
                        activity=activity, staff=staff, full_name=typed_name,
                    )
                    added += 1

                if added:
                    messages.success(request, "%d participant(s) added." % added)
                else:
                    messages.error(request, "Choose someone from the list, or type a new name.")
                return redirect("step:activity_detail", pk=activity.pk)

    context.update(_chrome(educator))
    return render(request, "step/activities/participant_create.html", context)


@login_required
def activity_detail(request, pk: int):
    educator = _educator(request)
    activity = get_object_or_404(Activity.objects.select_related("school"), pk=pk, educator=educator)
    today = date.today()

    sessions = list(activity.sessions.all())
    due_sessions = [
        s for s in sessions
        if s.status == constants.SESSION_STATUS_EXPECTED and s.scheduled_for <= today
    ]

    plan_obligation = None
    if activity.kind == constants.ACTIVITY_KIND_ECA:
        month_start = scheduling.period_start_for(today, constants.PERIOD_MONTH)
        plan_obligation = Obligation.objects.filter(activity=activity, period_start=month_start).first()

    context = {
        "nav": "activities",
        "activity": activity,
        "participants": activity.participants.all(),
        "sessions": sessions,
        "due_sessions": due_sessions,
        "plan_obligation": plan_obligation,
        "today": today,
        "today_iso": today.isoformat(),
    }
    context.update(_chrome(educator))
    return render(request, "step/activities/detail.html", context)


@login_required
def activity_session_create(request, pk: int):
    """An off-schedule extra session for an arbitrary date. Creates it
    `expected`, then sends the teacher straight to logging it — there is
    nothing else to do with a bare session row."""
    educator = _educator(request)
    activity = get_object_or_404(Activity, pk=pk, educator=educator)

    if request.method != "POST":
        raise Http404("This page only accepts a submitted date.")

    raw = (request.POST.get("scheduled_for") or "").strip()
    try:
        scheduled_for = date.fromisoformat(raw)
    except ValueError:
        messages.error(request, "Choose a real date for the extra session.")
        return redirect("step:activity_detail", pk=activity.pk)

    session, _created = Session.objects.get_or_create(
        activity=activity, scheduled_for=scheduled_for,
        defaults={"status": constants.SESSION_STATUS_EXPECTED},
    )
    return redirect("step:activity_session_log", pk=activity.pk, session_pk=session.pk)


@login_required
def activity_session_log(request, pk: int, session_pk: int):
    """The 20-second screen: confirm who showed up. Everyone is pre-checked
    on a session nobody has touched yet — unchecking is the only work most
    teachers ever do here (fix step plan design context)."""
    educator = _educator(request)
    activity = get_object_or_404(Activity, pk=pk, educator=educator)
    session = get_object_or_404(Session, pk=session_pk, activity=activity)

    participants = list(activity.participants.all())
    checked_ids = set(
        SessionAttendance.objects.filter(session=session).values_list("participant_id", flat=True)
    )
    if session.status == constants.SESSION_STATUS_EXPECTED and not checked_ids:
        checked_ids = {participant.pk for participant in participants}

    if request.method == "POST":
        action = request.POST.get("action") or "held"

        if action == "cancel":
            session.status = constants.SESSION_STATUS_CANCELLED
            session.held_on = None
            session.save(update_fields=["status", "held_on"])
            SessionAttendance.objects.filter(session=session).delete()
            messages.success(request, "Session marked as cancelled.")
            return redirect("step:activity_detail", pk=activity.pk)

        topic = (request.POST.get("topic") or "").strip()
        notes = (request.POST.get("notes") or "").strip()
        evidence_url = (request.POST.get("evidence_url") or "").strip()
        present_ids = {int(value) for value in request.POST.getlist("present") if value.isdigit()}

        session.status = constants.SESSION_STATUS_HELD
        session.held_on = date.today()
        session.topic = topic
        session.notes = notes
        session.evidence_url = evidence_url
        session.save(update_fields=["status", "held_on", "topic", "notes", "evidence_url"])

        with transaction.atomic():
            # Replace, don't accumulate: an edit of an already-logged session
            # must not leave orphaned or duplicated attendance rows behind.
            SessionAttendance.objects.filter(session=session).exclude(
                participant_id__in=present_ids
            ).delete()
            already_present_ids = set(
                SessionAttendance.objects.filter(session=session)
                .values_list("participant_id", flat=True)
            )
            for participant in participants:
                if participant.pk in present_ids and participant.pk not in already_present_ids:
                    SessionAttendance.objects.create(session=session, participant=participant)

        if evidence_url and not _link_looks_reachable(evidence_url):
            messages.warning(
                request, "This link may not be reachable — check it opens for someone else."
            )
        messages.success(request, "Session logged.")
        return redirect("step:activity_detail", pk=activity.pk)

    last_held = (
        activity.sessions.filter(status=constants.SESSION_STATUS_HELD)
        .exclude(pk=session.pk).order_by("-scheduled_for").first()
    )
    prefill_topic = session.topic or (last_held.topic if last_held else "")

    context = {
        "nav": "activities",
        "activity": activity,
        "session": session,
        "participants": participants,
        "checked_ids": checked_ids,
        "prefill_topic": prefill_topic,
    }
    context.update(_chrome(educator))
    return render(request, "step/activities/session_log.html", context)
