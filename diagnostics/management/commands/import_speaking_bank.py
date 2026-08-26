"""Import the real 50-prompt speaking bank and its marking rubric."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from diagnostics.extraction.xlsx_speaking import extract_rubric, extract_speaking_prompts
from diagnostics.models import SpeakingPrompt, SpeakingRubric

WORKBOOK_NAME = "Question Bank -Diagnostic Test.xlsx"


class Command(BaseCommand):
    help = "Import the real speaking prompt bank (50 items) and its rubric."

    def handle(self, *args, **options):
        path = settings.DIAGNOSTICS_SOURCE_DIR / WORKBOOK_NAME
        if not path.exists():
            raise CommandError(f"Missing source file: {path}")

        prompts = extract_speaking_prompts(path)
        # Adaptive: only object if a task's pool can't cover one grade's 4
        # non-overlapping variants (1 prompt per task per variant).
        from collections import Counter

        from diagnostics.constants import SPEAKING_TASK_ORDER

        counts = Counter(item["task"] for item in prompts)
        for task in SPEAKING_TASK_ORDER:
            if counts.get(task, 0) < 4:
                raise CommandError(
                    f"Need at least 4 '{task}' speaking prompts (one per grade "
                    f"variant), only found {counts.get(task, 0)}."
                )
        rubric = extract_rubric(path)
        missing_rubric = set(SPEAKING_TASK_ORDER) - set(rubric)
        if missing_rubric:
            raise CommandError(f"Missing rubric rows for tasks: {sorted(missing_rubric)}")

        with transaction.atomic():
            # PaperSpeakingPrompt.prompt uses on_delete=PROTECT, so this
            # delete-all will fail once real Papers reference these rows.
            # Only safe to run before build_papers has populated any papers.
            SpeakingPrompt.objects.all().delete()
            for item in prompts:
                SpeakingPrompt.objects.create(
                    task=item["task"], prompt=item["prompt"], bullets=item["bullets"],
                )
            for task, entry in rubric.items():
                SpeakingRubric.objects.update_or_create(
                    task=task, defaults={"marks": entry["marks"], "indicators": entry["indicators"]},
                )

        self.stdout.write(self.style.SUCCESS(
            f"Imported {SpeakingPrompt.objects.count()} speaking prompts, "
            f"{SpeakingRubric.objects.count()} rubric rows."
        ))
