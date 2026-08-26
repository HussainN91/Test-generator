"""Populate the item bank with deterministically-derived items (no API key needed).

    python manage.py seed_bank                    # every unit, every grade
    python manage.py seed_bank --grade 9
    python manage.py seed_bank --grade 10 --unit 3
    python manage.py seed_bank --reset            # drop bootstrap items first

Items are written with review_status=approved because their correctness follows
from the source data rather than from a model's judgement: the definitions are
the guide's own, and word-formation items whose answer is not unique are
dropped before they are written (see bootstrap._drop_ambiguous_word_formation).
Pass --needs-review to stage them for manual approval instead.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from bank.generation.bootstrap import generate_for_unit
from bank.models import Item, ReviewStatus
from content.models import Unit

BOOTSTRAP_BATCH = "bootstrap"


class Command(BaseCommand):
    help = "Generate item-bank entries from the imported syllabus, without calling an LLM."

    def add_arguments(self, parser):
        parser.add_argument("--grade", type=int, action="append", dest="grades")
        parser.add_argument("--unit", type=int, action="append", dest="units")
        parser.add_argument("--type", type=str, action="append", dest="types")
        parser.add_argument("--reset", action="store_true", help="Delete existing bootstrap items first.")
        parser.add_argument(
            "--needs-review",
            action="store_true",
            help="Write items as flagged rather than approved.",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        units = Unit.objects.select_related("grade", "grammar_point").prefetch_related("vocabulary")
        if options["grades"]:
            units = units.filter(grade__number__in=options["grades"])
        if options["units"]:
            units = units.filter(number__in=options["units"])

        if options["reset"] and not options["dry_run"]:
            # Items already placed in a generated test are protected: deleting
            # them would break the traceability of tests a teacher has printed.
            removable = Item.objects.filter(
                generation_batch=BOOTSTRAP_BATCH, unit__in=units, placements__isnull=True
            )
            in_use = Item.objects.filter(
                generation_batch=BOOTSTRAP_BATCH, unit__in=units, placements__isnull=False
            ).count()
            deleted, _ = removable.delete()
            self.stdout.write(f"Removed {deleted} existing bootstrap items.")
            if in_use:
                self.stdout.write(
                    self.style.WARNING(f"Kept {in_use} item(s) already used in a generated test.")
                )

        status = ReviewStatus.FLAGGED if options["needs_review"] else ReviewStatus.APPROVED
        created_total = 0
        skipped_total = 0
        by_type: dict[str, int] = {}

        for unit in units:
            drafts = generate_for_unit(unit, options["types"])
            if not drafts:
                continue

            existing = set(
                Item.objects.filter(unit=unit).values_list("content_hash", flat=True)
            )
            to_create = []
            for draft in drafts:
                digest = draft.content_hash()
                if digest in existing:
                    skipped_total += 1
                    continue
                existing.add(digest)
                to_create.append(
                    Item(
                        unit=unit,
                        grammar_point=getattr(unit, "grammar_point", None),
                        target_vocabulary_id=draft.target_vocabulary_id,
                        question_type=draft.question_type,
                        payload=draft.payload,
                        model_answer=draft.model_answer,
                        acceptable_answers=draft.acceptable_answers,
                        review_status=status,
                        review_notes="Derived from the syllabus without an LLM (seed_bank).",
                        generation_batch=BOOTSTRAP_BATCH,
                        content_hash=digest,
                    )
                )
                by_type[draft.question_type] = by_type.get(draft.question_type, 0) + 1

            if options["dry_run"]:
                created_total += len(to_create)
                continue

            with transaction.atomic():
                Item.objects.bulk_create(to_create, batch_size=500)
            created_total += len(to_create)

        verb = "Would create" if options["dry_run"] else "Created"
        self.stdout.write(self.style.SUCCESS(f"{verb} {created_total} items ({skipped_total} already present)."))
        for question_type, count in sorted(by_type.items()):
            self.stdout.write(f"  {question_type}: {count}")
        if not options["dry_run"]:
            self.stdout.write(
                "Gap-fill, key word transformation and error correction need the "
                "Claude pipeline: python manage.py generate_items --help"
            )
