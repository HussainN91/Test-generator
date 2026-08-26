"""Verify all 48 papers independently of Paper.clean(), including reuse caps.

Run this after build_papers, and any time the content banks are re-imported.
"""

from django.core.management.base import BaseCommand, CommandError

from diagnostics.verification import (
    EXPECTED_PAPER_COUNT, find_completeness_problems, find_reuse_violations,
)


class Command(BaseCommand):
    help = "Verify that every grade's variants stay within their reuse caps."

    def handle(self, *args, **options):
        problems = find_completeness_problems() + find_reuse_violations()
        if problems:
            raise CommandError("Verification failed:\n  " + "\n  ".join(problems))

        self.stdout.write(self.style.SUCCESS(
            f"All {EXPECTED_PAPER_COUNT} papers pass: complete sections, and no "
            f"component shared beyond its reuse cap within any grade."
        ))
