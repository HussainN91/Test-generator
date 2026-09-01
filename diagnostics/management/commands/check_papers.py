"""Verify all 48 papers independently of Paper.clean(): reuse caps, section
completeness, and the four group invariants.

Run this after build_papers, and any time the content banks are re-imported.
"""

from django.core.management.base import BaseCommand, CommandError

from diagnostics.navigation import GROUPS_PER_GRADE
from diagnostics.constants import GRADES
from diagnostics.verification import (
    EXPECTED_PAPER_COUNT, find_completeness_problems, find_group_violations,
    find_reuse_violations,
)

EXPECTED_GROUP_COUNT = len(GRADES) * GROUPS_PER_GRADE


class Command(BaseCommand):
    help = (
        "Verify reuse caps, section completeness, and that every exam sitting "
        "shares its audio and nothing else."
    )

    def handle(self, *args, **options):
        problems = (
            find_completeness_problems()
            + find_reuse_violations()
            + find_group_violations()
        )
        if problems:
            raise CommandError("Verification failed:\n  " + "\n  ".join(problems))

        self.stdout.write(self.style.SUCCESS(
            f"All {EXPECTED_PAPER_COUNT} papers pass: complete sections, no "
            f"component shared beyond its reuse cap within any grade, and all "
            f"{EXPECTED_GROUP_COUNT} sittings share one recording pair while "
            f"sharing no questions, prompt or passage."
        ))
