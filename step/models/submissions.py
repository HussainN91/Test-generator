"""What a teacher hands in, and what an administrator says about it.

Two decisions are load-bearing:

* **Evidence is a list.** The monthly report needs both the form data and the
  photographed stamp, so one submission carries many items (spec §5.7).
* **Revisions never overwrite.** A returned submission that is resubmitted
  becomes revision 2; revision 1 stays. That history is the only record of what
  was originally sent, and it cannot be reconstructed (spec §5.8).

The director's rating, name, date and comments are captured here but are
**self-reported** — no Uzbek staff hold accounts, so the teacher transcribes
them and the stamped photograph is the only verification (spec §5.10).
"""

from django.conf import settings
from django.db import models

from step import constants
from step.models.obligations import Obligation


class Submission(models.Model):
    obligation = models.ForeignKey(Obligation, on_delete=models.CASCADE, related_name="submissions")
    revision = models.PositiveSmallIntegerField(default=1)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True, help_text="Anything the teacher wants to say.")

    # --- Self-reported evaluation (spec §5.10) ---------------------------
    director_rating = models.PositiveSmallIntegerField(
        null=True, blank=True, choices=constants.DIRECTOR_RATING_CHOICES,
        help_text="SELF-REPORTED. Transcribed by the teacher from the stamped paper.",
    )
    director_name = models.CharField(max_length=200, blank=True, help_text="SELF-REPORTED.")
    director_comments = models.TextField(blank=True, help_text="SELF-REPORTED.")
    evaluation_date = models.DateField(null=True, blank=True, help_text="SELF-REPORTED.")
    outcome = models.CharField(
        max_length=32, blank=True, choices=constants.OUTCOME_CHOICES,
        help_text="SELF-REPORTED. The binary outcome radio from the client mockup.",
    )

    # --- Review outcome ---------------------------------------------------
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="step_reviews",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_comment = models.TextField(
        blank=True, help_text="Shown to the teacher under Feedback & Correction when returned.",
    )

    class Meta:
        ordering = ["obligation", "-revision"]
        constraints = [
            models.UniqueConstraint(
                fields=["obligation", "revision"], name="step_submission_revision_unique"
            ),
        ]
        indexes = [models.Index(fields=["submitted_at"])]

    def __str__(self) -> str:
        return f"{self.obligation.display_name} rev {self.revision}"


class Evidence(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="evidence")
    kind = models.CharField(max_length=8, choices=constants.EVIDENCE_KIND_CHOICES)
    url = models.URLField(blank=True, max_length=1000)
    file = models.FileField(upload_to="step/evidence/%Y/%m/", blank=True)
    caption = models.CharField(max_length=200, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["submission", "uploaded_at"]

    def __str__(self) -> str:
        return self.caption or self.url or (self.file.name if self.file else f"Evidence {self.pk}")
