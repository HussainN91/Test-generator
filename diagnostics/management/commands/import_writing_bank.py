"""Import the real 200-question writing bank. Idempotent: clears and reloads."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from diagnostics.extraction.xlsx_writing import extract_writing_items
from diagnostics.models import WritingQuestion

WORKBOOK_NAME = "Question Bank -Diagnostic Test.xlsx"


class Command(BaseCommand):
    help = "Import the real writing question bank (200 items)."

    def handle(self, *args, **options):
        path = settings.DIAGNOSTICS_SOURCE_DIR / WORKBOOK_NAME
        if not path.exists():
            raise CommandError(f"Missing source file: {path}")

        items = extract_writing_items(path)
        # Adaptive, not a snapshot check: import whatever the bank holds, and
        # only object if a subtype's pool is too small to give one grade
        # (4 variants) a non-overlapping selection - the inviolable rule's
        # actual floor, from the headroom analysis in Design Revision 1 §5.
        from collections import Counter

        from diagnostics.constants import WRITING_SUBTYPE_COUNTS

        counts = Counter(item["subtype"] for item in items)
        for subtype, per_paper in WRITING_SUBTYPE_COUNTS.items():
            floor = per_paper * 4
            if counts.get(subtype, 0) < floor:
                raise CommandError(
                    f"Need at least {floor} '{subtype}' writing questions "
                    f"(4 variants x {per_paper} each), only found {counts.get(subtype, 0)}."
                )

        with transaction.atomic():
            # PaperWritingQuestion.question uses on_delete=PROTECT, so this
            # delete-all will fail once real Papers reference these rows.
            # Only safe to run before build_papers has populated any papers.
            WritingQuestion.objects.all().delete()
            for item in items:
                WritingQuestion.objects.create(
                    subtype=item["subtype"], stem=item["stem"],
                    options=item["options"], answer=item["answer"],
                )

        self.stdout.write(self.style.SUCCESS(
            f"Imported {WritingQuestion.objects.count()} writing questions."
        ))
