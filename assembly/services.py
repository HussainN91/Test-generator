"""Test assembly: sampling variants out of the item bank (spec 3.4).

No LLM, no generation — this is SQL plus a shuffle, which is why building a
test is instant and free.

Two rules shape the algorithm:

1. **Non-overlap within a batch.** The variants a teacher asks for together
   must not share items, or "Test A" and "Test B" stop being different papers.
   Across batches, overlap is fine and expected — a globally-unique constraint
   would drain a shared multi-teacher bank within a term.

2. **Weighted towards production types.** Gap-fill, word formation, key word
   transformation and error correction test recall; matching and multiple
   choice test recognition. The default mix reflects that, but degrades
   gracefully: if the bank has no gap-fill items for the selected units yet,
   the shortfall is redistributed and reported rather than silently ignored.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Count

from assembly.models import TestBatch, TestQuestion, TestVariant
from bank.models import Item, QuestionType, ReviewStatus

#: Relative weights for the default question mix (spec 3.5).
DEFAULT_TYPE_WEIGHTS = {
    QuestionType.GAP_FILL: 3,
    QuestionType.WORD_FORMATION: 3,
    QuestionType.KEY_WORD_TRANSFORMATION: 2,
    QuestionType.ERROR_CORRECTION: 2,
    QuestionType.MATCHING: 1,
    QuestionType.MULTIPLE_CHOICE: 1,
    QuestionType.ODD_ONE_OUT: 1,
}

#: Variant labels, in order: Test A, Test B, ...
VARIANT_LABELS = [chr(code) for code in range(ord("A"), ord("Z") + 1)]

MAX_VARIANTS = len(VARIANT_LABELS)


class AssemblyError(Exception):
    """Raised when a request cannot be satisfied at all."""


@dataclass
class Shortfall:
    """One question type that could not be filled to the requested count."""

    question_type: str
    requested: int
    available: int

    def __str__(self) -> str:
        label = QuestionType(self.question_type).label
        return f"{label}: asked for {self.requested}, bank has {self.available}"


@dataclass
class AssemblyPlan:
    """The outcome of a sampling run, before or after it is saved."""

    variants: list[list[Item]] = field(default_factory=list)
    shortfalls: list[Shortfall] = field(default_factory=list)
    requested_per_variant: int = 0
    #: Types the default mix wanted but the selected units hold none of. These
    #: are dropped and their share re-apportioned, not reported as failures —
    #: the default mix is our heuristic, not something the teacher asked for.
    unavailable_types: list[str] = field(default_factory=list)

    @property
    def actual_per_variant(self) -> int:
        return min((len(v) for v in self.variants), default=0)

    @property
    def is_complete(self) -> bool:
        return not self.shortfalls and self.actual_per_variant == self.requested_per_variant


def resolve_type_mix(question_count: int, weights: dict[str, int] | None = None) -> dict[str, int]:
    """Turn relative weights into whole-number question counts summing to `question_count`.

    Largest-remainder apportionment, so a 10-question test with the default
    weights gives 3/3/2/2/1/1 rather than rounding everything down to 9.
    """
    weights = {k: v for k, v in (weights or DEFAULT_TYPE_WEIGHTS).items() if v > 0}
    if not weights or question_count <= 0:
        return {}

    total_weight = sum(weights.values())
    exact = {qt: question_count * w / total_weight for qt, w in weights.items()}
    counts = {qt: int(value) for qt, value in exact.items()}

    remaining = question_count - sum(counts.values())
    by_remainder = sorted(exact, key=lambda qt: (exact[qt] - counts[qt], weights[qt]), reverse=True)
    for qt in by_remainder[:remaining]:
        counts[qt] += 1
    return {qt: c for qt, c in counts.items() if c > 0}


def eligible_items(unit_ids: list[int], question_type: str | None = None):
    """Approved items for the selected units — the only pool assembly ever reads."""
    queryset = Item.objects.filter(
        unit_id__in=unit_ids, review_status=ReviewStatus.APPROVED
    ).select_related("unit", "unit__grade", "grammar_point")
    if question_type:
        queryset = queryset.filter(question_type=question_type)
    return queryset


def bank_summary(unit_ids: list[int]) -> dict[str, int]:
    """Approved item counts per question type, for the "can this be built?" warning."""
    summary = {qt.value: 0 for qt in QuestionType}
    rows = (
        eligible_items(unit_ids).values("question_type").order_by().annotate(count=Count("id"))
    )
    for row in rows:
        summary[row["question_type"]] = row["count"]
    return summary


def build_plan(
    unit_ids: list[int],
    question_count: int,
    variant_count: int,
    type_mix: dict[str, int] | None = None,
    seed: int | None = None,
) -> AssemblyPlan:
    """Sample `variant_count` non-overlapping variants of `question_count` items each."""
    if not unit_ids:
        raise AssemblyError("Select at least one unit.")
    if question_count < 1:
        raise AssemblyError("A test needs at least one question.")
    if not 1 <= variant_count <= MAX_VARIANTS:
        raise AssemblyError(f"Choose between 1 and {MAX_VARIANTS} variants.")

    rng = random.Random(seed)
    if type_mix:
        # An explicit mix is the teacher's own request: honour it as given and
        # report anything the bank cannot supply as a shortfall.
        mix, unavailable = type_mix, []
    else:
        mix, unavailable = _fit_default_mix(unit_ids, question_count, variant_count)

    # Draw the whole batch's worth of each type up front, then deal them out —
    # this is what guarantees variants never share an item.
    pools: dict[str, list[Item]] = {}
    shortfalls: list[Shortfall] = []
    for question_type, per_variant in mix.items():
        needed = per_variant * variant_count
        pool = list(eligible_items(unit_ids, question_type))
        rng.shuffle(pool)
        if len(pool) < needed:
            shortfalls.append(
                Shortfall(
                    question_type=question_type,
                    requested=per_variant,
                    available=len(pool) // variant_count,
                )
            )
        pools[question_type] = pool[:needed]

    variants: list[list[Item]] = [[] for _ in range(variant_count)]
    for question_type, per_variant in mix.items():
        pool = pools[question_type]
        # Deal round-robin so a short pool thins every variant evenly rather
        # than filling Test A and starving Test D.
        for index, item in enumerate(pool):
            variants[index % variant_count].append(item)

    deficit = question_count - min((len(v) for v in variants), default=0)
    if deficit > 0:
        _backfill(variants, unit_ids, question_count, rng)

    for variant in variants:
        rng.shuffle(variant)

    return AssemblyPlan(
        variants=variants,
        shortfalls=shortfalls,
        requested_per_variant=question_count,
        unavailable_types=unavailable,
    )


def _fit_default_mix(
    unit_ids: list[int], question_count: int, variant_count: int
) -> tuple[dict[str, int], list[str]]:
    """Apportion the default mix over what the selected units can actually supply.

    The default weights assume a fully-stocked bank. Against a real one — filled
    type by type as the offline pipeline runs — a straight apportionment sends
    most of every test to types holding no items at all, and the paper arrives
    short and buried under warnings about a mix nobody asked for. So: drop the
    types with nothing in them, cap the rest at what they can supply without
    variants having to share an item, and re-apportion the freed slots over
    whatever still has headroom. This is the "degrades gracefully" half of rule 2.
    """
    stock = bank_summary(unit_ids)
    # How many questions of a type one variant can take before the batch would
    # have to reuse an item across variants, which rule 1 forbids.
    capacity = {qt: stock.get(qt.value, 0) // variant_count for qt in DEFAULT_TYPE_WEIGHTS}
    weights = {qt: w for qt, w in DEFAULT_TYPE_WEIGHTS.items() if capacity[qt] > 0}
    if not weights:
        # Nothing usable in the selection: keep the full default mix so the
        # shortfalls are reported honestly rather than silently vanishing.
        return resolve_type_mix(question_count), []

    unavailable = [qt.label for qt in DEFAULT_TYPE_WEIGHTS if capacity[qt] <= 0]

    mix: dict = {}
    remaining = question_count
    while remaining > 0 and weights:
        share = resolve_type_mix(remaining, weights)
        maxed = [qt for qt, count in share.items() if count >= capacity[qt]]
        if not maxed:
            mix.update(share)
            break
        # Pin every type that hit its ceiling, then go round again with the
        # leftover questions spread across the types that still have room.
        for qt in maxed:
            mix[qt] = capacity[qt]
            remaining -= capacity[qt]
            del weights[qt]
    return mix, unavailable


def _backfill(
    variants: list[list[Item]], unit_ids: list[int], question_count: int, rng: random.Random
) -> None:
    """Top short variants up from any remaining approved item, still without overlap."""
    used = {item.pk for variant in variants for item in variant}
    spare = [item for item in eligible_items(unit_ids) if item.pk not in used]
    rng.shuffle(spare)

    # Always top up the shortest variant next. Filling one variant at a time
    # would hand every spare item to Test A and leave Test B a one-question
    # paper — and `actual_per_variant` is a minimum, so the whole batch would
    # then report itself as one question long.
    while spare:
        shortest = min(variants, key=len)
        if len(shortest) >= question_count:
            break
        shortest.append(spare.pop())


@transaction.atomic
def save_plan(plan: AssemblyPlan, batch: TestBatch) -> list[TestVariant]:
    """Persist a plan so the batch stays traceable after export."""
    saved: list[TestVariant] = []
    for index, items in enumerate(plan.variants):
        variant = TestVariant.objects.create(batch=batch, label=VARIANT_LABELS[index])
        TestQuestion.objects.bulk_create(
            [
                TestQuestion(variant=variant, item=item, position=position)
                for position, item in enumerate(items, start=1)
            ]
        )
        saved.append(variant)
    return saved
