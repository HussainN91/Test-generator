"""Assembly & tracking (spec 3.4): pure sampling from the item bank.

A TestBatch is the set of variants a teacher requested together. Exclusion of
already-used items applies *within* a batch only — deliberately not globally,
so a shared multi-teacher bank does not deplete.
"""

from django.conf import settings
from django.db import models

from bank.models import Item
from content.models import Grade, Unit


class TestBatch(models.Model):
    """One teacher request: N variants over a selected set of units."""

    grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name="test_batches")
    units = models.ManyToManyField(Unit, related_name="test_batches")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="test_batches",
    )
    question_count = models.PositiveSmallIntegerField()
    variant_count = models.PositiveSmallIntegerField()
    type_mix = models.JSONField(
        default=dict,
        blank=True,
        help_text="question_type -> count. Empty means use the default weighted mix.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "test batches"

    def __str__(self):
        return f"Batch #{self.pk} — G{self.grade.number}, {self.variant_count} variants"


class TestVariant(models.Model):
    """A single tagged, traceable test (Test A, Test B, ...)."""

    batch = models.ForeignKey(TestBatch, on_delete=models.CASCADE, related_name="variants")
    label = models.CharField(max_length=8, help_text='Variant tag, e.g. "A".')
    items = models.ManyToManyField(Item, through="TestQuestion", related_name="variants")

    class Meta:
        ordering = ["batch", "label"]
        constraints = [
            models.UniqueConstraint(fields=["batch", "label"], name="unique_variant_label_per_batch"),
        ]

    def __str__(self):
        return f"Batch #{self.batch_id} — Test {self.label}"


class TestQuestion(models.Model):
    """An item's placement within a variant, fixing question order for the answer key."""

    variant = models.ForeignKey(TestVariant, on_delete=models.CASCADE, related_name="questions")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="placements")
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["variant", "position"]
        constraints = [
            models.UniqueConstraint(fields=["variant", "position"], name="unique_position_per_variant"),
            models.UniqueConstraint(fields=["variant", "item"], name="unique_item_per_variant"),
        ]

    def __str__(self):
        return f"{self.variant} Q{self.position}"
