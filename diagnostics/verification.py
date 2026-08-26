"""Independent re-derivation of the client's per-component reuse cap rule.

Deliberately does NOT call Paper.clean(). It recomputes the answer from what
is actually stored, so a paper written by a bulk update or a .create() that
skipped model validation is still caught. That independence is the whole
point: under the sampled-selection model, writing/speaking slots are attached
to a paper AFTER it is saved, so clean() cannot self-trigger at the moment the
last slot lands.
"""

from collections import defaultdict

from diagnostics.constants import GRADES, REUSE_CAPS, VARIANTS
from diagnostics.models import Paper

EXPECTED_PAPER_COUNT = len(GRADES) * len(VARIANTS)


def find_reuse_violations():
    """Return human-readable problems; empty means the bank is legal.

    Deliberately does NOT call Paper.clean(). Writing and speaking slots are
    attached AFTER a paper is saved, so clean() cannot self-trigger at the
    moment the last slot lands. This recomputes the answer from what is
    actually stored, catching papers written by bulk updates or .create().
    """
    problems = []
    papers = Paper.objects.select_related(
        "listening_clip_1", "listening_clip_2", "reading_passage"
    ).prefetch_related("writing_questions", "speaking_prompts")

    by_grade = defaultdict(list)
    for paper in papers:
        by_grade[paper.grade].append(paper)

    for grade in GRADES:
        counts = defaultdict(list)
        for paper in by_grade.get(grade, []):
            for label, pk in paper.shared_components():
                counts[(label, pk)].append(paper.variant)

        for (label, _pk), variants in sorted(counts.items()):
            cap = REUSE_CAPS[label]
            if len(variants) > cap:
                problems.append(
                    f"Grade {grade}: {label} used by {len(variants)} variants "
                    f"({', '.join(sorted(variants))}), cap is {cap}."
                )

        combos = [
            tuple(sorted(paper.shared_components()))
            for paper in by_grade.get(grade, [])
        ]
        if len(combos) != len(set(combos)):
            problems.append(
                f"Grade {grade}: two variants have an identical combination "
                f"of components."
            )
    return problems


def find_completeness_problems():
    """Return problems about missing papers or under-filled sections."""
    problems = []
    count = Paper.objects.count()
    if count != EXPECTED_PAPER_COUNT:
        problems.append(f"Expected {EXPECTED_PAPER_COUNT} papers, found {count}.")

    for paper in Paper.objects.prefetch_related("writing_questions", "speaking_prompts"):
        writing = paper.writing_questions.count()
        speaking = paper.speaking_prompts.count()
        if writing != 10:
            problems.append(f"{paper}: expected 10 writing questions, found {writing}.")
        if speaking != 5:
            problems.append(f"{paper}: expected 5 speaking prompts, found {speaking}.")
    return problems
