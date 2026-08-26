"""Export approved items to JSON — the offline-to-production handoff (spec 3.4).

Generation happens on a machine with an API key; the VPS only imports the
result. Items are keyed by (grade, unit number) rather than by database id so
the file survives a rebuilt production database.

    python manage.py export_bank --out bank-export.json
    python manage.py export_bank --grade 10 --out grade10.json
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from bank.models import Item, ReviewStatus

EXPORT_VERSION = 1


class Command(BaseCommand):
    help = "Write approved bank items to a portable JSON file."

    def add_arguments(self, parser):
        parser.add_argument("--out", type=str, required=True)
        parser.add_argument("--grade", type=int, action="append", dest="grades")
        parser.add_argument("--unit", type=int, action="append", dest="units")
        parser.add_argument(
            "--include-unapproved",
            action="store_true",
            help="Also export draft/flagged items, for moving a review queue between machines.",
        )

    def handle(self, *args, **options):
        items = Item.objects.select_related("unit", "unit__grade", "target_vocabulary")
        if not options["include_unapproved"]:
            items = items.filter(review_status=ReviewStatus.APPROVED)
        if options["grades"]:
            items = items.filter(unit__grade__number__in=options["grades"])
        if options["units"]:
            items = items.filter(unit__number__in=options["units"])

        records = [
            {
                "grade": item.unit.grade.number,
                "unit": item.unit.number,
                "question_type": item.question_type,
                "payload": item.payload,
                "model_answer": item.model_answer,
                "acceptable_answers": item.acceptable_answers,
                "review_status": item.review_status,
                "review_notes": item.review_notes,
                "spacy_validated": item.spacy_validated,
                "llm_validated": item.llm_validated,
                "gap_uniqueness_checked": item.gap_uniqueness_checked,
                "generation_batch": item.generation_batch,
                "content_hash": item.content_hash,
                "target_word": item.target_vocabulary.word if item.target_vocabulary else "",
            }
            for item in items.iterator()
        ]

        path = Path(options["out"])
        path.write_text(
            json.dumps(
                {"version": EXPORT_VERSION, "items": records}, ensure_ascii=False, indent=1
            ),
            encoding="utf-8",
        )
        self.stdout.write(self.style.SUCCESS(f"Exported {len(records)} items to {path}"))
