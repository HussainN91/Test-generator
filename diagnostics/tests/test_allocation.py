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

from diagnostics.allocation import Allocation, allocate, allocate_group
from diagnostics.constants import (
    CLIP_TASK_TYPES, GRADES, PICTURE_CLIPS, REUSE_CAPS, TaskType, VARIANTS,
)
from diagnostics.navigation import (
    GROUP_NUMBERS, group_for_variant, variants_for_group,
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
                result = allocate(grade, variant)
                self.assertIn(result.picture_clip, PICTURE_CLIPS, f"G{grade}-{variant}")
                self.assertNotIn(result.rotating_clip, PICTURE_CLIPS, f"G{grade}-{variant}")

    def test_the_two_clips_are_never_the_same(self):
        for grade in GRADES:
            for variant in VARIANTS:
                result = allocate(grade, variant)
                self.assertNotEqual(result.picture_clip, result.rotating_clip)

    def test_reuse_caps_are_respected_within_each_grade(self):
        for grade in GRADES:
            pictures, rotators, passages = Counter(), Counter(), Counter()
            for variant in VARIANTS:
                result = allocate(grade, variant)
                pictures[result.picture_clip] += 1
                rotators[result.rotating_clip] += 1
                passages[result.passage] += 1
            self.assertLessEqual(max(pictures.values()), REUSE_CAPS["picture_clip"])
            self.assertLessEqual(max(rotators.values()), REUSE_CAPS["rotating_clip"])
            self.assertLessEqual(max(passages.values()), REUSE_CAPS["reading_passage"])

    def test_rotating_task_types_are_evenly_spread(self):
        """No grade may lean on one task type.

        The rotating clip is now drawn once per group (8 groups per grade)
        and both of a group's variants inherit it, so the fairest possible
        split - 8 groups over 3 types is 3/3/2 - gets doubled to 6/6/4 at the
        16-variant level. That doubled gap of 2 is a mathematical floor, not
        a tuning knob: 8 is not divisible by 3, and no indexing scheme
        changes that. A gap of exactly 2 is fine; a total collapse onto
        fewer types is still caught by the len(types) == 3 check below, so
        this bound's job is catching a round-robin skewed worse than the
        structural 6/6/4, not a missing type.
        """
        for grade in GRADES:
            types = Counter(
                CLIP_TASK_TYPES[allocate(grade, v).rotating_clip] for v in VARIANTS
            )
            self.assertEqual(len(types), 3, f"G{grade} used {len(types)} types")
            self.assertLessEqual(max(types.values()) - min(types.values()), 2)

    def test_no_two_variants_in_a_grade_share_a_combination(self):
        for grade in GRADES:
            combos = [allocate(grade, v) for v in VARIANTS]
            self.assertEqual(len(set(combos)), len(VARIANTS))

    def test_rejects_an_unknown_variant(self):
        with self.assertRaises(ValueError):
            allocate(9, "Z")


class GroupAllocationTests(SimpleTestCase):
    """A group is one room at one time playing one recording, so both its
    variants must draw the same clip pair - and then differ on everything
    else, or the two papers are the same paper."""

    def test_both_variants_in_a_group_get_the_same_clip_pair(self):
        for grade in GRADES:
            for group in GROUP_NUMBERS:
                first, second = variants_for_group(group)
                a, b = allocate(grade, first), allocate(grade, second)
                self.assertEqual(
                    (a.picture_clip, a.rotating_clip),
                    (b.picture_clip, b.rotating_clip),
                    f"G{grade} group {group} ({first}/{second}) would need two "
                    f"recordings in one room",
                )

    def test_the_two_variants_in_a_group_get_different_set_numbers(self):
        for grade in GRADES:
            for group in GROUP_NUMBERS:
                first, second = variants_for_group(group)
                self.assertNotEqual(
                    allocate(grade, first).set_number,
                    allocate(grade, second).set_number,
                )

    def test_set_numbers_are_always_one_or_two(self):
        for grade in GRADES:
            for variant in VARIANTS:
                self.assertIn(allocate(grade, variant).set_number, (1, 2))

    def test_the_two_variants_in_a_group_get_different_passages(self):
        for grade in GRADES:
            for group in GROUP_NUMBERS:
                first, second = variants_for_group(group)
                self.assertNotEqual(
                    allocate(grade, first).passage,
                    allocate(grade, second).passage,
                    f"G{grade} group {group} shares a reading passage",
                )

    def test_a_rotating_clip_never_serves_two_groups_in_one_grade(self):
        """The new invariant. A rotating clip's uses within a grade must all
        fall inside one group: 15 clips against 8 groups leaves room, and a
        clip crossing a group boundary would mean two sittings hearing the
        same recording for no reason."""
        for grade in GRADES:
            owners = {}
            for variant in VARIANTS:
                clip = allocate(grade, variant).rotating_clip
                group = group_for_variant(variant)
                owners.setdefault(clip, set()).add(group)
            for clip, groups in owners.items():
                self.assertEqual(
                    len(groups), 1,
                    f"G{grade}: rotating clip {clip} serves groups {sorted(groups)}",
                )

    def test_a_picture_clip_serves_at_most_two_groups_in_one_grade(self):
        """Five picture clips against eight groups forces sharing: three
        clips take two groups each, two take one. More than two would push
        the clip past REUSE_CAPS["picture_clip"] of 4 paper-uses."""
        for grade in GRADES:
            owners = {}
            for variant in VARIANTS:
                clip = allocate(grade, variant).picture_clip
                owners.setdefault(clip, set()).add(group_for_variant(variant))
            for clip, groups in owners.items():
                self.assertLessEqual(
                    len(groups), 2,
                    f"G{grade}: picture clip {clip} serves groups {sorted(groups)}",
                )

    def test_every_picture_clip_in_the_bank_is_used_each_grade(self):
        for grade in GRADES:
            used = {allocate(grade, v).picture_clip for v in VARIANTS}
            self.assertEqual(used, set(PICTURE_CLIPS), f"grade {grade}")

    def test_allocate_group_and_allocate_agree(self):
        for grade in GRADES:
            for group in GROUP_NUMBERS:
                picture, rotating = allocate_group(grade, group)
                for variant in variants_for_group(group):
                    result = allocate(grade, variant)
                    self.assertEqual(result.picture_clip, picture)
                    self.assertEqual(result.rotating_clip, rotating)

    def test_unknown_group_is_rejected(self):
        with self.assertRaises(ValueError):
            allocate_group(9, 0)
        with self.assertRaises(ValueError):
            allocate_group(9, 9)
