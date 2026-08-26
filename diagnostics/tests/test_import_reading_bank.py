from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diagnostics.extraction.xlsx_reading import (
    VERIFIED_MATCHING_ITEMS,
    resolve_subtype,
)
from diagnostics.models import ReadingPassage, ReadingQuestion, ReadingSubtype


class ImportReadingBankTests(TestCase):
    def test_imports_fifteen_passages_and_one_hundred_fifty_questions(self):
        call_command("import_reading_bank", stdout=StringIO())
        self.assertEqual(ReadingPassage.objects.count(), 15)
        self.assertEqual(ReadingQuestion.objects.count(), 150)

    def test_idempotent(self):
        call_command("import_reading_bank", stdout=StringIO())
        call_command("import_reading_bank", stdout=StringIO())
        self.assertEqual(ReadingPassage.objects.count(), 15)

    def test_matching_items_are_not_imported_as_mcq(self):
        """R04 Q6-10 and R10 Q9-10 are match-to-paragraph items, not MCQs.

        They arrive with no options and answers outside A-D (R04 Q10 is 'E'),
        which is impossible for a four-option MCQ. Importing them as 'mcq'
        produces a question a student cannot answer: an MCQ with no choices.
        """
        call_command("import_reading_bank", stdout=StringIO())
        stray = [
            q for q in ReadingQuestion.objects.filter(subtype=ReadingSubtype.MCQ)
            if not q.options
        ]
        self.assertEqual(
            stray, [],
            f"{len(stray)} MCQ questions have no options: "
            f"{[(q.passage.label, q.position) for q in stray]}",
        )

    def test_paragraph_matching_items_keep_their_answers(self):
        call_command("import_reading_bank", stdout=StringIO())
        matched = ReadingQuestion.objects.filter(
            passage__label="R04", position__in=[6, 7, 8, 9, 10],
        ).order_by("position")
        self.assertEqual(
            [q.subtype for q in matched],
            [ReadingSubtype.PARAGRAPH_MATCHING] * 5,
        )
        self.assertEqual([q.answer for q in matched], ["D", "A", "C", "B", "E"])

    def test_unverified_option_less_mcq_raises(self):
        """An option-less mcq at a position NOT in VERIFIED_MATCHING_ITEMS must
        raise, not be silently converted - that's what catches a genuinely new
        source anomaly instead of misclassifying it as paragraph_matching.
        """
        self.assertNotIn(("R01", 1), VERIFIED_MATCHING_ITEMS)
        with self.assertRaises(ValueError):
            resolve_subtype(ReadingSubtype.MCQ, [], "R01", 1)

    def test_verified_option_less_mcq_does_not_raise(self):
        """The 7 independently-verified positions must NOT raise - they are
        the known-safe cases resolve_subtype() is allowed to convert."""
        for label, position in VERIFIED_MATCHING_ITEMS:
            resolve_subtype(ReadingSubtype.MCQ, [], label, position)

    def test_mcq_with_options_never_raises(self):
        """A real MCQ (has options) is never affected by this guard,
        regardless of position."""
        resolve_subtype(ReadingSubtype.MCQ, ["A", "B", "C", "D"], "R01", 1)
