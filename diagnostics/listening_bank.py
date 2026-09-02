"""Which grades and groups actually sit each listening question set.

Read from stored Paper rows, never from allocation.py. verification.py takes
the same line and for the same reason: the question a reviewer is asking is
"what did we issue", not "what would the allocator issue".

A group, not a variant, is the unit here - a group is one room at one time,
and its two variants sit the same recording, so listing both letters would
say the same thing twice.
"""

from collections import defaultdict

from diagnostics.constants import TaskType
from diagnostics.models import Paper
from diagnostics.navigation import group_for_variant

#: Task types answered in free text rather than by picking a letter.
#: The answer-key balance panel exists to expose a letter that is
#: over-represented; these have no letters, so they are counted
#: instead of tallied. See key_balance.
FREE_TEXT_TASKS = frozenset({TaskType.GAP_FILL.value})


def set_usage():
    """Map question set id -> sorted list of (grade, group) pairs.

    Every set that any paper uses appears. A set no paper uses is absent;
    callers should treat a missing key as "unallocated" rather than an
    error - see usage_title.
    """
    pairs = defaultdict(set)
    rows = Paper.objects.values_list(
        "grade", "variant", "listening_set_1_id", "listening_set_2_id"
    )
    for grade, variant, first, second in rows:
        group = group_for_variant(variant)
        for set_id in (first, second):
            if set_id is not None:
                pairs[set_id].add((grade, group))
    return {set_id: sorted(found) for set_id, found in pairs.items()}


def usage_title(pairs):
    """Render (grade, group) pairs as one human title.

    "Grade 9 groups 1, 6 · Grade 10 groups 3, 8 · Grade 11 group 5"

    Compound because no question set is exclusive to one grade: the same
    recording is issued to several grades, so a single-grade title would be
    wrong for most of the bank.
    """
    if not pairs:
        return "Not currently allocated to any paper"

    by_grade = defaultdict(list)
    for grade, group in sorted(set(pairs)):
        by_grade[grade].append(group)

    parts = []
    for grade, groups in sorted(by_grade.items()):
        label = "group" if len(groups) == 1 else "groups"
        parts.append(f"Grade {grade} {label} {', '.join(str(g) for g in groups)}")
    return " · ".join(parts)


def key_balance(questions):
    """Summarise the answer key per task type across `questions`.

    A guessable key is a real defect: set 2's mcq3 answers were once
    A=6 B=14 C=5, so answering B every time scored 56% against 33% by
    chance. Showing the distribution makes that visible at a glance
    instead of needing someone to tally 200 answers by hand.

    Task types are kept apart because they are not comparable - true_false
    has two options and the rest have three.

    Gap-fill is counted rather than tallied. Its answers are free text, so
    there is no letter to over-pick and a distribution of forty distinct
    answers occurring once each says nothing about guessability - it just
    reprints the key, which buried the three rows that do carry signal.

    Returns task type -> {"letters": {...}} or {"free_text": count}, in the
    order the task types are declared rather than the order the rows happen
    to arrive in.
    """
    counts = defaultdict(lambda: defaultdict(int))
    free_text = defaultdict(int)

    rows = questions.values_list("question_set__clip__task_type", "answer")
    for task_type, answer in rows:
        if task_type in FREE_TEXT_TASKS:
            free_text[task_type] += 1
        else:
            counts[task_type][answer] += 1

    balance = {}
    for task in TaskType:
        if task.value in counts:
            balance[task.value] = {
                "letters": dict(sorted(counts[task.value].items()))
            }
        elif task.value in free_text:
            balance[task.value] = {"free_text": free_text[task.value]}
    return balance
