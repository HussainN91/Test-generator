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
