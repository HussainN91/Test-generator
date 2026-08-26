"""Parse answer keys out of the client's worksheet text.

The source uses at least six conventions, all of them present in the tests:
a colon glued to the first number, the key on the following line, a missing
space between number and letter, a missing separator between two answers,
markdown escapes, and — worst — a gap-fill answer that is itself a digit
("4 5 / five"), which a left-to-right scan would mistake for the next marker.

Nothing here is trusted blindly: `verify_listening_keys` (Task 12) forces a
human to sign off all 100 answers before they can be used.
"""

import re

ANSWERS_MARKER_RE = re.compile(r"Answers?\s*:?", re.IGNORECASE)
LETTER_PAIR_RE = re.compile(r"([1-5])\s*\.?\s*([ABC])\b")
EXPECTED = 5


def _normalise(blob):
    """Strip markdown noise so the numbering is visible."""
    cleaned = blob.replace("\\", "").replace("*", "").replace("#", "")
    return re.sub(r"\s+", " ", cleaned)


def _after_last_marker(blob):
    """Everything after the final 'Answers' marker.

    Using the *last* marker avoids picking up option letters that appear in
    the question text above the key.
    """
    text = _normalise(blob)
    matches = list(ANSWERS_MARKER_RE.finditer(text))
    if not matches:
        raise ValueError("No 'Answers' marker found.")
    return text[matches[-1].end():]


def parse_letter_key(blob):
    """Parse an A/B/C key into five letters. For picture, mcq3 and true_false."""
    tail = _after_last_marker(blob)
    pairs = LETTER_PAIR_RE.findall(tail)

    answers = {}
    for number, letter in pairs:
        number = int(number)
        if number in answers and answers[number] != letter:
            raise ValueError(
                f"Marker {number} has conflicting answers {answers[number]!r} and "
                f"{letter!r} in {tail!r}."
            )
        answers[number] = letter

    if sorted(answers) != [1, 2, 3, 4, 5]:
        raise ValueError(f"Expected 5 lettered answers, found {sorted(answers)}: {tail!r}")
    return [answers[n] for n in range(1, EXPECTED + 1)]


def parse_gap_fill_key(blob):
    """Parse a numbered gap-fill key into five answer strings.

    Markers are located left to right, except the final one, which is taken
    from the *last* plausible position so that an answer containing a digit
    (clip 19's "4 5 / five") is not truncated.

    This asymmetry (last-match only for the final marker) is scoped to the 20
    known clips, all of which parse correctly — verified by direct execution
    against the real source file. It is not a general-purpose guarantee for
    markers 1-4: an early answer containing a digit matching the next marker
    could in principle cause a similar mis-split. The real safety net against
    that residual risk is verify_listening_keys, which requires a human to
    check every parsed answer against the real audio before use.
    """
    tail = _after_last_marker(blob)

    starts = []
    cursor = 0
    for number in range(1, EXPECTED + 1):
        pattern = re.compile(rf"(?<!\d){number}\s*[.):]?\s*")
        if number < EXPECTED:
            match = pattern.search(tail, cursor)
        else:
            candidates = [m for m in pattern.finditer(tail, cursor)]
            match = candidates[-1] if candidates else None
        if match is None:
            raise ValueError(f"Could not locate marker {number} in {tail!r}")
        starts.append((match.start(), match.end()))
        cursor = match.end()

    answers = []
    for index, (_start, end) in enumerate(starts):
        stop = starts[index + 1][0] if index + 1 < len(starts) else len(tail)
        answers.append(tail[end:stop].strip(" .:,"))

    if any(not answer for answer in answers):
        raise ValueError(f"Empty answer parsed from {tail!r}: {answers}")
    return answers


def split_alternatives(answer):
    """Split 'a / b' or 'a/b' into acceptable alternatives."""
    parts = [part.strip() for part in answer.split("/")]
    return [part for part in parts if part]
