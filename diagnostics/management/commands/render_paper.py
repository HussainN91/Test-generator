"""Turn a built paper into the two .docx files a teacher actually needs.

Two documents, not one: the student copy and the answer key are separated so
the key can be printed apart from the test rather than being torn off the
back of it. Naming is fixed (G9-A-Student.docx / G9-A-AnswerKey.docx) so a
whole run of --all sorts into an obvious pack.

The documents themselves are built by diagnostics/export.py, which the
paper-download view also calls — one implementation, not two that could
drift apart. This command is a thin CLI wrapper: resolve papers, write the
files this command's own naming convention wants.

python-docx is an optional dependency here as it is in assembly/export.py —
the difference is that this command has no HTML fallback to offer, so a
missing library is a CommandError rather than a quiet degrade.
"""

import os

from django.core.management.base import BaseCommand, CommandError

from diagnostics.constants import GRADES, VARIANTS
from diagnostics.export import answer_key_docx, docx_available, student_docx
from diagnostics.models import Paper


class Command(BaseCommand):
    help = "Render a diagnostic paper as student and answer-key .docx files."

    def add_arguments(self, parser):
        parser.add_argument("--grade", type=int, help="9, 10 or 11.")
        parser.add_argument("--variant", help="A through P.")
        parser.add_argument(
            "--out", default=".", help="Directory to write the .docx files into."
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Render all 48 papers; --grade/--variant are ignored.",
        )

    def handle(self, *args, **options):
        if not docx_available():
            raise CommandError(
                "python-docx is not installed, so no .docx can be written. "
                "Install it with: pip install python-docx"
            )

        out_dir = options["out"]
        if options["all"]:
            papers = self._all_papers()
        else:
            papers = [self._one_paper(options["grade"], options["variant"])]

        # Only create the directory once the papers are known to exist, so a
        # failed run does not leave an empty directory behind suggesting it
        # half-worked.
        os.makedirs(out_dir, exist_ok=True)

        for paper in papers:
            student_path = os.path.join(out_dir, f"{paper}-Student.docx")
            key_path = os.path.join(out_dir, f"{paper}-AnswerKey.docx")
            student_docx(paper).save(student_path)
            answer_key_docx(paper).save(key_path)
            self.stdout.write(f"{student_path}\n{key_path}")

        self.stdout.write(self.style.SUCCESS(
            f"Rendered {len(papers)} paper(s) to {os.path.abspath(out_dir)}."
        ))

    # ------------------------------------------------------------------ lookup

    def _one_paper(self, grade, variant):
        if grade is None or not variant:
            raise CommandError(
                "Give --grade and --variant, or pass --all to render every paper."
            )
        try:
            return Paper.objects.select_related(
                "listening_set_1__clip", "listening_set_2__clip", "reading_passage"
            ).get(grade=grade, variant=variant)
        except Paper.DoesNotExist:
            raise CommandError(
                f"No paper G{grade}-{variant}. Run build_papers first, or check "
                f"the grade/variant."
            ) from None

    def _all_papers(self):
        papers = list(
            Paper.objects.select_related(
                "listening_set_1__clip", "listening_set_2__clip", "reading_passage"
            ).order_by("grade", "variant")
        )
        if not papers:
            raise CommandError("No papers exist yet. Run build_papers first.")
        missing = [
            f"G{grade}-{variant}"
            for grade in GRADES
            for variant in VARIANTS
            if not any(p.grade == grade and p.variant == variant for p in papers)
        ]
        if missing:
            raise CommandError(
                f"Cannot render the full pack, these papers are missing: "
                f"{', '.join(missing)}. Run build_papers first."
            )
        return papers
