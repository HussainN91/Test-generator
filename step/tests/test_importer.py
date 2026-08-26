"""Re-importing an updated sheet must never destroy people (spec §4.2).

The sheet is a living source of truth: it grows, it gets re-exported, and rows
disappear for mundane reasons. A person who vanishes is flagged, not deleted,
because deletion would cascade away their entire submission history.
"""

import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings
from openpyxl import Workbook

from step.models import Educator, Region, RosterImport, School, UnresolvedRow
from step.roster import importer

MEDIA = tempfile.mkdtemp()


def write_sheet(rows, headers=("Full Name", "Email", "Region", "School")):
    """Write a temporary .xlsx and return its path.

    Django's TestCase rolls back the database but NOT file writes, so these go
    to a temp directory that the class cleans up.
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(list(headers))
    for row in rows:
        sheet.append(list(row))
    path = Path(tempfile.mkstemp(suffix=".xlsx")[1])
    workbook.save(path)
    return path


@override_settings(MEDIA_ROOT=MEDIA, STEP_ROSTER_MATCH_KEYS=["email"])
class ImportRosterTests(TestCase):
    def setUp(self):
        call_command("seed_geography", stdout=StringIO())

    def test_creates_educators_schools_and_records_the_import(self):
        path = write_sheet([
            ("Maria Santos", "maria@example.com", "Samarkand", "International School 4"),
            ("John Cruz", "john@example.com", "Fergana", "School 12"),
        ])
        result = importer.import_file(path)

        self.assertEqual(Educator.objects.count(), 2)
        self.assertEqual(School.objects.count(), 2)
        self.assertEqual(result.created_count, 2)
        self.assertEqual(result.updated_count, 0)
        self.assertEqual(RosterImport.objects.count(), 1)

    def test_unmapped_columns_are_preserved(self):
        path = write_sheet(
            [("Maria Santos", "maria@example.com", "Samarkand", "Contract A")],
            headers=("Full Name", "Email", "Region", "Contract Type"),
        )
        importer.import_file(path)
        educator = Educator.objects.get(email="maria@example.com")
        self.assertEqual(educator.source_fields["Contract Type"], "Contract A")

    def test_reimport_updates_in_place_and_does_not_duplicate(self):
        first = write_sheet([("Maria Santos", "maria@example.com", "Samarkand", "School A")])
        importer.import_file(first)

        second = write_sheet([("Maria Santos-Cruz", "maria@example.com", "Samarkand", "School A")])
        result = importer.import_file(second)

        self.assertEqual(Educator.objects.count(), 1)
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.updated_count, 1)
        self.assertEqual(Educator.objects.get().full_name, "Maria Santos-Cruz")

    def test_a_person_missing_from_a_reimport_is_flagged_not_deleted(self):
        first = write_sheet([
            ("Maria Santos", "maria@example.com", "Samarkand", "School A"),
            ("John Cruz", "john@example.com", "Fergana", "School B"),
        ])
        importer.import_file(first)

        second = write_sheet([("Maria Santos", "maria@example.com", "Samarkand", "School A")])
        importer.import_file(second)

        self.assertEqual(Educator.objects.count(), 2)
        self.assertTrue(Educator.objects.get(email="john@example.com").missing_from_last_import)
        self.assertFalse(Educator.objects.get(email="maria@example.com").missing_from_last_import)

    def test_returning_to_the_sheet_clears_the_missing_flag(self):
        both = [
            ("Maria Santos", "maria@example.com", "Samarkand", "School A"),
            ("John Cruz", "john@example.com", "Fergana", "School B"),
        ]
        importer.import_file(write_sheet(both))
        importer.import_file(write_sheet(both[:1]))
        importer.import_file(write_sheet(both))
        self.assertFalse(Educator.objects.get(email="john@example.com").missing_from_last_import)

    def test_an_unresolvable_region_becomes_an_unresolved_row(self):
        path = write_sheet([("Maria Santos", "maria@example.com", "Atlantis", "School A")])
        result = importer.import_file(path)

        self.assertEqual(Educator.objects.count(), 0)
        self.assertEqual(result.unresolved_count, 1)
        row = UnresolvedRow.objects.get()
        self.assertIn("region", row.reason.lower())
        self.assertEqual(row.payload["Full Name"], "Maria Santos")

    def test_a_row_with_no_identity_value_is_unresolved(self):
        path = write_sheet([("Maria Santos", "", "Samarkand", "School A")])
        result = importer.import_file(path)
        self.assertEqual(result.unresolved_count, 1)
        self.assertEqual(Educator.objects.count(), 0)

    def test_an_insufficient_sheet_raises_before_writing_anything(self):
        path = write_sheet(
            [("Maria Santos", "Contract A")], headers=("Full Name", "Contract Type")
        )
        with self.assertRaises(importer.InsufficientMapping):
            importer.import_file(path)
        self.assertEqual(Educator.objects.count(), 0)
        self.assertEqual(RosterImport.objects.count(), 0)

    def test_a_district_column_alone_places_the_educator(self):
        path = write_sheet(
            [("Maria Santos", "maria@example.com", "Kokand")],
            headers=("Full Name", "Email", "District"),
        )
        importer.import_file(path)
        educator = Educator.objects.get()
        self.assertEqual(educator.district.code, "kokand")
        self.assertEqual(educator.region.code, "fergana")

    def test_the_confirmed_mapping_is_stored_on_the_import(self):
        path = write_sheet([("Maria Santos", "maria@example.com", "Samarkand", "School A")])
        importer.import_file(path)
        stored = RosterImport.objects.get().mapping
        self.assertEqual(stored["Email"], "email")
        self.assertEqual(stored["Region"], "region")


@override_settings(MEDIA_ROOT=MEDIA, STEP_ROSTER_MATCH_KEYS=["email"])
class ImportRosterCommandTests(TestCase):
    def setUp(self):
        call_command("seed_geography", stdout=StringIO())

    def test_dry_run_reports_without_writing(self):
        path = write_sheet([("Maria Santos", "maria@example.com", "Samarkand", "School A")])
        out = StringIO()
        call_command("import_roster", str(path), "--dry-run", stdout=out)
        self.assertIn("would create 1", out.getvalue().lower())
        self.assertEqual(Educator.objects.count(), 0)

    def test_command_imports(self):
        path = write_sheet([("Maria Santos", "maria@example.com", "Samarkand", "School A")])
        call_command("import_roster", str(path), stdout=StringIO())
        self.assertEqual(Educator.objects.count(), 1)
