"""The bank's shape is fixed and verified; these tests lock it in."""

from collections import Counter

from django.test import SimpleTestCase, TestCase

from diagnostics.constants import (
    CLIP_TASK_TYPES,
    IMAGE_SLOTS,
    REUSE_CAPS,
    VARIANTS,
    TaskType,
)


class PassageWordBoundsTests(TestCase):
    def test_bounds_cover_the_real_bank_range(self):
        from diagnostics.constants import MAX_PASSAGE_WORDS, MIN_PASSAGE_WORDS
        # Real bank range, verified 2026-08-24: 203-274 words across 15 passages.
        self.assertLessEqual(MIN_PASSAGE_WORDS, 200)
        self.assertGreaterEqual(MAX_PASSAGE_WORDS, 280)


class ClipTaskTypeTests(TestCase):
    def test_all_twenty_clips_are_typed(self):
        self.assertEqual(sorted(CLIP_TASK_TYPES), list(range(1, 21)))

    def test_bank_is_balanced_five_of_each_type(self):
        counts = Counter(CLIP_TASK_TYPES.values())
        self.assertEqual(
            counts,
            Counter({TaskType.PICTURE: 5, TaskType.MCQ3: 5,
                     TaskType.GAP_FILL: 5, TaskType.TRUE_FALSE: 5}),
        )


class ImageSlotTests(TestCase):
    def test_twenty_five_slots_in_document_order(self):
        self.assertEqual(len(IMAGE_SLOTS), 25)

    def test_slots_group_five_per_picture_clip(self):
        self.assertEqual(IMAGE_SLOTS[0], (1, 1))
        self.assertEqual(IMAGE_SLOTS[4], (1, 5))
        self.assertEqual(IMAGE_SLOTS[5], (5, 1))
        self.assertEqual(IMAGE_SLOTS[24], (15, 5))

    def test_slots_only_reference_picture_clips(self):
        clips = {clip for clip, _ in IMAGE_SLOTS}
        self.assertEqual(clips, {1, 5, 9, 13, 15})


class VariantTests(TestCase):
    def test_sixteen_variants_per_grade(self):
        self.assertEqual(len(VARIANTS), 16)
        self.assertEqual(VARIANTS[0], "A")
        self.assertEqual(VARIANTS[-1], "P")
        self.assertEqual(len(set(VARIANTS)), 16)

    def test_every_variant_label_is_one_character(self):
        """Paper.variant is max_length=1; a two-character label would be
        silently truncated to a duplicate of another variant."""
        for variant in VARIANTS:
            self.assertEqual(len(variant), 1, variant)


class ReuseCapTests(TestCase):
    def test_reuse_caps_cover_every_capped_component(self):
        self.assertEqual(
            set(REUSE_CAPS),
            {"picture_clip", "rotating_clip", "reading_passage",
             "speaking_prompt", "writing_question"},
        )

    def test_caps_supply_enough_slots_for_sixteen_variants(self):
        """Each cap must yield at least 16 usable slots per grade, or the
        48-paper build is unsatisfiable before it starts."""
        pools = {
            "picture_clip": 5, "rotating_clip": 15, "reading_passage": 15,
            "speaking_prompt": 10, "writing_question": 50,
        }
        for component, pool in pools.items():
            slots = pool * REUSE_CAPS[component]
            self.assertGreaterEqual(
                slots, len(VARIANTS),
                f"{component}: {pool} items x cap {REUSE_CAPS[component]} "
                f"= {slots} slots, need {len(VARIANTS)}",
            )


class StemCorrectionTests(SimpleTestCase):
    """The client's source .md has four typos we correct on import. Keyed by
    (clip number, position) so a correction can never be applied to the wrong
    question if the source is re-split."""

    def test_all_four_corrections_are_present(self):
        from diagnostics.constants import STEM_CORRECTIONS
        self.assertEqual(
            sorted(STEM_CORRECTIONS), [(1, 4), (5, 4), (6, 5), (13, 3)]
        )

    def test_each_correction_names_the_wrong_text_and_the_right_text(self):
        from diagnostics.constants import STEM_CORRECTIONS
        for slot, (wrong, right) in STEM_CORRECTIONS.items():
            self.assertNotEqual(wrong, right, slot)
            self.assertTrue(wrong.strip(), slot)
            self.assertTrue(right.strip(), slot)

    def test_the_boy_packing_typo_is_corrected(self):
        from diagnostics.constants import STEM_CORRECTIONS
        wrong, right = STEM_CORRECTIONS[(1, 4)]
        self.assertEqual(wrong, "What will the girl take with her on holiday?")
        self.assertEqual(right, "What will the boy take with him on holiday?")
