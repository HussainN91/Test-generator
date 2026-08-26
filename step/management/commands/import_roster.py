"""Imports the client roster spreadsheet.

`--dry-run` exists because the sheet's shape is unknown: the safe first move on
any new file is to see what the importer thinks it is looking at.
"""

from django.core.management.base import BaseCommand, CommandError

from step.roster import importer


class Command(BaseCommand):
    help = "Import educators from a roster spreadsheet. Idempotent; never deletes."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--header-row", type=int, default=1)
        parser.add_argument("--dry-run", action="store_true", help="Report without writing.")

    def handle(self, *args, **options):
        try:
            result = importer.import_file(
                options["path"], header_row=options["header_row"], dry_run=options["dry_run"]
            )
        except importer.InsufficientMapping as exc:
            raise CommandError(str(exc)) from exc

        verb = "would create" if options["dry_run"] else "created"
        second = "would update" if options["dry_run"] else "updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{result.row_count} rows: {verb} {result.created_count}, "
                f"{second} {result.updated_count}, {result.unresolved_count} unresolved."
            )
        )
        self.stdout.write(f"Mapping used: {result.mapping}")
