"""Tests for item generation and the validation layer.

The emphasis is on the two failure modes that would actually reach a
classroom: an item with more than one defensible answer, and an item whose
answer is visible in its own prompt.
"""

from django.test import TestCase

from bank.generation.bootstrap import (
    _is_safe_distractor,
    _strip_negative_prefix,
    build_matching_items,
    build_multiple_choice_items,
    build_odd_one_out_items,
    build_word_formation_items,
    generate_for_unit,
)
from bank.generation.validation import validate_item
from bank.models import Item, QuestionType
from bank.presentation import render_question
from content.models import (
    Grade,
    PartOfSpeech,
    Unit,
    VocabularyCategory,
    VocabularyEntry,
)
import random


def entry(unit, word, pos=PartOfSpeech.ADJECTIVE, definition="", category=None, family=""):
    return VocabularyEntry.objects.create(
        unit=unit,
        category=category,
        word=word,
        lemma=word.lower(),
        part_of_speech=pos,
        definition=definition,
        word_family=family,
    )


class BootstrapBaseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.grade = Grade.objects.create(number=10)
        cls.unit = Unit.objects.create(grade=cls.grade, number=1, title="Unit 1")


class DistractorSafetyTests(BootstrapBaseTest):
    def test_near_synonym_is_rejected_as_a_distractor(self):
        target = entry(self.unit, "attractive", definition="Beautiful or pleasant to look at")
        synonym = entry(self.unit, "pretty", definition="Attractive (usually used for a woman)")
        self.assertFalse(_is_safe_distractor(target, synonym))

    def test_unrelated_word_is_an_acceptable_distractor(self):
        target = entry(self.unit, "attractive", definition="Beautiful or pleasant to look at")
        other = entry(self.unit, "bald", definition="With little or no hair")
        self.assertTrue(_is_safe_distractor(target, other))

    def test_definitions_sharing_two_content_words_are_rejected(self):
        target = entry(self.unit, "cheerful", definition="Feeling happy and full of energy")
        overlap = entry(self.unit, "lively", definition="Full of energy and happy spirit")
        self.assertFalse(_is_safe_distractor(target, overlap))


class MultipleChoiceTests(BootstrapBaseTest):
    def test_no_mcq_is_built_without_enough_safe_distractors(self):
        entry(self.unit, "attractive", definition="Beautiful or pleasant to look at")
        entry(self.unit, "pretty", definition="Attractive (usually used for a woman)")
        items = build_multiple_choice_items(self.unit, random.Random(0))
        self.assertEqual(items, [])

    def test_options_are_unique_and_include_the_answer(self):
        entry(self.unit, "bald", definition="With little or no hair")
        entry(self.unit, "curly", definition="Shaped like a curl")
        entry(self.unit, "elderly", definition="A polite word for old")
        entry(self.unit, "shy", definition="Nervous about meeting new faces")
        items = build_multiple_choice_items(self.unit, random.Random(0))
        self.assertTrue(items)
        for item in items:
            options = item.payload["options"]
            self.assertEqual(len(options), len(set(options)), "duplicate options")
            self.assertIn(item.payload["correct_option"], "ABCD")

    def test_definition_restating_the_word_produces_no_item(self):
        # "unfriendly -> Not friendly" gives the answer away.
        entry(self.unit, "friendly", definition="Behaving in a friendly way")
        items = build_multiple_choice_items(self.unit, random.Random(0))
        self.assertEqual(items, [])


class OddOneOutTests(BootstrapBaseTest):
    def setUp(self):
        self.animals = VocabularyCategory.objects.create(unit=self.unit, name="Animals", order=0)
        self.places = VocabularyCategory.objects.create(
            unit=self.unit, name="Geographical Features", order=1
        )
        for word in ("dolphin", "elephant", "giraffe", "monkey"):
            entry(self.unit, word, PartOfSpeech.NOUN, category=self.animals)
        for word in ("valley", "river", "desert", "lake"):
            entry(self.unit, word, PartOfSpeech.NOUN, category=self.places)

    def test_builds_items_with_four_unique_options(self):
        items = build_odd_one_out_items(self.unit, random.Random(1))
        self.assertTrue(items)
        for item in items:
            options = item.payload["options"]
            self.assertEqual(len(options), 4)
            self.assertEqual(len(set(options)), 4)

    def test_items_are_written_as_odd_one_out_not_multiple_choice(self):
        # The two were previously conflated under one question_type, which
        # made a bank of nothing-but-odd-one-out look like a healthy,
        # varied multiple-choice bank from the coverage page.
        items = build_odd_one_out_items(self.unit, random.Random(1))
        self.assertTrue(items)
        for item in items:
            self.assertEqual(item.question_type, QuestionType.ODD_ONE_OUT)

    def test_the_answer_is_the_word_from_the_other_category(self):
        animals = {"dolphin", "elephant", "giraffe", "monkey"}
        for item in build_odd_one_out_items(self.unit, random.Random(1)):
            options = item.payload["options"]
            answer = options["ABCD".index(item.model_answer)]
            in_animals = [o for o in options if o in animals]
            # Either three animals and one outsider, or the mirror image.
            self.assertIn(len(in_animals), (1, 3))
            if len(in_animals) == 3:
                self.assertNotIn(answer, animals)
            else:
                self.assertIn(answer, animals)

    def test_a_word_listed_in_both_categories_is_never_the_odd_one(self):
        entry(self.unit, "dolphin", PartOfSpeech.VERB, category=self.places)
        for item in build_odd_one_out_items(self.unit, random.Random(3)):
            options = item.payload["options"]
            self.assertEqual(len(set(options)), len(options))

    def test_prefix_categories_are_not_treated_as_semantic_fields(self):
        unit = Unit.objects.create(grade=self.grade, number=2)
        prefixes = VocabularyCategory.objects.create(unit=unit, name="Prefixes: Un-, In-", order=0)
        suffixes = VocabularyCategory.objects.create(unit=unit, name="Adjective Suffixes", order=1)
        for word in ("unkind", "unwell", "unfair", "unlucky"):
            entry(unit, word, category=prefixes)
        for word in ("hopeful", "careless", "helpful", "useless"):
            entry(unit, word, category=suffixes)
        self.assertEqual(build_odd_one_out_items(unit, random.Random(0)), [])

    def test_part_1_and_part_2_of_the_same_field_are_never_paired(self):
        unit = Unit.objects.create(grade=self.grade, number=3)
        a = VocabularyCategory.objects.create(unit=unit, name="Animals (Part 1)", order=0)
        b = VocabularyCategory.objects.create(unit=unit, name="Animals (Part 2)", order=1)
        for word in ("dolphin", "elephant", "giraffe"):
            entry(unit, word, category=a)
        for word in ("tiger", "zebra", "camel"):
            entry(unit, word, category=b)
        self.assertEqual(build_odd_one_out_items(unit, random.Random(0)), [])

    def test_a_unit_with_one_usable_category_borrows_an_outsider_from_a_sibling_unit(self):
        # Units 4, 7, 14, 19, 20 of the real grade 9 guide each have exactly
        # one semantic field of their own — not enough to contrast against
        # internally — which used to mean zero items for the whole unit.
        two_unit_grade = Grade.objects.create(number=12)
        lonely = Unit.objects.create(grade=two_unit_grade, number=1, title="Lonely unit")
        appliances = VocabularyCategory.objects.create(unit=lonely, name="Appliances", order=0)
        for word in ("kettle", "toaster", "fridge", "oven"):
            entry(lonely, word, category=appliances)

        sibling = Unit.objects.create(grade=two_unit_grade, number=2, title="Sibling unit")
        weather = VocabularyCategory.objects.create(unit=sibling, name="Weather", order=0)
        for word in ("rain", "storm", "sunshine"):
            entry(sibling, word, category=weather)

        items = build_odd_one_out_items(lonely, random.Random(0))
        self.assertTrue(items, "a unit with one local category should still borrow across the grade")
        for item in items:
            options = item.payload["options"]
            self.assertEqual(len(options), 4)
            self.assertEqual(len(set(options)), 4)
            # The three-word family must still come from the unit itself.
            odd = options["ABCD".index(item.model_answer)]
            family = [o for o in options if o != odd]
            self.assertTrue(all(w in ("kettle", "toaster", "fridge", "oven") for w in family))
            self.assertIn(odd, ("rain", "storm", "sunshine"))

    def test_a_unit_alone_in_its_grade_with_one_category_still_yields_nothing(self):
        # No sibling to borrow from (a fresh grade with only this unit in it):
        # must return [] rather than crash.
        solo_grade = Grade.objects.create(number=11)
        lonely = Unit.objects.create(grade=solo_grade, number=1, title="Only unit")
        appliances = VocabularyCategory.objects.create(unit=lonely, name="Appliances", order=0)
        for word in ("kettle", "toaster", "fridge"):
            entry(lonely, word, category=appliances)
        self.assertEqual(build_odd_one_out_items(lonely, random.Random(0)), [])


class WordFormationTests(BootstrapBaseTest):
    def test_prefix_stripping(self):
        self.assertEqual(_strip_negative_prefix("unhappy"), "happy")
        self.assertEqual(_strip_negative_prefix("disagree"), "agree")
        self.assertIsNone(_strip_negative_prefix("cat"))

    def test_accidental_prefix_match_is_rejected(self):
        # "mistake" is not "mis" + "take": different part of speech, and its
        # definition does not describe a negation.
        entry(self.unit, "take", PartOfSpeech.VERB, definition="To get hold of something")
        entry(self.unit, "mistake", PartOfSpeech.NOUN, definition="Something done wrongly")
        items = build_word_formation_items(self.unit, random.Random(0))
        self.assertEqual(items, [])

    def test_genuine_negation_produces_an_item(self):
        entry(self.unit, "friendly", definition="Behaving in a pleasant way")
        entry(self.unit, "unfriendly", definition="Not friendly")
        items = build_word_formation_items(self.unit, random.Random(0))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].model_answer, "unfriendly")
        self.assertEqual(items[0].payload["root_word"], "friendly")

    def test_word_family_with_two_nouns_is_dropped_as_ambiguous(self):
        # "the noun from ENTERTAIN" has two right answers.
        entry(self.unit, "entertain", PartOfSpeech.VERB, family="entertain")
        entry(self.unit, "entertainer", PartOfSpeech.NOUN, family="entertain")
        entry(self.unit, "entertainment", PartOfSpeech.NOUN, family="entertain")
        items = build_word_formation_items(self.unit, random.Random(0))
        self.assertEqual([i.model_answer for i in items], [])

    def test_homograph_is_never_its_own_answer(self):
        entry(self.unit, "record", PartOfSpeech.NOUN, family="record")
        entry(self.unit, "record", PartOfSpeech.VERB, family="record")
        for item in build_word_formation_items(self.unit, random.Random(0)):
            self.assertNotEqual(
                item.payload["root_word"].lower(), item.payload["correct_form"].lower()
            )


class MatchingTests(BootstrapBaseTest):
    def test_answer_key_matches_the_displayed_columns(self):
        for word, definition in [
            ("charge", "to ask an amount of money for a service"),
            ("discount", "a reduction in price"),
            ("receipt", "a piece of paper proving payment"),
            ("serve", "to help customers in a shop"),
            ("promotions", "activities to advertise something"),
        ]:
            entry(self.unit, word, PartOfSpeech.NOUN, definition=definition)

        draft = build_matching_items(self.unit, random.Random(5))[0]
        item = Item.objects.create(
            unit=self.unit,
            question_type=QuestionType.MATCHING,
            payload=draft.payload,
            model_answer=draft.model_answer,
            content_hash="matching-key-test",
        )
        question = render_question(item)
        rows = question.matching_rows
        by_word = {p["left"]: p["right"] for p in draft.payload["item_set"]}

        # The key reads "1-C, 2-A, ..." — follow each mapping back to the grid
        # and confirm it lands on the definition that word was stored with.
        for mapping in draft.model_answer.split(", "):
            number, letter = mapping.split("-")
            word = rows[int(number) - 1]["left"]
            definition = next(r["right"] for r in rows if r["letter"] == letter)
            self.assertEqual(by_word[word], definition)


class ValidationTests(BootstrapBaseTest):
    def _item(self, question_type, payload, answer=""):
        return Item.objects.create(
            unit=self.unit,
            question_type=question_type,
            payload=payload,
            model_answer=answer,
            content_hash=f"v-{question_type}-{hash(str(payload)) & 0xFFFF}",
        )

    def test_gap_fill_with_the_answer_in_the_prompt_fails(self):
        entry(self.unit, "polite", definition="Behaving well")
        item = self._item(
            QuestionType.GAP_FILL,
            {"sentence_with_gap": "Being polite means being ________.", "target_word": "polite"},
            "polite",
        )
        result = validate_item(item)
        self.assertFalse(result.passed)
        self.assertTrue(any("appears in the prompt" in f for f in result.failures))

    def test_gap_fill_with_two_blanks_fails(self):
        entry(self.unit, "polite", definition="Behaving well")
        item = self._item(
            QuestionType.GAP_FILL,
            {"sentence_with_gap": "He is ________ and ________.", "target_word": "polite"},
            "polite",
        )
        self.assertFalse(validate_item(item).passed)

    def test_gap_fill_targeting_a_word_outside_the_unit_fails(self):
        item = self._item(
            QuestionType.GAP_FILL,
            {"sentence_with_gap": "She was very ________ today.", "target_word": "gregarious"},
            "gregarious",
        )
        result = validate_item(item)
        self.assertTrue(any("not in this unit's vocabulary" in f for f in result.failures))

    def test_transformation_missing_its_key_word_fails(self):
        item = self._item(
            QuestionType.KEY_WORD_TRANSFORMATION,
            {
                "original_sentence": "She started work two years ago.",
                "keyword": "been",
                "acceptable_answers": ["She has worked here for two years."],
            },
            "She has worked here for two years.",
        )
        result = validate_item(item)
        self.assertTrue(any("omits the key word" in f for f in result.failures))

    def test_mcq_with_duplicate_options_fails(self):
        item = self._item(
            QuestionType.MULTIPLE_CHOICE,
            {"sentence": "Pick one.", "options": ["a", "b", "a", "c"], "correct_option": "A"},
            "A",
        )
        result = validate_item(item)
        self.assertTrue(any("duplicate options" in f for f in result.failures))

    def test_matching_with_a_repeated_definition_fails(self):
        item = self._item(
            QuestionType.MATCHING,
            {
                "item_set": [
                    {"left": "a", "right": "same"},
                    {"left": "b", "right": "same"},
                    {"left": "c", "right": "other"},
                ]
            },
            "1-A, 2-B, 3-C",
        )
        result = validate_item(item)
        self.assertTrue(any("same definition" in f for f in result.failures))

    def test_cue_frame_items_skip_the_parser_pos_check(self):
        item = self._item(
            QuestionType.WORD_FORMATION,
            {
                "sentence_with_gap": "Write the adjective formed from ENTERTAIN: ________",
                "root_word": "entertain",
                "correct_form": "entertaining",
                "target_pos": PartOfSpeech.ADJECTIVE,
                "cue_frame": True,
            },
            "entertaining",
        )
        result = validate_item(item)
        self.assertTrue(result.passed)
        self.assertTrue(any("cue frame" in s for s in result.skipped))


class DeterminismTests(BootstrapBaseTest):
    def test_generation_is_repeatable_for_the_same_unit(self):
        for word, definition in [
            ("charge", "to ask an amount of money for a service"),
            ("discount", "a reduction in price"),
            ("receipt", "a piece of paper proving payment"),
            ("serve", "to help customers in a shop"),
            ("promotions", "activities to advertise something"),
            ("refunds", "money given back after a purchase"),
        ]:
            entry(self.unit, word, PartOfSpeech.NOUN, definition=definition)

        first = [d.content_hash() for d in generate_for_unit(self.unit)]
        second = [d.content_hash() for d in generate_for_unit(self.unit)]
        self.assertEqual(first, second)
