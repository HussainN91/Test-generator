from django.conf import settings
from django.test import TestCase

from diagnostics.extraction.xlsx_reading import extract_passages

WORKBOOK = settings.DIAGNOSTICS_SOURCE_DIR / "Question Bank -Diagnostic Test.xlsx"


class ExtractPassagesTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not WORKBOOK.exists():
            raise AssertionError(f"Source file missing: {WORKBOOK}")
        cls.passages = extract_passages(WORKBOOK)

    def test_finds_fifteen_passages(self):
        self.assertEqual(len(self.passages), 15)

    def test_every_passage_has_ten_questions(self):
        for passage in self.passages:
            self.assertEqual(len(passage["questions"]), 10, passage["title"])

    def test_every_passage_body_is_within_the_widened_bounds(self):
        from diagnostics.constants import MAX_PASSAGE_WORDS, MIN_PASSAGE_WORDS

        for passage in self.passages:
            count = len(passage["body"].split())
            self.assertTrue(
                MIN_PASSAGE_WORDS <= count <= MAX_PASSAGE_WORDS,
                f"{passage['title']}: {count} words",
            )

    def test_known_passage_one_matches_the_verified_content(self):
        passage = self.passages[0]
        self.assertEqual(passage["title"], "The School Garden")
        self.assertEqual(passage["questions"][0]["subtype"], "true_false_ng")
        self.assertEqual(passage["questions"][0]["answer"], "FALSE")
        self.assertEqual(passage["questions"][8]["answer"], "height")

    def test_heading_matching_passage_is_recognised(self):
        heading_passage = next(
            p for p in self.passages if p["title"] == "Why Some Cities Are Becoming Greener"
        )
        self.assertEqual(heading_passage["questions"][0]["subtype"], "heading_matching")
        self.assertEqual(heading_passage["questions"][0]["answer"], "iii")
