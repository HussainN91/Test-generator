"""Recurring delivery with a roster: the ECA Programme and CPD Offline verticals.

Both are actually Activity -> Session -> Attendance, not paperwork owed by a
date, so they sit as a peer to the obligation engine rather than inside it
(fix step plan §2-§3; platform spine spec, docs/superpowers/specs/
2026-08-26-step-platform-spine-design.md). An ECA activity may still owe a
monthly/termly plan obligation (see step/models/obligations.py's `activity`
FK), but the register of who showed up when lives here.
"""

from django.db import models

from step import constants
from step.models.classes import Student
from step.models.roster import Educator, School, SchoolStaff


class Activity(models.Model):
    educator = models.ForeignKey(Educator, on_delete=models.CASCADE, related_name="activities")
    kind = models.CharField(max_length=16, choices=constants.ACTIVITY_KIND_CHOICES)
    title = models.CharField(max_length=200)
    # Nullable: an ECA activity may not need a school, but a CPD Offline one
    # does. No DB-level conditional requirement for now (fix step plan §3.2).
    school = models.ForeignKey(
        School, null=True, blank=True, on_delete=models.SET_NULL, related_name="activities"
    )
    schedule_rule = models.JSONField(
        default=dict, blank=True,
        help_text='For example {"weekdays": [4]} for Friday. Same convention as '
                  "ObligationType.due_rule.",
    )
    started_on = models.DateField()
    archived_on = models.DateField(
        null=True, blank=True,
        help_text="Stops future sessions and plan obligations. Past data is never deleted.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-started_on", "title"]

    def __str__(self) -> str:
        return self.title


class ActivityParticipant(models.Model):
    """A named row in an activity's register.

    `full_name` is always stored, even when linked to a Student or SchoolStaff,
    so a past register never silently rewrites itself if the linked record is
    later removed (fix step plan §3.4).
    """

    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="participants")
    full_name = models.CharField(max_length=200)
    student = models.ForeignKey(
        Student, null=True, blank=True, on_delete=models.SET_NULL, related_name="activity_participations"
    )
    staff = models.ForeignKey(
        SchoolStaff, null=True, blank=True, on_delete=models.SET_NULL, related_name="activity_participations"
    )

    class Meta:
        ordering = ["full_name"]
        constraints = [
            # student and staff are mutually exclusive: a participant is
            # sourced from a class Student, from a School's typed-in
            # SchoolStaff, or just typed with neither set — never both.
            models.CheckConstraint(
                condition=~(models.Q(student__isnull=False) & models.Q(staff__isnull=False)),
                name="step_activity_participant_not_both_student_and_staff",
            ),
        ]

    def __str__(self) -> str:
        return self.full_name


class Session(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="sessions")
    scheduled_for = models.DateField()
    held_on = models.DateField(
        null=True, blank=True,
        help_text="Filled when logged. May differ from scheduled_for for off-schedule sessions.",
    )
    status = models.CharField(
        max_length=16, choices=constants.SESSION_STATUS_CHOICES, default=constants.SESSION_STATUS_EXPECTED
    )
    topic = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    # Link only, never a file field: the teacher keeps their own Drive
    # evidence, STEP never stores the file (fix step plan §3.7).
    evidence_url = models.URLField(blank=True)
    #: When this session was last logged/edited.
    recorded_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scheduled_for"]

    def __str__(self) -> str:
        return f"{self.activity.title} - {self.scheduled_for}"


class SessionAttendance(models.Model):
    """A row exists only for a participant who was present. No absentee rows
    (fix step plan §3.6)."""

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="attendances")
    participant = models.ForeignKey(
        ActivityParticipant, on_delete=models.CASCADE, related_name="attendances"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session", "participant"], name="step_attendance_unique_per_session_participant"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.participant.full_name} @ {self.session}"


class ActivityPlan(models.Model):
    """One per (activity, period) — an autosaved draft filled in progressively."""

    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="plans")
    period = models.DateField(help_text="First of the month, mirroring Obligation.period_start.")
    overview = models.TextField(blank=True)
    session_outline = models.TextField(blank=True)
    intended_outcomes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["activity", "period"]
        constraints = [
            models.UniqueConstraint(fields=["activity", "period"], name="step_activity_plan_unique_per_period"),
        ]

    def __str__(self) -> str:
        return f"{self.activity.title} plan ({self.period:%B %Y})"
