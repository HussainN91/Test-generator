"""Extract real question stems and options from a listening clip's body text.

Reuses `split_clips` (worksheets.py) for clip boundaries — this module only
turns one clip's raw body text into the five per-question stem/options
dicts. Each of the four task-type shapes was verified directly against the
real source file, including two real formatting quirks:

  - Sentence boundaries in the cloze-passage clips (3, 18, 19) are sometimes
    glued with no space ("...front of the (4) … .There are no
    animals..."), so sentence-splitting must not require a space after the
    period.
  - Clip 19's second gap-fill blank is mislabelled "(**3**)" in the source
    (the real marker sequence is 1, 3, 3, 4, 5 - there is no "2" at all).
    Blanks are therefore matched by their left-to-right order of
    appearance, never by the digit printed inside the marker.

Two of the five gap-fill clips (7 and 11) are note/form layouts rather than
a single flowing paragraph - one blank per line instead of several blanks
sharing one line. Both shapes are handled by the same function: a line with
exactly one blank marker is used as-is; a line with more than one marker
(the cloze-paragraph case) is split into sentences first.
"""

import re

from diagnostics.constants import TaskType

EXPECTED = 5

ANSWERS_MARKER_RE = re.compile(r"Answers?\s*:?", re.IGNORECASE)

#: Picture clips: "**1**   Which dish did Mark cook in the competition?"
#: Some clips (5, 13) wrap every line in a "#####" heading; clip 9's first
#: question has its image glued onto the same line with no separator at
#: all ("...woman's bag?![][image11]") - the trailing image markdown is
#: stripped out in _clean.
PICTURE_LINE_RE = re.compile(r"^#*\s*\*\*(\d)\*\*\s+(.+)$")

#: A markdown image reference, e.g. "![][image11]" - strips images that
#: get glued directly onto a question line with no separator.
IMAGE_REF_RE = re.compile(r"!\[.*?\]\[.*?\]")

#: MCQ3 clips: "**1\.**   Simon's mum decided..." then "**A**   she had...".
#: The trailing period is not consistent across clips - clip 6 uses
#: "**1**" with no period at all - so it is optional here.
MCQ3_QUESTION_RE = re.compile(r"^\*\*(\d)\\?\.?\*\*\s+(.+)$")
MCQ3_OPTION_RE = re.compile(r"^\*\*([ABC])\*\*\s+(.+)$")

#: True/false table rows: "| **1**   Lucas thinks ... | **A** | **B** |"
TRUE_FALSE_ROW_RE = re.compile(r"^\|\s*\*\*(\d)\*\*\s+(.*?)\s*\|")

#: A gap-fill blank: "(**1**)" optionally followed by "£" then a run of
#: horizontal-ellipsis characters (U+2026), e.g. "(**3**) £………".
BLANK_RE = re.compile(r"\(\*\*\d+\*\*\)\s*(£?)\s*…+")

#: A sentence boundary: '.', '!' or '?' followed by optional whitespace and
#: a capital letter (or end of string). Deliberately does not require a
#: space, to handle the glued "sentence.Next" quirk described above.
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s*(?=[A-Z])")


#: Verbatim slips in the client's own document that would otherwise be
#: printed onto a student's paper. Keyed by (clip number, question
#: position); each entry pairs the exact wrong stem with its correction,
#: and is applied only when the stem still matches character for
#: character - so the client fixing their file upstream quietly turns the
#: entry into a no-op instead of crashing the import or double-correcting.
#:
#: Deliberately narrow. Almost every entry here is an unambiguous
#: spelling/agreement slip (a wrong or missing letter, a singular/plural
#: mismatch) verified against the raw line. The one exception is clip 1
#: Q4, a verified content error rather than a typo: the source transcript
#: has the *boy* packing for the holiday, not the girl printed in this
#: stem. Anything else that changes what a question asks, and any
#: answer-key disagreement, goes back to the client instead - clip 19
#: Q5's answer "CITYENTS" (for "tickets online at www.____.org") is the
#: standing example: plainly garbled, but the real value is unknowable
#: without listening to the audio, so it stays as the source has it.
STEM_CORRECTIONS = {
    (1, 4): (
        "What will the girl take with her on holiday?",
        "What will the boy take with him on holiday?",
    ),
    (4, 3): (
        "Lucas and Claire have the name opinion about the band’s costumes.",
        "Lucas and Claire have the same opinion about the band’s costumes.",
    ),
    (5, 4): (
        "Which pictures shows what happened?",
        "Which picture shows what happened?",
    ),
    (6, 5): (
        "What does the festival programme offer at lckworth?",
        "What does the festival programme offer at Ickworth?",
    ),
    (13, 3): (
        "Why will drives have problems this morning?",
        "Why will drivers have problems this morning?",
    ),
}


def extract_question_content(clip_number, task_type, body):
    """Return [{"stem": str, "options": [str, ...]}, ...] for 5 questions.

    `task_type` is one of the diagnostics.constants.TaskType values.
    `body` is the raw clip text as returned by worksheets.split_clips.
    """
    if task_type == TaskType.PICTURE:
        items = _extract_picture(body)
    elif task_type == TaskType.MCQ3:
        items = _extract_mcq3(body)
    elif task_type == TaskType.TRUE_FALSE:
        items = _extract_true_false(body)
    elif task_type == TaskType.GAP_FILL:
        items = _extract_gap_fill(body)
    else:
        raise ValueError(f"Unknown task_type {task_type!r} for clip {clip_number}")
    return _apply_corrections(clip_number, items)


def _apply_corrections(clip_number, items):
    """Swap in the STEM_CORRECTIONS text for any stem that still matches."""
    for position, item in enumerate(items, start=1):
        correction = STEM_CORRECTIONS.get((clip_number, position))
        if correction is not None and item["stem"] == correction[0]:
            item["stem"] = correction[1]
    return items


def _before_answers(body):
    """Everything before the key.

    Uses the *last* 'Answers' marker, mirroring keys.py's
    `_after_last_marker` - the framing text ("choose the correct answer.")
    contains the word "answer" too, so the first match would truncate the
    passage before any of the actual questions.
    """
    matches = list(ANSWERS_MARKER_RE.finditer(body))
    return body[: matches[-1].start()] if matches else body


def _clean(text):
    """Strip markdown noise and collapse whitespace."""
    text = text.replace("\\", "")
    text = text.replace("**", "")
    text = IMAGE_REF_RE.sub("", text)
    text = re.sub(r"\s+([.,;:])", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _check_positions(mapping, clip_hint):
    if sorted(mapping) != list(range(1, EXPECTED + 1)):
        raise ValueError(
            f"Expected positions 1-{EXPECTED}, found {sorted(mapping)} "
            f"while parsing: {clip_hint!r}"
        )


def _extract_picture(body):
    passage = _before_answers(body)
    found = {}
    for line in passage.splitlines():
        match = PICTURE_LINE_RE.match(line.strip())
        if match:
            found[int(match.group(1))] = _clean(match.group(2))
    _check_positions(found, passage)
    return [{"stem": found[n], "options": []} for n in range(1, EXPECTED + 1)]


def _extract_mcq3(body):
    passage = _before_answers(body)
    questions = {}
    current = None
    for raw_line in passage.splitlines():
        line = raw_line.strip()
        question_match = MCQ3_QUESTION_RE.match(line)
        if question_match:
            current = int(question_match.group(1))
            questions[current] = {"stem": _clean(question_match.group(2)), "options": []}
            continue
        option_match = MCQ3_OPTION_RE.match(line)
        if option_match and current is not None:
            questions[current]["options"].append(_clean(option_match.group(2)))
    _check_positions(questions, passage)
    for number, question in questions.items():
        if len(question["options"]) != 3:
            raise ValueError(
                f"MCQ3 question {number} has {len(question['options'])} "
                f"options (expected 3): {question}"
            )
    return [questions[n] for n in range(1, EXPECTED + 1)]


def _extract_true_false(body):
    passage = _before_answers(body)
    found = {}
    for line in passage.splitlines():
        match = TRUE_FALSE_ROW_RE.match(line.strip())
        if match:
            found[int(match.group(1))] = _clean(match.group(2))
    _check_positions(found, passage)
    return [{"stem": found[n], "options": ["YES", "NO"]} for n in range(1, EXPECTED + 1)]


def _split_sentences(text):
    return [part.strip() for part in SENTENCE_SPLIT_RE.split(text) if part.strip()]


def _render_blank(match):
    return match.group(1) + "______"


def _extract_gap_fill(body):
    passage = _before_answers(body)
    units = []
    for raw_line in passage.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        marker_count = len(BLANK_RE.findall(line))
        if marker_count == 0:
            continue
        if marker_count == 1:
            units.append(line)
        else:
            # A cloze-paragraph line carrying several blanks: split into
            # sentences and keep only the ones that actually own a blank.
            units.extend(s for s in _split_sentences(line) if BLANK_RE.search(s))

    if len(units) != EXPECTED:
        raise ValueError(
            f"Expected {EXPECTED} gap-fill units, found {len(units)} "
            f"while parsing: {passage!r}"
        )

    results = []
    for unit in units:
        stem = BLANK_RE.sub(_render_blank, unit)
        results.append({"stem": _clean(stem), "options": []})
    return results
