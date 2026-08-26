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
"""

from diagnostics.constants import (
    GRADES, PICTURE_CLIPS, ROTATING_CLIPS_BY_TYPE, VARIANTS,
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


def allocate(grade, variant):
    """Return (picture_clip_number, rotating_clip_number, passage_label).

    Pure: the same arguments always produce the same result, with no
    database access and no randomness.

    The grade offset staggers each grade's starting point so grades do not
    all open on the same clip - cross-grade reuse is permitted, but three
    identical-looking grade 9/10/11 variant As would look like a bug to a
    teacher holding two of them.

    The passage index also gets a one-slot nudge on the last variant of
    every grade, to stop it wrapping onto passage 0 in exact lockstep with
    the picture and rotating pools - see the inline comment above the
    passage calculation for the arithmetic.
    """
    try:
        index = VARIANTS.index(variant)
    except ValueError:
        raise ValueError(
            f"Unknown variant {variant!r}; expected one of {''.join(VARIANTS)}."
        ) from None

    offset = (grade - min(GRADES)) * len(VARIANTS)

    picture = PICTURE_CLIPS[(index + offset) % len(PICTURE_CLIPS)]
    rotating = _ROTATION[(index + offset) % len(_ROTATION)]

    passages = _passages()
    # len(VARIANTS) is 16 but there are only 15 passages, so a plain
    # `index % 15` would send the 16th variant (index 15) right back to
    # passage 0 - the same wrap point where the picture pool (%5) and the
    # rotation list (%15) also both cycle back to their own index-0 value.
    # Left alone, that quadruple coincidence would make the very last
    # variant in every grade an exact duplicate of the very first one on
    # all three axes at once. `index // len(passages)` is 0 for every
    # index except the last, where it nudges the wrapped slot one passage
    # forward so that one collision never happens; nothing else in the
    # 0-14 range is affected.
    passage_index = (index + index // len(passages) + offset) % len(passages)
    passage = passages[passage_index]

    return picture, rotating, passage
