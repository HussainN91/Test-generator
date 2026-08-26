"""Uzbekistan's administrative divisions, seeded from a repository fixture.

Deliberately NOT derived from the client roster spreadsheet. Region is the axis
every administration chart pivots on, and free-text region names would produce
"Tashkent", "Toshkent" and "Tashkent city" as three separate regions with three
separate bars in the same chart. Seeding makes that failure impossible.
"""

from django.db import models


class Region(models.Model):
    """A viloyat, the Republic of Karakalpakstan, or Tashkent City."""

    name = models.CharField(max_length=100, unique=True)
    name_uz = models.CharField(max_length=100, blank=True)
    code = models.SlugField(max_length=32, unique=True)
    is_city = models.BooleanField(
        default=False,
        help_text="True for Tashkent City, which is a top-level division but not a viloyat.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class District(models.Model):
    """A tuman within a region."""

    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="districts")
    name = models.CharField(max_length=100)
    name_uz = models.CharField(max_length=100, blank=True)
    code = models.SlugField(max_length=48)

    class Meta:
        ordering = ["region__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["region", "code"], name="step_district_code_unique_per_region"),
        ]

    def __str__(self) -> str:
        return f"{self.name}, {self.region.name}"
