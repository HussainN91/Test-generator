from django.conf import settings
from django.test import TestCase

from diagnostics.extraction.xlsx_speaking import extract_rubric, extract_speaking_prompts

WORKBOOK = settings.DIAGNOSTICS_SOURCE_DIR / "Question Bank -Diagnostic Test.xlsx"


class ExtractSpeakingTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not WORKBOOK.exists():
            raise AssertionError(f"Source file missing: {WORKBOOK}")
        cls.prompts = extract_speaking_prompts(WORKBOOK)
        cls.rubric = extract_rubric(WORKBOOK)

    def test_fifty_prompts_total(self):
        self.assertEqual(len(self.prompts), 50)

    def test_ten_per_task(self):
        from collections import Counter

        from diagnostics.constants import SPEAKING_TASK_ORDER

        counts = Counter(p["task"] for p in self.prompts)
        for task in SPEAKING_TASK_ORDER:
            self.assertEqual(counts.get(task), 10, task)

    def test_rubric_has_all_five_tasks(self):
        from diagnostics.constants import SPEAKING_TASK_ORDER

        self.assertEqual(sorted(self.rubric), sorted(SPEAKING_TASK_ORDER))

    def test_rubric_marks_sum_to_ten(self):
        self.assertEqual(sum(entry["marks"] for entry in self.rubric.values()), 10)
