"""Run the validation layer (spec 3.3) over items already in the bank.

    python manage.py validate_items                      # everything not yet approved
    python manage.py validate_items --status approved    # audit what teachers can see
    python manage.py validate_items --grade 10 --apply   # flag/clear based on results

Without --apply nothing is written: the command reports what it would do. That
matters because the gap-uniqueness check is the one place where a false
positive would silently remove usable items from the bank.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from bank.generation.validation import spacy_available, validate_item
from bank.models import Item, ReviewStatus


class Command(BaseCommand):
    help = "Check bank items against their structural constraints."

    def add_arguments(self, parser):
        parser.add_argument("--grade", type=int, action="append", dest="grades")
        parser.add_argument("--unit", type=int, action="append", dest="units")
        parser.add_argument("--type", type=str, action="append", dest="types")
        parser.add_argument(
            "--status", type=str, action="append", dest="statuses",
            help="Defaults to draft and flagged.",
        )
        parser.add_argument("--apply", action="store_true", help="Write the results back.")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        if not spacy_available():
            self.stdout.write(
                self.style.WARNING(
                    "spaCy or en_core_web_sm is not installed — structural checks will run, "
                    "but part-of-speech and gap-uniqueness checks will be skipped.\n"
                    "  pip install spacy && python -m spacy download en_core_web_sm  (~45MB)"
                )
            )

        items = Item.objects.select_related("unit").prefetch_related("unit__vocabulary")
        statuses = options["statuses"] or [ReviewStatus.DRAFT, ReviewStatus.FLAGGED]
        items = items.filter(review_status__in=statuses)
        if options["grades"]:
            items = items.filter(unit__grade__number__in=options["grades"])
        if options["units"]:
            items = items.filter(unit__number__in=options["units"])
        if options["types"]:
            items = items.filter(question_type__in=options["types"])
        if options["limit"]:
            items = items[: options["limit"]]

        passed = failed = 0
        updates = []

        for item in items:
            result = validate_item(item)
            if result.passed:
                passed += 1
            else:
                failed += 1
                self.stdout.write(
                    f"  #{item.pk} [{item.question_type}] u{item.unit.number}: "
                    + "; ".join(result.failures)
                )

            item.spacy_validated = result.spacy_ran
            item.gap_uniqueness_checked = result.uniqueness_checked
            if not result.passed:
                item.review_status = ReviewStatus.FLAGGED
                item.review_notes = "Validation: " + "; ".join(result.failures)
            updates.append(item)

        if options["apply"] and updates:
            with transaction.atomic():
                Item.objects.bulk_update(
                    updates,
                    ["spacy_validated", "gap_uniqueness_checked", "review_status", "review_notes"],
                    batch_size=500,
                )

        summary = f"{passed} passed, {failed} failed"
        self.stdout.write(
            self.style.SUCCESS(summary + (" (written back)" if options["apply"] else " (dry run — pass --apply to save)"))
        )
