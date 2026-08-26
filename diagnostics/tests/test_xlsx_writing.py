from django.conf import settings
from django.test import TestCase

from diagnostics.extraction.xlsx_writing import extract_writing_items

WORKBOOK = settings.DIAGNOSTICS_SOURCE_DIR / "Question Bank -Diagnostic Test.xlsx"


class ExtractWritingItemsTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not WORKBOOK.exists():
            raise AssertionError(f"Source file missing: {WORKBOOK}")
        cls.items = extract_writing_items(WORKBOOK)

    def test_two_hundred_items_total(self):
        self.assertEqual(len(self.items), 200)

    def test_fifty_of_each_subtype(self):
        from collections import Counter

        counts = Counter(item["subtype"] for item in self.items)
        self.assertEqual(
            counts,
            Counter({"grammar": 50, "vocabulary": 50, "jumbled": 50, "fill_blank": 50}),
        )

    def test_every_item_has_four_options_and_a_letter_answer(self):
        for item in self.items:
            self.assertEqual(len(item["options"]), 4, item["stem"])
            self.assertIn(item["answer"], {"A", "B", "C", "D"}, item["stem"])

    def test_known_first_grammar_item(self):
        first = next(i for i in self.items if i["subtype"] == "grammar")
        self.assertIn("Maria", first["stem"])
        self.assertEqual(first["answer"], "B")

    def test_known_data_inconsistency_item_135_resolves_to_master_key(self):
        # Source data quirk, verified 2026-08-25: item 135's inline sentence-
        # order text says "D-A-B-C" but the master answer key says "C" - the
        # master key is authoritative (per Design Revision 1), so the answer
        # must be "C", not "D". This test guards against that resolution
        # silently reversing if the extractor changes.
        jumbled_items = [item for item in self.items if item["subtype"] == "jumbled"]
        item_135 = jumbled_items[34]  # 135 is the 35th jumbled item (101-150 range)
        self.assertEqual(item_135["answer"], "C")
