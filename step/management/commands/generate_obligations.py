"""Creates the next period's obligations. Scheduled, and safe to re-run."""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from step import generation
from step.models import AcademicYear, Term


class Command(BaseCommand):
    help = "Generate obligation instances for a month and/or a term. Idempotent."

    def add_arguments(self, parser):
        parser.add_argument("--month", help='Month to generate, as YYYY-MM. Defaults to today.')
        parser.add_argument("--term", help="Term name within the current academic year.")

    def handle(self, *args, **options):
        total = 0

        raw_month = options.get("month")
        if raw_month:
            try:
                year, month = raw_month.split("-")
                month_start = date(int(year), int(month), 1)
            except (ValueError, TypeError) as exc:
                raise CommandError(f"--month must look like 2026-05, got {raw_month!r}") from exc
        else:
            month_start = date.today().replace(day=1)

        total += generation.generate_for_month(month_start)

        term_name = options.get("term")
        if term_name:
            current = AcademicYear.objects.filter(is_current=True).first()
            if current is None:
                raise CommandError("No academic year is marked current.")
            term = Term.objects.filter(year=current, name=term_name).first()
            if term is None:
                raise CommandError(f"No term named {term_name!r} in {current.label}.")
            total += generation.generate_for_term(term)

        self.stdout.write(self.style.SUCCESS(f"Created {total} obligations."))
