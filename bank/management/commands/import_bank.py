"""Import a bank export onto the production server (spec 7.1).

This is how a VPS gets its items: the admin generates and reviews offline,
exports, copies the file over, and imports. The server never generates.

    python manage.py import_bank --in bank-export.json
    python manage.py import_bank --in bank-export.json --dry-run

Items are matched to units by (grade, unit number) and deduplicated by
content_hash, so re-importing the same file is a no-op.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bank.models import Item
from content.models import Unit


class Command(BaseCommand):
    help = "Load items from a bank export file."

    def add_arguments(self, parser):
        parser.add_argument("--in", dest="infile", type=str, required=True)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Refresh review status and notes on items already present.",
        )

    def handle(self, *args, **options):
        path = Path(options["infile"])
        if not path.exists():
            raise CommandError(f"No such file: {path}")

        data = json.loads(path.read_text(encoding="utf-8"))
        records = data.get("items", [])
        if not records:
            self.stdout.write(self.style.WARNING("The export contains no items."))
            return

        units = {
            (unit.grade.number, unit.number): unit
            for unit in Unit.objects.select_related("grade")
        }
        existing = dict(Item.objects.values_list("content_hash", "pk"))

        created, updated, skipped, orphaned = [], 0, 0, set()

        for record in records:
            key = (record["grade"], record["unit"])
            unit = units.get(key)
            if unit is None:
                orphaned.add(key)
                continue

            digest = record["content_hash"]
            if digest in existing:
                if options["update_existing"] and not options["dry_run"]:
                    Item.objects.filter(pk=existing[digest]).update(
                        review_status=record["review_status"],
                        review_notes=record.get("review_notes", ""),
                    )
                    updated += 1
                else:
                    skipped += 1
                continue

            created.append(
                Item(
                    unit=unit,
                    grammar_point=getattr(unit, "grammar_point", None),
                    target_vocabulary=unit.vocabulary.filter(
                        word__iexact=record.get("target_word", "")
                    ).first()
                    if record.get("target_word")
                    else None,
                    question_type=record["question_type"],
                    payload=record["payload"],
                    model_answer=record["model_answer"],
                    acceptable_answers=record.get("acceptable_answers", []),
                    review_status=record["review_status"],
                    review_notes=record.get("review_notes", ""),
                    spacy_validated=record.get("spacy_validated", False),
                    llm_validated=record.get("llm_validated", False),
                    gap_uniqueness_checked=record.get("gap_uniqueness_checked", False),
                    generation_batch=record.get("generation_batch", ""),
                    content_hash=digest,
                )
            )
            existing[digest] = None

        if orphaned:
            listing = ", ".join(f"grade {g} unit {u}" for g, u in sorted(orphaned))
            self.stdout.write(
                self.style.WARNING(f"No matching unit for: {listing}. Run import_guide first.")
            )

        if not options["dry_run"]:
            with transaction.atomic():
                Item.objects.bulk_create(created, batch_size=500, ignore_conflicts=True)

        verb = "Would import" if options["dry_run"] else "Imported"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {len(created)} new items; {skipped} already present; {updated} updated."
            )
        )
