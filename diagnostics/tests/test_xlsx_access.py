"""Confirms the real content workbook is readable before anything depends on it."""

from django.conf import settings
from django.test import TestCase

WORKBOOK = settings.DIAGNOSTICS_SOURCE_DIR / "Question Bank -Diagnostic Test.xlsx"


class WorkbookAccessTests(TestCase):
    def test_workbook_exists(self):
        self.assertTrue(WORKBOOK.exists(), f"Missing: {WORKBOOK}")

    def test_workbook_has_the_expected_tabs(self):
        import openpyxl

        workbook = openpyxl.load_workbook(WORKBOOK, data_only=True, read_only=True)
        expected = {
            "Overall Pattern", "CEFR Conversion table LRW", "Speaking QB",
            "Reading QB with answers", "Listening QB", "Speaking Assessment Rubrics",
            "Writing QB with key", "Writing sample Question papers ",
        }
        self.assertEqual(set(workbook.sheetnames), expected)
