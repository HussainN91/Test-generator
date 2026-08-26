"""The allocator decides which fixed content each of the 48 papers gets.

These tests exist because the allocation is the one part of paper assembly
that must never change between runs. build_papers uses update_or_create for
listening and reading, so those fields are rewritten every single build; if
the allocator were not deterministic, re-running the build would reissue
different content under the same paper name and two teachers holding "G9-A"
would be administering different tests.
"""

from collections import Counter
from django.test import SimpleTestCase

from diagnostics.allocation import allocate
from diagnostics.constants import (
    CLIP_TASK_TYPES, GRADES, PICTURE_CLIPS, REUSE_CAPS, TaskType, VARIANTS,
)


class AllocationTests(SimpleTestCase):
    def test_is_deterministic(self):
        first = {(g, v): allocate(g, v) for g in GRADES for v in VARIANTS}
        second = {(g, v): allocate(g, v) for g in GRADES for v in VARIANTS}
        self.assertEqual(first, second)

    def test_every_paper_gets_exactly_one_picture_clip(self):
        """The whole point of the rebalance: 5 photo questions on every
        paper, not 5 on half of them and 0 on the other half."""
        for grade in GRADES:
            for variant in VARIANTS:
                picture, rotating, _passage = allocate(grade, variant)
                self.assertIn(picture, PICTURE_CLIPS, f"G{grade}-{variant}")
                self.assertNotIn(rotating, PICTURE_CLIPS, f"G{grade}-{variant}")

    def test_the_two_clips_are_never_the_same(self):
        for grade in GRADES:
            for variant in VARIANTS:
                picture, rotating, _ = allocate(grade, variant)
                self.assertNotEqual(picture, rotating)

    def test_reuse_caps_are_respected_within_each_grade(self):
        for grade in GRADES:
            pictures, rotators, passages = Counter(), Counter(), Counter()
            for variant in VARIANTS:
                picture, rotating, passage = allocate(grade, variant)
                pictures[picture] += 1
                rotators[rotating] += 1
                passages[passage] += 1
            self.assertLessEqual(max(pictures.values()), REUSE_CAPS["picture_clip"])
            self.assertLessEqual(max(rotators.values()), REUSE_CAPS["rotating_clip"])
            self.assertLessEqual(max(passages.values()), REUSE_CAPS["reading_passage"])

    def test_rotating_task_types_are_evenly_spread(self):
        """No grade may lean on one task type. With 16 variants across three
        types the fairest split is 6/5/5, so no type may appear more than
        twice as often as another."""
        for grade in GRADES:
            types = Counter(
                CLIP_TASK_TYPES[allocate(grade, v)[1]] for v in VARIANTS
            )
            self.assertEqual(len(types), 3, f"G{grade} used {len(types)} types")
            self.assertLessEqual(max(types.values()) - min(types.values()), 1)

    def test_no_two_variants_in_a_grade_share_a_combination(self):
        for grade in GRADES:
            combos = [allocate(grade, v) for v in VARIANTS]
            self.assertEqual(len(set(combos)), len(VARIANTS))

    def test_rejects_an_unknown_variant(self):
        with self.assertRaises(ValueError):
            allocate(9, "Z")
