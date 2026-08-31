"""Which fixed content each of the 48 papers gets - deterministically.

Replaces the hand-written 12-entry PAPER_ALLOCATION table, which does not
scale to 48 rows without becoming unmaintainable and subtly wrong.

Two properties matter more than elegance here:

  Determinism. build_papers rewrites a paper's listening and reading fields
  on every run via update_or_create. A random allocator would reissue
  different content under the same paper name, so "G9-A" would mean two
  different tests to two teachers. There is no RNG in this module.

  Cap compliance. The bank cannot give 16 variants per grade unique content
  (20 clips against 32 slots), so components repeat up to REUSE_CAPS. The
  round-robin below distributes that reuse as evenly as the pool allows
  rather than exhausting one clip before touching the next.

  Group coherence. A group is two variants sitting in one room at one time
  with one recording playing, so the clip pair is drawn once per group and
  both its variants inherit it. Everything else - the question set number,
  the reading passage, and the sampled writing and speaking - stays
  per-variant, because those are what make the two papers in the room
  different from each other.
"""

from dataclasses import dataclass

from diagnostics.constants import (
    GRADES, PICTURE_CLIPS, ROTATING_CLIPS_BY_TYPE, VARIANTS,
)
from diagnostics.navigation import (
    GROUPS_PER_GRADE, GROUP_NUMBERS, group_for_variant, variants_for_group,
)

#: Rotating clips flattened into one list that alternates task type, so
#: consecutive variants get different types and stepping through the list
#: spreads the three types evenly by construction rather than by luck.
_ROTATION = []
_by_type = [list(clips) for clips in ROTATING_CLIPS_BY_TYPE.values()]
for _index in range(max(len(clips) for clips in _by_type)):
    for _clips in _by_type:
        if _index < len(_clips):
            _ROTATION.append(_clips[_index])


def _passages():
    """Reading passage labels R01..R15, in canonical order."""
    return [f"R{number:02d}" for number in range(1, 16)]


@dataclass(frozen=True)
class Allocation:
    """What one paper gets. Named fields rather than a tuple because the
    third element used to be the passage and is now the set number; a
    positional unpack would have kept working and silently swapped them."""

    picture_clip: int
    rotating_clip: int
    set_number: int
    passage: str


def allocate_group(grade, group):
    """Return (picture_clip_number, rotating_clip_number) for one sitting.

    Pure: same arguments, same result, no database and no randomness.

    Both clips are indexed by the group number rather than the variant, which
    is the whole fix - sixteen variants used to draw sixteen independent clip
    pairs, so every one of the 24 rooms needed two recordings playing at once.
    Eight groups per grade need eight pairs, not sixteen.

    The grade offset staggers each grade's starting point so grades do not all
    open on the same clip; three identical-looking grade 9/10/11 group 1s
    would look like a bug to a teacher holding two of them.
    """
    if group not in GROUP_NUMBERS:
        raise ValueError(
            f"Group {group} does not exist; grades run 1-{GROUPS_PER_GRADE}."
        )

    offset = (grade - min(GRADES)) * GROUPS_PER_GRADE
    index = group - 1 + offset

    # 15 rotating clips against 8 groups: consecutive indices never repeat
    # within a grade, which is what keeps a rotating clip inside one group.
    rotating = _ROTATION[index % len(_ROTATION)]
    # 5 picture clips against 8 groups: three clips take two groups each.
    # Unavoidable - see the plan's section 0.5 on the picture residual.
    picture = PICTURE_CLIPS[index % len(PICTURE_CLIPS)]
    return picture, rotating


def allocate(grade, variant):
    """Return the Allocation for one paper.

    Pure: same arguments, same result, no database and no randomness. This
    matters more than elegance here, because build_papers rewrites a paper's
    listening and reading fields on every run via update_or_create; a random
    allocator would reissue different content under the same paper name, so
    "G9-A" would mean two different tests to two teachers.
    """
    try:
        index = VARIANTS.index(variant)
    except ValueError:
        raise ValueError(
            f"Unknown variant {variant!r}; expected one of {''.join(VARIANTS)}."
        ) from None

    group = group_for_variant(variant)
    picture, rotating = allocate_group(grade, group)

    # Which of the recording's two question papers this variant answers. The
    # first variant in the room gets set 1, the second gets set 2 - this is
    # the only thing that stops the two papers in a room being identical now
    # that they share both recordings.
    set_number = variants_for_group(group).index(variant) + 1

    offset = (grade - min(GRADES)) * len(VARIANTS)
    passages = _passages()
    # len(VARIANTS) is 16 but there are only 15 passages, so a plain
    # `index % 15` would send the 16th variant (index 15) right back to
    # passage 0 - the same wrap point where the picture and rotating pools
    # also cycle back. `index // len(passages)` is 0 for every index except
    # the last, where it nudges the wrapped slot one passage forward so that
    # collision never happens. It also keeps the two variants in the last
    # group off the same passage, which the group tests now pin explicitly.
    passage_index = (index + index // len(passages) + offset) % len(passages)

    return Allocation(
        picture_clip=picture,
        rotating_clip=rotating,
        set_number=set_number,
        passage=passages[passage_index],
    )
