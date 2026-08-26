"""Import the real reading passage bank from the client's workbook."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from diagnostics.extraction.xlsx_reading import extract_passages, resolve_subtype
from diagnostics.models import ReadingPassage, ReadingQuestion

WORKBOOK_NAME = "Question Bank -Diagnostic Test.xlsx"


class Command(BaseCommand):
    help = "Import the real reading passage bank."

    def handle(self, *args, **options):
        path = settings.DIAGNOSTICS_SOURCE_DIR / WORKBOOK_NAME
        if not path.exists():
            raise CommandError(f"Missing source file: {path}")

        passages = extract_passages(path)
        # The bank is the living source of truth: import whatever it holds,
        # and only object if there isn't enough for 4 non-overlapping
        # passages within a single grade (the inviolable rule's floor) - not
        # if the count differs from a snapshot taken on any particular day.
        if len(passages) < 4:
            raise CommandError(
                f"Need at least 4 reading passages (one grade's worth of "
                f"non-overlapping variants), only found {len(passages)}."
            )

        with transaction.atomic():
            for index, data in enumerate(passages, start=1):
                label = f"R{index:02d}"
                passage, _ = ReadingPassage.objects.update_or_create(
                    label=label,
                    defaults={"title": data["title"] or label, "body": data["body"]},
                )
                passage.questions.all().delete()
                for question in data["questions"]:
                    subtype = resolve_subtype(
                        question["subtype"], question["options"],
                        label, question["position"],
                    )
                    ReadingQuestion.objects.create(
                        passage=passage,
                        position=question["position"],
                        subtype=subtype,
                        stem=question["stem"],
                        options=question["options"],
                        answer=question["answer"],
                    )

        self.stdout.write(self.style.SUCCESS(
            f"Imported {ReadingPassage.objects.count()} passages, "
            f"{ReadingQuestion.objects.count()} questions."
        ))
