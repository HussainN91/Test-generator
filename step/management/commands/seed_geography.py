"""Loads Uzbekistan's administrative divisions.

Idempotent by design: it runs on every deployment, and re-running must never
duplicate a region or orphan a district. Upserts on `code`, which is why the
fixture carries stable codes rather than relying on names.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from step.models import District, Region

FIXTURE = Path(__file__).resolve().parent.parent.parent / "fixtures" / "uz_geography.json"


class Command(BaseCommand):
    help = "Seed or refresh Uzbekistan's regions and districts. Safe to re-run."

    @transaction.atomic
    def handle(self, *args, **options):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

        regions_touched = districts_touched = 0
        for entry in payload:
            region, _ = Region.objects.update_or_create(
                code=entry["code"],
                defaults={
                    "name": entry["name"],
                    "name_uz": entry.get("name_uz", ""),
                    "is_city": entry.get("is_city", False),
                },
            )
            regions_touched += 1
            for d in entry.get("districts", []):
                District.objects.update_or_create(
                    region=region,
                    code=d["code"],
                    defaults={"name": d["name"], "name_uz": d.get("name_uz", "")},
                )
                districts_touched += 1

        self.stdout.write(
            self.style.SUCCESS(f"Seeded {regions_touched} regions and {districts_touched} districts.")
        )
