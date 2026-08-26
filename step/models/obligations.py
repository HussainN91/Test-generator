"""The obligation engine.

An ObligationType is a database row rather than a Python class, which is the
single decision the whole platform rests on: it makes CPD Online, CPD Offline,
ECA and any future vertical configuration rather than code (spec §5.1). Only a
vertical needing a bespoke form or bespoke content requires programming, and it
attaches through `form_slug`.

Status is stored. Urgency is not — see `step/urgency.py` and spec §5.3.
"""

from django.db import models

from step import constants
from step.models.roster import Educator
from step.scheduling import period_end as _period_end


class AcademicYear(models.Model):
    label = models.CharField(max_length=32, unique=True, help_text='For example "2025-26".')
    start = models.DateField()
    end = models.DateField()
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["-start"]

    def save(self, *args, **kwargs):
        """Only one year is current. Enforced here because two current years
        would make every "this year" figure on the dashboard ambiguous."""
        super().save(*args, **kwargs)
        if self.is_current:
            AcademicYear.objects.exclude(pk=self.pk).filter(is_current=True).update(is_current=False)

    def __str__(self) -> str:
        return self.label


class Term(models.Model):
    year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="terms")
    name = models.CharField(max_length=32)
    sequence = models.PositiveSmallIntegerField()
    start = models.DateField()
    end = models.DateField()

    class Meta:
        ordering = ["year", "sequence"]
        constraints = [
            models.UniqueConstraint(fields=["year", "sequence"], name="step_term_sequence_unique_per_year"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.year.label})"


class ObligationType(models.Model):
    name_template = models.CharField(
        max_length=200,
        help_text='Shown to teachers. "{period}" is replaced with the month or term; '
                  'if absent, the period is appended after a dash.',
    )
    category = models.CharField(max_length=32, choices=constants.CATEGORY_CHOICES)
    cadence = models.CharField(max_length=16, choices=constants.CADENCE_CHOICES)
    due_rule = models.JSONField(
        default=dict, blank=True,
        help_text='For example {"kind": "day_of_month", "day": 27}. Empty means the period end.',
    )
    evidence_spec = models.CharField(
        max_length=16, choices=constants.EVIDENCE_SPEC_CHOICES, default=constants.EVIDENCE_EITHER
    )
    min_count = models.PositiveSmallIntegerField(default=1)
    requires_review = models.BooleanField(
        default=False, help_text="When false, a submission is accepted immediately."
    )
    scope_rule = models.CharField(
        max_length=16, choices=constants.SCOPE_CHOICES, default=constants.SCOPE_ALL
    )
    form_slug = models.SlugField(
        max_length=64, blank=True,
        help_text="Names a coded form for verticals that need one. Blank means link/file only.",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category", "name_template"]

    @property
    def period_kind(self) -> str:
        return constants.CADENCE_TO_PERIOD_KIND[self.cadence]

    def __str__(self) -> str:
        return self.name_template


class Obligation(models.Model):
    """One concrete thing one educator owes for one period."""

    type = models.ForeignKey(ObligationType, on_delete=models.PROTECT, related_name="obligations")
    educator = models.ForeignKey(Educator, on_delete=models.CASCADE, related_name="obligations")

    period_kind = models.CharField(max_length=16, choices=constants.PERIOD_KIND_CHOICES)
    period_start = models.DateField()
    period_label = models.CharField(
        max_length=32, blank=True,
        help_text='For terms, the term name ("Term 1"). Months derive their own label.',
    )

    due_date = models.DateField()
    due_date_overridden = models.BooleanField(
        default=False, help_text="Set when an extension was granted. Visible, never silent."
    )
    status = models.CharField(
        max_length=16, choices=constants.OBLIGATION_STATUS_CHOICES, default=constants.STATUS_NOT_STARTED
    )
    opened_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "type__category"]
        constraints = [
            models.UniqueConstraint(
                fields=["type", "educator", "period_start"], name="step_obligation_unique_per_period"
            ),
        ]
        indexes = [
            models.Index(fields=["educator", "status"]),
            models.Index(fields=["type", "period_start", "status"]),
            models.Index(fields=["due_date"]),
        ]

    @property
    def period_display(self) -> str:
        if self.period_label:
            return self.period_label
        if self.period_kind == constants.PERIOD_MONTH:
            return self.period_start.strftime("%B %Y")
        if self.period_kind == constants.PERIOD_YEAR:
            return str(self.period_start.year)
        return ""

    @property
    def display_name(self) -> str:
        """What the teacher actually reads. Never exposes model vocabulary."""
        template = self.type.name_template
        period = self.period_display
        if "{period}" in template:
            return template.replace("{period}", period)
        return f"{template} - {period}" if period else template

    @property
    def period_end(self):
        return _period_end(self.period_start, self.period_kind)

    @property
    def latest_submission(self):
        """The current revision, or None. Earlier revisions stay in `submissions`."""
        return self.submissions.order_by("-revision").first()

    def __str__(self) -> str:
        return f"{self.display_name} ({self.educator.full_name})"
