"""A teacher's own classes, students, and checkpoint progress.

New per the classes/gradebook spec (2026-08-27), which brings the Assessments
vertical forward ahead of Monthly Reporting and replaces the two-obligation
shape sketched in the platform spine spec §9 (annotated there to point here).

Wired into the obligation engine the same way every other vertical is: three
ObligationType rows with form_slug="assessment_checkpoint" (step/constants.py),
generated per class rather than per educator (step/generation.py) and
auto-completed once every student has a structured entry for a checkpoint
(step/workflow.py) — no evidence to check, so nothing waits for a reviewer.
"""

from django.db import models

from step import constants
from step.models.roster import Educator


class TeachingClass(models.Model):
    educator = models.ForeignKey(Educator, on_delete=models.CASCADE, related_name="classes")
    grade = models.PositiveSmallIntegerField()
    slot = models.PositiveSmallIntegerField()
    display_name = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["grade", "slot"]
        constraints = [
            models.UniqueConstraint(fields=["grade", "slot"], name="one_teaching_class_per_grade_slot"),
        ]

    def __str__(self) -> str:
        return self.display_name


class Student(models.Model):
    teaching_class = models.ForeignKey(TeachingClass, on_delete=models.CASCADE, related_name="students")
    full_name = models.CharField(max_length=200)

    class Meta:
        ordering = ["full_name"]

    def __str__(self) -> str:
        return self.full_name


class ProgressEntry(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="progress_entries")
    checkpoint = models.CharField(max_length=8, choices=constants.CHECKPOINT_CHOICES, blank=True)
    score = models.PositiveSmallIntegerField(null=True, blank=True)
    skill = models.CharField(max_length=16, choices=constants.SKILL_CHOICES, blank=True)
    grammar_point = models.ForeignKey(
        "content.GrammarPoint", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="step_progress_entries",
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # A blank checkpoint means a freeform note and may repeat freely;
            # a non-blank checkpoint is the one structured record for that
            # checkpoint and may not.
            models.UniqueConstraint(
                fields=["student", "checkpoint"],
                condition=~models.Q(checkpoint=""),
                name="one_structured_entry_per_student_checkpoint",
            ),
        ]

    def __str__(self) -> str:
        label = self.get_checkpoint_display() if self.checkpoint else "Note"
        return f"{label} — {self.student.full_name}"
