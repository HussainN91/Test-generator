"""Random-with-cap sampling for writing/speaking (Design Revision 2).

Mirrors the sibling assembly app's TestVariant/TestQuestion sampling shape,
reimplemented locally (diagnostics imports nothing from assembly).

At 4 variants/grade a paper's grade siblings could share nothing at all -
that headroom was checked analytically and comfortably held. At 16
variants/grade it no longer holds (10 speaking prompts per task against 16
slots, 50 writing questions per subtype against 48 needed at most): the
sampler now excludes an id only once it has hit its REUSE_CAPS limit within
the paper's grade, rather than excluding every id a sibling has ever used.
Writing's cap of 1 still yields genuine zero reuse, because its pool is large
enough to support it; speaking's cap of 2 makes reuse mandatory once every
prompt has been used once. Cross-grade reuse remains unrestricted either way.

Speaking carries one extra rule the cap cannot express: the other paper in
the same room is excluded outright, at any usage count. Ten of the
twenty-four groups were sharing a prompt under the cap alone.
"""

import random
from collections import Counter

from django.db import transaction

from diagnostics.constants import REUSE_CAPS, SPEAKING_TASK_ORDER, WRITING_SUBTYPE_COUNTS
from diagnostics.models import (
    Paper, PaperSpeakingPrompt, PaperWritingQuestion, SpeakingPrompt, WritingQuestion,
)
from diagnostics.navigation import partner_variant


class SamplingError(Exception):
    """A paper's grade cannot be satisfied from the remaining pool."""


def _at_cap_in_grade(model, paper, field_name, cap):
    """Ids that have already hit their reuse cap within this paper's grade.

    Replaces the old "every id a sibling used" exclusion. At 16 variants the
    bank cannot supply unique content for every paper (10 speaking prompts
    per task against 16 slots), so components repeat up to REUSE_CAPS
    instead of being banned outright - see Design Revision 2 section 2.
    """
    counts = Counter(
        model.objects.filter(paper__grade=paper.grade)
        .exclude(paper=paper)
        .values_list(f"{field_name}_id", flat=True)
    )
    return {item_id for item_id, used in counts.items() if used >= cap}


def used_by_group_partner(paper):
    """Speaking prompt ids already taken by the other paper in this room.

    A hard exclusion, not a cap: two students sitting side by side must never
    get the same speaking prompt, whatever the grade-wide budget allows. The
    cap alone was not enough - REUSE_CAPS is scoped per grade, so a prompt
    used once elsewhere in the grade was still under its cap of 2 and landed
    on both papers in a room in 10 of the 24 groups.

    Returns an empty set when the partner paper does not exist yet (the first
    paper in a room to be sampled has nothing to avoid) - so build order does
    not change the rule, only which of the pair moves.
    """
    partner = Paper.objects.filter(
        grade=paper.grade, variant=partner_variant(paper.variant)
    ).first()
    if partner is None:
        return set()
    return set(
        PaperSpeakingPrompt.objects.filter(paper=partner)
        .values_list("prompt_id", flat=True)
    )


@transaction.atomic
def sample_writing_questions(paper):
    """Assign 10 writing questions to `paper`: 3 grammar, 2 vocabulary,
    3 jumbled, 2 fill_blank, none at or above the reuse cap within the same
    grade."""
    used_ids = _at_cap_in_grade(
        PaperWritingQuestion, paper, "question", REUSE_CAPS["writing_question"]
    )

    PaperWritingQuestion.objects.filter(paper=paper).delete()
    position = 0
    for subtype, count in WRITING_SUBTYPE_COUNTS.items():
        pool = list(
            WritingQuestion.objects.filter(subtype=subtype)
            .exclude(pk__in=used_ids)
            .values_list("pk", flat=True)
        )
        if len(pool) < count:
            raise SamplingError(
                f"Grade {paper.grade}: need {count} '{subtype}' writing "
                f"questions, only {len(pool)} available below the reuse cap "
                f"of {REUSE_CAPS['writing_question']}."
            )
        for question_id in random.sample(pool, count):
            position += 1
            PaperWritingQuestion.objects.create(
                paper=paper, question_id=question_id, position=position,
            )


@transaction.atomic
def sample_speaking_prompts(paper):
    """Assign 5 speaking prompts to `paper`, one per fixed task, in task
    order: none at or above the reuse cap within the same grade, and none
    already sitting on the other paper in the same room."""
    used_ids = _at_cap_in_grade(
        PaperSpeakingPrompt, paper, "prompt", REUSE_CAPS["speaking_prompt"]
    ) | used_by_group_partner(paper)

    PaperSpeakingPrompt.objects.filter(paper=paper).delete()
    for position, task in enumerate(SPEAKING_TASK_ORDER, start=1):
        pool = list(
            SpeakingPrompt.objects.filter(task=task)
            .exclude(pk__in=used_ids)
            .values_list("pk", flat=True)
        )
        if not pool:
            raise SamplingError(
                f"Grade {paper.grade} variant {paper.variant}: no '{task}' "
                f"speaking prompts available below the reuse cap of "
                f"{REUSE_CAPS['speaking_prompt']} that are not already on the "
                f"group partner's paper."
            )
        PaperSpeakingPrompt.objects.create(
            paper=paper, prompt_id=random.choice(pool), position=position,
        )
