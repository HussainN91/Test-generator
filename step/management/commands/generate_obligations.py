"""Creates the next period's obligations. Scheduled, and safe to re-run."""

from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from step import generation
from step.models import AcademicYear, Activity, Term


class Command(BaseCommand):
    help = "Generate obligation instances for a month and/or a term. Idempotent."

    def add_arguments(self, parser):
        parser.add_argument("--month", help='Month to generate, as YYYY-MM. Defaults to today.')
        parser.add_argument("--term", help="Term name within the current academic year.")
        parser.add_argument(
            "--checkpoints", action="store_true",
            help="Also generate this year's beginning/mid/end-of-year diagnostic obligations.",
        )
        parser.add_argument(
            "--sessions", action="store_true",
            help="Also generate ECA monthly-plan obligations and materialise upcoming "
                 "Session rows for every active activity.",
        )

    def handle(self, *args, **options):
        total = 0
        current = None  # resolved lazily so --month-only runs don't need a current year

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

        if options.get("checkpoints"):
            current = current or AcademicYear.objects.filter(is_current=True).first()
            if current is None:
                raise CommandError("No academic year is marked current.")
            total += generation.generate_checkpoint_obligations(current)

        if options.get("sessions"):
            total += generation.generate_activity_plan_obligations(month_start)

            sessions_created = 0
            active_activities = Activity.objects.filter(
                Q(archived_on__isnull=True) | Q(archived_on__gte=date.today())
            )
            for activity in active_activities:
                sessions_created += generation.generate_sessions(
                    activity,
                    through=date.today() + timedelta(days=generation.SESSION_GENERATION_HORIZON_DAYS),
                )

            self.stdout.write(
                self.style.SUCCESS(f"Created {total} obligations and {sessions_created} sessions.")
            )
        else:
            self.stdout.write(self.style.SUCCESS(f"Created {total} obligations."))
