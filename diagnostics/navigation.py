"""Class packs: which four variants belong to which class in a grade.

The school runs four classes in every grade and hands each class its own set
of four papers, which is why a grade holds sixteen variants (Design Revision
2, section 2.1) rather than the original four. That grouping was real but
invisible to the code: the register printed all sixteen variants of a grade
in one table and left the teacher to work out which four were meant for the
class in front of them.

The mapping is positional and sequential -- class 1 takes the first four
letters of VARIANTS, class 2 the next four, and so on -- because that is the
order the packs were built and handed out in. Nothing is stored: a paper's
class is a fact about where its variant sits in VARIANTS, so deriving it
keeps the two from drifting apart the way a duplicated column would. Widen
VARIANTS again and the packs re-divide themselves, provided the count still
divides by four.
"""

from __future__ import annotations

from diagnostics.constants import VARIANTS
from step.models import TeachingClass

#: Classes per grade. Fixed by the school's timetable, not by the bank.
CLASSES_PER_GRADE = 4

if len(VARIANTS) % CLASSES_PER_GRADE:
    raise ValueError(
        f"{len(VARIANTS)} variants do not divide evenly into "
        f"{CLASSES_PER_GRADE} classes; every class must get the same "
        f"number of papers or some variants become unreachable."
    )

#: How many papers one class gets. Derived, so the two constants cannot disagree.
VARIANTS_PER_CLASS = len(VARIANTS) // CLASSES_PER_GRADE

#: 1-based, because that is how teachers name their classes.
CLASS_NUMBERS = tuple(range(1, CLASSES_PER_GRADE + 1))


def variants_for_class(number: int) -> tuple[str, ...]:
    """The variant letters belonging to class `number` (1-based).

    Raises ValueError for a number outside CLASS_NUMBERS rather than
    returning an empty tuple: a request for class 7 is a bad URL, not a
    class that happens to have no papers, and the caller should be able to
    tell those apart.
    """
    if number not in CLASS_NUMBERS:
        raise ValueError(f"Class {number} does not exist; grades run 1-{CLASSES_PER_GRADE}.")
    start = (number - 1) * VARIANTS_PER_CLASS
    return VARIANTS[start:start + VARIANTS_PER_CLASS]


def class_for_variant(variant: str) -> int:
    """Which class a variant letter belongs to (1-based)."""
    try:
        position = VARIANTS.index(variant)
    except ValueError:
        raise ValueError(f"{variant!r} is not one of the {len(VARIANTS)} variants.") from None
    return position // VARIANTS_PER_CLASS + 1


def variant_span(number: int) -> str:
    """A short label for the pack's range, e.g. "A-D". Used on the picker
    screens so a teacher can recognise the pack by the paper names they
    already have on paper, not only by the class number."""
    letters = variants_for_class(number)
    return f"{letters[0]}-{letters[-1]}"


#: Groups per class. Each class sits the diagnostic in two sittings, and a
#: sitting is one room at one time playing one recording - which is why the
#: group, not the class and not the variant, is the unit the audio is
#: allocated to. Fixed by the school's timetable, like CLASSES_PER_GRADE.
GROUPS_PER_CLASS = 2

if VARIANTS_PER_CLASS % GROUPS_PER_CLASS:
    raise ValueError(
        f"{VARIANTS_PER_CLASS} variants per class do not divide evenly into "
        f"{GROUPS_PER_CLASS} groups; a group that straddles two classes would "
        f"put papers from different class packs in the same room."
    )

#: Derived, so the constants cannot disagree.
VARIANTS_PER_GROUP = VARIANTS_PER_CLASS // GROUPS_PER_CLASS
GROUPS_PER_GRADE = CLASSES_PER_GRADE * GROUPS_PER_CLASS

#: 1-based and numbered straight through the grade (1-8), not restarted per
#: class. A group number is the natural key for "which sitting", and the
#: allocator indexes clip pools by it, so a globally unique number keeps that
#: arithmetic to one modulo instead of a class/group pair.
GROUP_NUMBERS = tuple(range(1, GROUPS_PER_GRADE + 1))


def variants_for_group(number: int) -> tuple[str, ...]:
    """The variant letters sitting together in group `number` (1-based).

    Raises ValueError outside GROUP_NUMBERS rather than returning an empty
    tuple, for the same reason variants_for_class does: a request for group 9
    is a bad input, not a sitting that happens to have no papers.
    """
    if number not in GROUP_NUMBERS:
        raise ValueError(
            f"Group {number} does not exist; grades run 1-{GROUPS_PER_GRADE}."
        )
    start = (number - 1) * VARIANTS_PER_GROUP
    return VARIANTS[start:start + VARIANTS_PER_GROUP]


def group_for_variant(variant: str) -> int:
    """Which group a variant letter sits in (1-based)."""
    try:
        position = VARIANTS.index(variant)
    except ValueError:
        raise ValueError(f"{variant!r} is not one of the {len(VARIANTS)} variants.") from None
    return position // VARIANTS_PER_GROUP + 1


def groups_for_class(number: int) -> tuple[int, ...]:
    """The group numbers belonging to class `number` (1-based).

    Derived from the class's own variants rather than from arithmetic on the
    class number, so the nesting stays correct if either split changes.
    """
    letters = variants_for_class(number)
    seen = []
    for letter in letters:
        group = group_for_variant(letter)
        if group not in seen:
            seen.append(group)
    return tuple(seen)


def group_span(number: int) -> str:
    """A short label for the sitting, e.g. "A-B", to match variant_span."""
    letters = variants_for_group(number)
    return f"{letters[0]}-{letters[-1]}"


def partner_variant(variant: str) -> str:
    """The other variant sitting in the same room at the same time.

    Only meaningful while VARIANTS_PER_GROUP is 2; raises if a future widening
    breaks that assumption rather than silently returning one of several
    partners. Callers that must handle any group size should use
    variants_for_group(group_for_variant(v)) instead.
    """
    if VARIANTS_PER_GROUP != 2:
        raise ValueError(
            f"partner_variant assumes 2 variants per group, not {VARIANTS_PER_GROUP}."
        )
    first, second = variants_for_group(group_for_variant(variant))
    return second if variant == first else first


def display_name_for(grade: int, number: int) -> str:
    """The teacher's own name for this class pack, if one has been set.

    STEP owns the name (TeachingClass.display_name); diagnostics only reads
    it, never writes it (classes/gradebook spec, "Diagnostics rename"). Falls
    back to the positional "Class N" this module always showed, so an
    unclaimed pack still prints something sensible.
    """
    teaching_class = TeachingClass.objects.filter(grade=grade, slot=number).first()
    if teaching_class:
        return teaching_class.display_name
    return f"Class {number}"
