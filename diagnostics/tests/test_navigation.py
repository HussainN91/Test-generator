"""The class-pack split is derived, not stored, so these tests are what stop
it drifting: every variant must land in exactly one pack, and the packs must
stay the same size as each other."""

from django.test import TestCase

from diagnostics.constants import VARIANTS
from diagnostics.navigation import (
    CLASSES_PER_GRADE,
    CLASS_NUMBERS,
    VARIANTS_PER_CLASS,
    class_for_variant,
    variant_span,
    variants_for_class,
)
from diagnostics.navigation import (
    GROUPS_PER_CLASS,
    GROUPS_PER_GRADE,
    GROUP_NUMBERS,
    VARIANTS_PER_GROUP,
    group_for_variant,
    group_span,
    groups_for_class,
    variants_for_group,
)


class PackShapeTests(TestCase):
    def test_four_classes_of_four_papers(self):
        self.assertEqual(CLASSES_PER_GRADE, 4)
        self.assertEqual(VARIANTS_PER_CLASS, 4)
        self.assertEqual(CLASS_NUMBERS, (1, 2, 3, 4))

    def test_every_pack_is_the_same_size(self):
        for number in CLASS_NUMBERS:
            self.assertEqual(len(variants_for_class(number)), VARIANTS_PER_CLASS)

    def test_packs_partition_the_variants_with_none_left_over(self):
        seen = [letter for number in CLASS_NUMBERS for letter in variants_for_class(number)]
        self.assertEqual(seen, list(VARIANTS))


class SequentialGroupingTests(TestCase):
    def test_class_one_takes_the_first_four_letters(self):
        self.assertEqual(variants_for_class(1), ("A", "B", "C", "D"))

    def test_each_class_takes_the_next_four(self):
        self.assertEqual(variants_for_class(2), ("E", "F", "G", "H"))
        self.assertEqual(variants_for_class(3), ("I", "J", "K", "L"))
        self.assertEqual(variants_for_class(4), ("M", "N", "O", "P"))

    def test_span_labels_the_range(self):
        self.assertEqual(variant_span(1), "A-D")
        self.assertEqual(variant_span(4), "M-P")


class ReverseLookupTests(TestCase):
    def test_variant_maps_back_to_its_own_pack(self):
        for number in CLASS_NUMBERS:
            for letter in variants_for_class(number):
                self.assertEqual(class_for_variant(letter), number)

    def test_unknown_variant_is_rejected(self):
        with self.assertRaises(ValueError):
            class_for_variant("Z")

    def test_class_outside_the_range_is_rejected(self):
        for number in (0, 5, -1):
            with self.assertRaises(ValueError):
                variants_for_class(number)


class GroupShapeTests(TestCase):
    """A group is one sitting: one room, one time, one recording. Two groups
    make a class, so eight groups make a grade."""

    def test_two_groups_per_class_of_two_papers_each(self):
        self.assertEqual(GROUPS_PER_CLASS, 2)
        self.assertEqual(VARIANTS_PER_GROUP, 2)

    def test_eight_groups_per_grade(self):
        self.assertEqual(GROUPS_PER_GRADE, 8)
        self.assertEqual(GROUP_NUMBERS, (1, 2, 3, 4, 5, 6, 7, 8))

    def test_every_group_is_the_same_size(self):
        for number in GROUP_NUMBERS:
            self.assertEqual(len(variants_for_group(number)), VARIANTS_PER_GROUP)

    def test_groups_partition_the_variants_with_none_left_over(self):
        seen = [v for n in GROUP_NUMBERS for v in variants_for_group(n)]
        self.assertEqual(seen, list(VARIANTS))


class GroupSequencingTests(TestCase):
    def test_group_one_is_the_first_two_letters(self):
        self.assertEqual(variants_for_group(1), ("A", "B"))

    def test_each_group_takes_the_next_two(self):
        self.assertEqual(variants_for_group(2), ("C", "D"))
        self.assertEqual(variants_for_group(3), ("E", "F"))
        self.assertEqual(variants_for_group(8), ("O", "P"))

    def test_span_labels_the_pair(self):
        self.assertEqual(group_span(1), "A-B")
        self.assertEqual(group_span(8), "O-P")


class GroupClassNestingTests(TestCase):
    """A group never straddles two classes - the split is 4 into 2+2."""

    def test_each_class_holds_exactly_two_groups(self):
        for number in CLASS_NUMBERS:
            self.assertEqual(len(groups_for_class(number)), GROUPS_PER_CLASS)

    def test_class_one_holds_groups_one_and_two(self):
        self.assertEqual(groups_for_class(1), (1, 2))
        self.assertEqual(groups_for_class(4), (7, 8))

    def test_a_group_variants_all_belong_to_one_class(self):
        for number in GROUP_NUMBERS:
            classes = {class_for_variant(v) for v in variants_for_group(number)}
            self.assertEqual(len(classes), 1, f"group {number} straddles {classes}")


class GroupReverseLookupTests(TestCase):
    def test_variant_maps_back_to_its_own_group(self):
        for number in GROUP_NUMBERS:
            for letter in variants_for_group(number):
                self.assertEqual(group_for_variant(letter), number)

    def test_unknown_variant_is_rejected(self):
        with self.assertRaises(ValueError):
            group_for_variant("Z")

    def test_group_outside_the_range_is_rejected(self):
        for number in (0, 9, -1):
            with self.assertRaises(ValueError):
                variants_for_group(number)

    def test_class_outside_the_range_is_rejected(self):
        for number in (0, 5, -1):
            with self.assertRaises(ValueError):
                groups_for_class(number)


class PartnerVariantTests(TestCase):
    def test_partner_is_the_other_variant_in_the_group(self):
        from diagnostics.navigation import partner_variant
        self.assertEqual(partner_variant("A"), "B")
        self.assertEqual(partner_variant("B"), "A")
        self.assertEqual(partner_variant("P"), "O")

    def test_partner_is_symmetric_for_every_variant(self):
        from diagnostics.navigation import partner_variant
        for letter in VARIANTS:
            self.assertEqual(partner_variant(partner_variant(letter)), letter)

    def test_a_variant_is_never_its_own_partner(self):
        from diagnostics.navigation import partner_variant
        for letter in VARIANTS:
            self.assertNotEqual(partner_variant(letter), letter)
