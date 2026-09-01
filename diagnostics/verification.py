"""Independent re-derivation of the client's per-component reuse cap rule.

Deliberately does NOT call Paper.clean(). It recomputes the answer from what
is actually stored, so a paper written by a bulk update or a .create() that
skipped model validation is still caught. That independence is the whole
point: under the sampled-selection model, writing/speaking slots are attached
to a paper AFTER it is saved, so clean() cannot self-trigger at the moment the
last slot lands.

The group checks below are the same idea applied to the sitting rather than
the grade: a group is two variants in one room at one time, so they must
share both recordings and share nothing else.
"""

from collections import defaultdict

from diagnostics.constants import GRADES, REUSE_CAPS, VARIANTS
from diagnostics.models import Paper
from diagnostics.navigation import GROUP_NUMBERS, variants_for_group

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
        "listening_set_1__clip", "listening_set_2__clip", "reading_passage"
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


def find_group_violations():
    """Return human-readable problems with the 24 exam sittings; empty is good.

    A group is two variants in one room at one time with one recording
    playing. Four things must hold, and all four are checked from what is
    stored rather than from the allocator, so a paper written by a bulk
    update is caught the same as one built by build_papers:

      G1  both papers use the same two recordings - otherwise the room needs
          two different clips playing at once, which is the defect this whole
          change exists to fix
      G2  the two papers use different question sets - otherwise, now that
          the audio is shared, they are the same listening paper
      G3  no shared speaking prompt - side-by-side students must not be
          asked to speak on the same topic
      G4  no shared reading passage
    """
    problems = []
    papers = Paper.objects.select_related(
        "listening_set_1__clip", "listening_set_2__clip", "reading_passage"
    ).prefetch_related("speaking_prompts")

    by_slot = {(paper.grade, paper.variant): paper for paper in papers}

    for grade in GRADES:
        for group in GROUP_NUMBERS:
            variants = variants_for_group(group)
            present = [by_slot[(grade, v)] for v in variants if (grade, v) in by_slot]
            label = f"Grade {grade} group {group} ({'/'.join(variants)})"

            if not present:
                # Sitting not built yet at all - nothing to verify.
                continue

            if len(present) != len(variants):
                problems.append(
                    f"{label}: only {len(present)} of {len(variants)} papers exist; "
                    f"a sitting with a missing paper cannot be administered."
                )
                continue

            first, second = present

            recordings = [
                (p.listening_set_1.clip_id, p.listening_set_2.clip_id) for p in present
            ]
            if recordings[0] != recordings[1]:
                problems.append(
                    f"{label}: the two papers need different recordings "
                    f"(clips {first.listening_set_1.clip.number}/"
                    f"{first.listening_set_2.clip.number} against "
                    f"{second.listening_set_1.clip.number}/"
                    f"{second.listening_set_2.clip.number}); one room cannot play "
                    f"two audio files at once."
                )

            sets_first = {first.listening_set_1_id, first.listening_set_2_id}
            sets_second = {second.listening_set_1_id, second.listening_set_2_id}
            if sets_first & sets_second:
                problems.append(
                    f"{label}: the two papers share a listening question set, "
                    f"so at least part of the listening paper is identical for "
                    f"the two students in the room."
                )

            shared_prompts = (
                set(first.speaking_prompts.values_list("pk", flat=True))
                & set(second.speaking_prompts.values_list("pk", flat=True))
            )
            if shared_prompts:
                problems.append(
                    f"{label}: {len(shared_prompts)} speaking prompt(s) appear on "
                    f"both papers in the room."
                )

            if first.reading_passage_id == second.reading_passage_id:
                problems.append(
                    f"{label}: both papers use reading passage "
                    f"{first.reading_passage.label}."
                )

    return problems
