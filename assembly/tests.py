"""Assembly tests: the guarantees teachers depend on when they print a batch."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from assembly.models import TestBatch
from assembly.services import (
    AssemblyError,
    build_plan,
    resolve_type_mix,
    save_plan,
)
from bank.models import Item, QuestionType, ReviewStatus
from content.models import Grade, Unit


def make_item(unit, question_type, index, status=ReviewStatus.APPROVED):
    return Item.objects.create(
        unit=unit,
        question_type=question_type,
        payload={"sentence": f"s{index}", "options": ["a", "b"], "correct_option": "A",
                 "sentence_with_gap": "g", "target_word": "w", "root_word": "r",
                 "correct_form": "c", "target_pos": "noun", "original_sentence": "o",
                 "keyword": "k", "acceptable_answers": [], "sentence_with_error": "e",
                 "error_type": "t", "corrected_word_phrase": "p", "item_set": []},
        model_answer=f"answer-{question_type}-{index}",
        review_status=status,
        content_hash=f"{question_type}-{unit.pk}-{index}",
    )


class TypeMixTests(TestCase):
    def test_counts_sum_to_requested_total(self):
        for total in range(1, 41):
            with self.subTest(total=total):
                self.assertEqual(sum(resolve_type_mix(total).values()), total)

    def test_default_mix_favours_production_types(self):
        mix = resolve_type_mix(12)
        recognition = (
            mix.get(QuestionType.MATCHING, 0)
            + mix.get(QuestionType.MULTIPLE_CHOICE, 0)
            + mix.get(QuestionType.ODD_ONE_OUT, 0)
        )
        production = sum(mix.values()) - recognition
        self.assertGreater(production, recognition)

    def test_custom_weights_respected(self):
        mix = resolve_type_mix(10, {QuestionType.GAP_FILL: 1})
        self.assertEqual(mix, {QuestionType.GAP_FILL: 10})

    def test_zero_questions_gives_empty_mix(self):
        self.assertEqual(resolve_type_mix(0), {})


class SamplingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.grade = Grade.objects.create(number=9)
        cls.unit = Unit.objects.create(grade=cls.grade, number=1, title="Unit 1")
        for index in range(40):
            make_item(cls.unit, QuestionType.MULTIPLE_CHOICE, index)
        for index in range(40):
            make_item(cls.unit, QuestionType.GAP_FILL, index)

    def test_variants_within_a_batch_never_share_items(self):
        plan = build_plan([self.unit.pk], question_count=8, variant_count=4, seed=1)
        seen = set()
        for variant in plan.variants:
            ids = {item.pk for item in variant}
            self.assertFalse(seen & ids, "variants overlapped within one batch")
            seen |= ids

    def test_each_variant_has_the_requested_number_of_questions(self):
        plan = build_plan([self.unit.pk], question_count=8, variant_count=4, seed=1)
        for variant in plan.variants:
            self.assertEqual(len(variant), 8)

    def test_unapproved_items_are_never_sampled(self):
        flagged = make_item(self.unit, QuestionType.GAP_FILL, 999, status=ReviewStatus.FLAGGED)
        plan = build_plan([self.unit.pk], question_count=10, variant_count=2, seed=2)
        sampled = {item.pk for variant in plan.variants for item in variant}
        self.assertNotIn(flagged.pk, sampled)

    def test_shortfall_is_reported_not_hidden(self):
        # 40 gap-fill items cannot supply 30 per variant across 4 variants.
        plan = build_plan(
            [self.unit.pk],
            question_count=30,
            variant_count=4,
            type_mix={QuestionType.GAP_FILL: 30},
            seed=3,
        )
        self.assertTrue(plan.shortfalls)
        self.assertFalse(plan.is_complete)

    def test_seed_makes_sampling_reproducible(self):
        first = build_plan([self.unit.pk], question_count=6, variant_count=2, seed=42)
        second = build_plan([self.unit.pk], question_count=6, variant_count=2, seed=42)
        self.assertEqual(
            [[i.pk for i in v] for v in first.variants],
            [[i.pk for i in v] for v in second.variants],
        )

    def test_no_units_selected_is_an_error(self):
        with self.assertRaises(AssemblyError):
            build_plan([], question_count=5, variant_count=1)

    def test_variant_count_is_bounded(self):
        with self.assertRaises(AssemblyError):
            build_plan([self.unit.pk], question_count=5, variant_count=99)

    def test_a_thin_bank_thins_every_variant_evenly(self):
        """A short pool must not fill Test A and leave Test B a one-question paper."""
        grade = Grade.objects.create(number=11)
        unit = Unit.objects.create(grade=grade, number=1, title="Thin unit")
        for index in range(6):
            make_item(unit, QuestionType.MULTIPLE_CHOICE, index)

        plan = build_plan([unit.pk], question_count=10, variant_count=2, seed=7)

        self.assertEqual([len(variant) for variant in plan.variants], [3, 3])
        self.assertEqual(plan.actual_per_variant, 3)

    def test_default_mix_never_asks_for_more_of_a_type_than_the_bank_holds(self):
        """A type with four items must not be handed a twelve-question share."""
        grade = Grade.objects.create(number=11)
        unit = Unit.objects.create(grade=grade, number=1, title="Lopsided unit")
        for index in range(200):
            make_item(unit, QuestionType.MULTIPLE_CHOICE, index)
        for index in range(4):
            make_item(unit, QuestionType.WORD_FORMATION, index)

        plan = build_plan([unit.pk], question_count=20, variant_count=4, seed=7)

        self.assertEqual([len(variant) for variant in plan.variants], [20] * 4)
        self.assertEqual(plan.shortfalls, [])

    def test_default_mix_skips_types_the_selection_cannot_supply(self):
        """The bank is stocked type by type; a test still has to come out full."""
        grade = Grade.objects.create(number=10)
        unit = Unit.objects.create(grade=grade, number=1, title="Multiple choice only")
        for index in range(60):
            make_item(unit, QuestionType.MULTIPLE_CHOICE, index)

        plan = build_plan([unit.pk], question_count=10, variant_count=2, seed=7)

        self.assertEqual([len(variant) for variant in plan.variants], [10, 10])
        self.assertEqual(plan.shortfalls, [])
        self.assertIn(QuestionType.GAP_FILL.label, plan.unavailable_types)

    def test_an_explicit_mix_is_honoured_rather_than_quietly_rewritten(self):
        plan = build_plan(
            [self.unit.pk],
            question_count=10,
            variant_count=2,
            type_mix={QuestionType.WORD_FORMATION: 10},
            seed=7,
        )
        self.assertEqual(plan.unavailable_types, [])
        self.assertTrue(plan.shortfalls)

    def test_saved_plan_keeps_question_order(self):
        plan = build_plan([self.unit.pk], question_count=5, variant_count=2, seed=7)
        batch = TestBatch.objects.create(grade=self.grade, question_count=5, variant_count=2)
        batch.units.set([self.unit])
        variants = save_plan(plan, batch)

        self.assertEqual([v.label for v in variants], ["A", "B"])
        positions = list(variants[0].questions.values_list("position", flat=True))
        self.assertEqual(positions, [1, 2, 3, 4, 5])


class BuilderViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.grade = Grade.objects.create(number=9)
        cls.unit = Unit.objects.create(grade=cls.grade, number=1, title="Unit 1")
        for index in range(30):
            make_item(cls.unit, QuestionType.MULTIPLE_CHOICE, index)
        cls.user = User.objects.create_user("teacher", password="pw-for-tests-8891")

    def test_builder_requires_login(self):
        response = self.client.get(reverse("builder"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_builder_renders_for_logged_in_teacher(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("builder"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unit 1")

    def test_generating_a_batch_creates_variants_and_records_the_teacher(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("builder"),
            {
                "grade": self.grade.pk,
                "units": [self.unit.pk],
                "question_count": 5,
                "variant_count": 2,
                "generate": "1",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        batch = TestBatch.objects.get()
        self.assertEqual(batch.created_by, self.user)
        self.assertEqual(batch.variants.count(), 2)

    def test_empty_unit_selection_is_rejected_with_a_message(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("builder"),
            {"grade": self.grade.pk, "question_count": 5, "variant_count": 1, "generate": "1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(TestBatch.objects.count(), 0)
        self.assertContains(response, "Select at least one unit.")

    def test_a_rejected_submission_keeps_the_units_the_teacher_shaded(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("builder"),
            {
                "grade": self.grade.pk,
                "units": [self.unit.pk],
                "question_count": 999,
                "variant_count": 1,
                "generate": "1",
            },
        )
        self.assertEqual(TestBatch.objects.count(), 0)
        rendered = " ".join(response.content.decode().split())
        self.assertIn(f'name="units" value="{self.unit.pk}" checked', rendered)

    def test_switching_grade_keeps_the_numbers_already_typed(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("builder"),
            {"grade": self.grade.pk, "question_count": 25, "variant_count": 4},
        )
        self.assertContains(response, 'name="question_count" value="25"')
        self.assertContains(response, 'name="variant_count" value="4"')
