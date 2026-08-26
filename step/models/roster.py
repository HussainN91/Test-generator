"""Educators, their schools, and the machinery for importing them.

The client's roster spreadsheet exists but its columns are unknown at design
time and may change between terms (spec §4.2). Everything here is therefore
built to tolerate an unfamiliar sheet: two required fields, every other column
preserved verbatim in `source_fields`, and no destructive updates — a person
who vanishes from the sheet is flagged, never deleted.
"""

from django.conf import settings
from django.db import models

from step.models.geography import District, Region


class School(models.Model):
    name = models.CharField(max_length=200)
    district = models.ForeignKey(District, on_delete=models.PROTECT, related_name="schools")
    external_id = models.CharField(
        max_length=64, blank=True, help_text="The client's own identifier, if the sheet carries one."
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Educator(models.Model):
    """An international educator. The only role that accrues obligations."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="educator",
        help_text="Set when the person signs up and is matched to this roster row.",
    )
    full_name = models.CharField(max_length=200)

    # Identity candidates. All optional: which one is authoritative is a
    # deployment decision (settings.STEP_ROSTER_MATCH_KEYS), not a schema one.
    email = models.EmailField(blank=True)
    passport_no = models.CharField(max_length=64, blank=True)
    pinfl = models.CharField(max_length=32, blank=True)

    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="educators")
    district = models.ForeignKey(
        District, null=True, blank=True, on_delete=models.SET_NULL, related_name="educators"
    )
    school = models.ForeignKey(
        School, null=True, blank=True, on_delete=models.SET_NULL, related_name="educators"
    )

    is_active = models.BooleanField(default=True)
    missing_from_last_import = models.BooleanField(
        default=False,
        help_text="Set when a re-import no longer finds this person. Never auto-deleted.",
    )
    source_fields = models.JSONField(
        default=dict,
        blank=True,
        help_text="Every spreadsheet column that did not map to a known field, kept verbatim.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]
        indexes = [
            models.Index(fields=["region", "is_active"]),
            models.Index(fields=["email"]),
        ]

    def __str__(self) -> str:
        return self.full_name


class RosterImport(models.Model):
    """One spreadsheet upload, with the column mapping that was confirmed for it."""

    file = models.FileField(upload_to="step/roster/")
    imported_at = models.DateTimeField(auto_now_add=True)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    header_row = models.PositiveIntegerField(default=1)
    mapping = models.JSONField(
        default=dict, blank=True, help_text="Spreadsheet header -> canonical field name."
    )
    row_count = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    unresolved_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-imported_at"]

    def __str__(self) -> str:
        return f"Roster import {self.pk} ({self.row_count} rows)"


class AliasMapping(models.Model):
    """A remembered decision about what a messy source string actually meant.

    Exists so a human maps "Tash. city" to Tashkent City exactly once. Without
    it, every import repeats the same manual work.
    """

    KIND_REGION = "region"
    KIND_DISTRICT = "district"
    KIND_SCHOOL = "school"
    KIND_CHOICES = [(KIND_REGION, "Region"), (KIND_DISTRICT, "District"), (KIND_SCHOOL, "School")]

    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    raw_value = models.CharField(max_length=200)
    normalised = models.CharField(max_length=200, db_index=True)
    region = models.ForeignKey(Region, null=True, blank=True, on_delete=models.CASCADE)
    district = models.ForeignKey(District, null=True, blank=True, on_delete=models.CASCADE)
    school = models.ForeignKey(School, null=True, blank=True, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["kind", "normalised"], name="step_alias_unique_per_kind"),
        ]

    def __str__(self) -> str:
        return f"{self.kind}: {self.raw_value}"


class UnresolvedRow(models.Model):
    """A spreadsheet row the importer could not place. Reviewed by hand."""

    roster_import = models.ForeignKey(
        RosterImport, on_delete=models.CASCADE, related_name="unresolved_rows"
    )
    row_number = models.PositiveIntegerField()
    reason = models.CharField(max_length=200)
    payload = models.JSONField(default=dict)
    resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ["roster_import", "row_number"]

    def __str__(self) -> str:
        return f"Row {self.row_number}: {self.reason}"


class PendingSignup(models.Model):
    """Someone signed up but matched no roster row. An administrator decides.

    The spreadsheet is the gatekeeper (spec §4.3), so an unmatched signup is
    held here rather than silently creating an educator.
    """

    full_name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    passport_no = models.CharField(max_length=64, blank=True)
    pinfl = models.CharField(max_length=32, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self) -> str:
        return f"Pending signup: {self.full_name}"
