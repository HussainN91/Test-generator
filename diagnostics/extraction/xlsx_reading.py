"""Extract the 15 reading passages from the real content workbook.

Source: 'Reading QB with answers' tab in Question Bank -Diagnostic Test.xlsx.
Answer-key layout is NOT consistent across passages (at least five column
arrangements observed - verified 2026-08-24 against every one of the 15
passages) so the key parser is tolerant, scanning every row for a bare int
cell in 1-10 and reading the answer from the next non-empty cell, rather
than assuming one fixed header/column layout.

Question numbering is also inconsistent: most passages number each question
at the start of its own line ("9. Students can measure..."), but passage
2's note-completion block (questions 6-10) embeds the number mid-sentence
instead ("Beginners should practise in a 6. __________ place."), and some
question stems have NO number at all on the stem line - the position has
to be inferred from the enclosing "Questions N-M: ..." range marker, using
a lookahead (a plain line immediately followed by an "A. ..." option line
is a stem, not leftover instruction text) to tell an unnumbered stem apart
from unnumbered instruction prose. This is a general pattern, not a
one-off: it's confirmed to fire correctly for passage 7's questions 1-3
and passage 12's questions 9-10.
"""

import re

import openpyxl

from diagnostics.models import ReadingSubtype

PASSAGE_HEADER_RE = re.compile(r"^READING PASSAGE[\s\-]*(\d+)", re.IGNORECASE)
QUESTIONS_MARKER_RE = re.compile(r"^Questions?\s+[\d–—-]+", re.IGNORECASE)
#: Captures the numeric range out of a marker line, e.g. "Questions 1-3: ..."
#: -> (1, 3). Falls back to a single number ("Question 5") -> (5, 5).
QUESTIONS_RANGE_RE = re.compile(r"Questions?\s+(\d{1,2})\s*(?:[–—-]\s*(\d{1,2}))?", re.IGNORECASE)
OPTION_LINE_RE = re.compile(r"^([A-D])[.)]\s*(.+)$")
NUMBERED_QUESTION_RE = re.compile(r"^(\d{1,2})[.)]\s*(.+)$")
#: Fallback for note-completion items that number the blank inline instead
#: of starting the line with the number (passage 2, questions 6-10).
MID_LINE_BLANK_RE = re.compile(r"(\d{1,2})\.\s*(_+)")


def _extract_range(marker_text):
    """Pull the (start, end) question range out of a 'Questions N-M' marker."""
    match = QUESTIONS_RANGE_RE.search(marker_text)
    if not match:
        return None, None
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else start
    return start, end


SUBTYPE_HINTS = [
    (re.compile(r"heading", re.IGNORECASE), "heading_matching"),
    (re.compile(r"paragraph\s*[A-E–—-]", re.IGNORECASE), "paragraph_matching"),
    (re.compile(r"true.*false|not given", re.IGNORECASE), "true_false_ng"),
    (re.compile(r"complete|sentence completion|fill", re.IGNORECASE), "completion"),
]


def _guess_subtype(instruction_text):
    for pattern, subtype in SUBTYPE_HINTS:
        if pattern.search(instruction_text):
            return subtype
    return "mcq"  # multiple choice, "matching" (4-option), vocabulary-in-context all share this shape


def _sheet_rows(workbook):
    sheet = workbook["Reading QB with answers"]
    for row in sheet.iter_rows(values_only=False):
        yield [cell.value for cell in row[:4]]


def extract_passages(path):
    """Return a list of 15 dicts: {title, body, questions: [...]}."""
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    rows = list(_sheet_rows(workbook))

    boundaries = [
        i for i, row in enumerate(rows)
        if row[0] and isinstance(row[0], str) and PASSAGE_HEADER_RE.match(row[0])
    ]
    boundaries.append(len(rows))

    passages = []
    for start, end in zip(boundaries, boundaries[1:]):
        passages.append(_parse_one_passage(rows[start:end]))
    return passages


def _parse_one_passage(block):
    # .strip(): at least one title cell in the source has a stray leading
    # space (passage 8, ' A Different Way to Travel') - verified directly
    # against the raw workbook, not an extraction artefact.
    title = next(
        (row[0].strip() for row in block[1:6] if row[0] and isinstance(row[0], str)), None
    )

    # Body: every string cell in column A between the title and the first
    # 'Questions N...' marker, skipping blank rows.
    body_lines = []
    questions_start = None
    started = False
    for i, row in enumerate(block):
        text = row[0]
        if isinstance(text, str) and text.strip() == (title or "").strip():
            started = True
            continue
        if not started:
            continue
        if isinstance(text, str) and QUESTIONS_MARKER_RE.match(text.strip()):
            questions_start = i
            break
        if isinstance(text, str) and text.strip() and not PASSAGE_HEADER_RE.match(text):
            body_lines.append(text.strip())
    body = " ".join(body_lines)

    questions = _parse_questions(block[questions_start:] if questions_start else [])
    answers = _parse_answer_key(block)
    for question in questions:
        question["answer"] = answers.get(question["position"], question.get("answer", ""))

    return {"title": title, "body": body, "questions": questions}


def _parse_questions(rows):
    """Parse the question stems, options and subtypes for one passage.

    The 'Questions N-M' marker line frequently carries NO subtype
    information itself (e.g. plain "Questions 1-5") - the real instruction
    ("Do the following statements agree...", "TRUE - if...", "Choose the
    correct heading...") appears on the lines *between* the marker and the
    first numbered question. So subtype is guessed from the whole
    accumulated instruction blob for a block, not just the marker line.
    Some passages (e.g. passage 15) instead pack the subtype straight into
    the marker line itself ("Questions 4-6: True, False or Not Given") -
    accumulating handles both since the marker line is included in the blob.
    """
    questions = []
    current_subtype = "mcq"
    current_options = []
    pending = None
    instruction_buffer = []
    awaiting_subtype = False
    range_next = None
    range_end = None

    texts = [row[0] for row in rows]

    for idx, text in enumerate(texts):
        if not isinstance(text, str) or not text.strip():
            continue
        text = text.strip()

        if QUESTIONS_MARKER_RE.match(text):
            instruction_buffer = [text]
            awaiting_subtype = True
            range_next, range_end = _extract_range(text)
            continue

        option_match = OPTION_LINE_RE.match(text)
        if option_match and pending is not None:
            current_options.append(option_match.group(2))
            continue

        number_match = NUMBERED_QUESTION_RE.match(text)
        mid_match = None if number_match else MID_LINE_BLANK_RE.search(text)

        is_unnumbered_stem = False
        if (
            not number_match and not mid_match
            and range_next is not None and range_end is not None
            and range_next <= range_end
        ):
            # A line with no leading number, inside an active question range,
            # that is immediately followed by an "A. ..." option line is an
            # unnumbered stem rather than leftover instruction prose -
            # instruction lines are never option-followed. This is a general
            # pattern, not a passage-specific special case: it fires for
            # passage 7's questions 1-3 and was independently verified to
            # also correctly handle passage 12's questions 9-10 ("'Weak
            # areas' means areas in which someone:" and "Which statement
            # best expresses the writer's view?"), a second real instance
            # in the 15-passage bank.
            next_text = next(
                (t.strip() for t in texts[idx + 1:] if isinstance(t, str) and t.strip()),
                None,
            )
            if next_text and OPTION_LINE_RE.match(next_text):
                is_unnumbered_stem = True

        if number_match or mid_match or is_unnumbered_stem:
            if awaiting_subtype:
                current_subtype = _guess_subtype(" ".join(instruction_buffer))
                awaiting_subtype = False
                instruction_buffer = []
            if pending is not None:
                pending["options"] = current_options
                questions.append(pending)
            if number_match:
                position = int(number_match.group(1))
                stem = number_match.group(2)
            elif mid_match:
                position = int(mid_match.group(1))
                # Drop the inline "N." label, keep the blank: "a 6. ____ place"
                # reads as "a ____ place" once the question is shown standalone.
                stem = MID_LINE_BLANK_RE.sub(mid_match.group(2), text)
            else:
                position = range_next
                stem = text
            if range_next is not None:
                range_next = position + 1
            if position > 10:
                pending = None
                continue
            pending = {
                "position": position, "subtype": current_subtype,
                "stem": stem, "options": [], "answer": "",
            }
            current_options = []
            continue

        if awaiting_subtype:
            instruction_buffer.append(text)

    if pending is not None:
        pending["options"] = current_options
        questions.append(pending)

    return sorted(questions, key=lambda q: q["position"])


def _normalize_key_value(value):
    """TRUE/FALSE/NOT GIVEN answers show up as native bools OR as strings
    with inconsistent case ('NOT GIVEN' vs 'Not Given') across passages -
    normalise both to a consistent uppercase string. Everything else
    (letters, headings, gap-fill words) passes through unchanged."""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    text = str(value).strip()
    if text.upper() in {"TRUE", "FALSE", "NOT GIVEN"}:
        return text.upper()
    return text


def _parse_answer_key(block):
    """Locate the 1-10 answer rows regardless of header/column layout.

    The client's answer-key layout is genuinely inconsistent - verified
    across all 15 passages, at least five distinct arrangements observed:
      - ['KEY:', 'Q', 'Answer'] header, data starting one column in
      - a further one-column-right-shifted variant of the same header
      - a bare ['Q', 'Answer'] header with NO 'KEY' text anywhere
      - a 'KEY' marker on its own row, THEN a ['Q', 'Answer'] header row
      - an 'Answer Key' marker row followed *directly* by data, no header
    Rather than special-case each layout, this scans every row in the block
    for a cell that is an int in 1-10 (excluding bool, since True/False
    answers are also ints in Python) and takes the next non-None cell after
    it as the answer. Question stems and options never contain a bare int
    cell (they're always one text string like "9. Students can measure..."
    or "A. To replace science classrooms"), so this does not collide with
    the question-parsing pass above.
    """
    answers = {}
    for row in block:
        for idx, cell in enumerate(row):
            if isinstance(cell, bool) or not isinstance(cell, int):
                continue
            if not 1 <= cell <= 10:
                continue
            rest = [c for c in row[idx + 1:] if c is not None]
            if rest:
                answers[cell] = _normalize_key_value(rest[0])
            break
    return answers


#: The 7 (passage label, position) pairs independently verified against the
#: raw workbook as genuine paragraph-matching items mislabelled 'mcq'
#: (Design Revision 2, section 4.1). resolve_subtype() converts any
#: option-less mcq unconditionally - this set is what keeps that conversion
#: from silently swallowing a genuinely new, unverified anomaly.
VERIFIED_MATCHING_ITEMS = {
    ("R04", 6), ("R04", 7), ("R04", 8), ("R04", 9), ("R04", 10),
    ("R10", 9), ("R10", 10),
}


def resolve_subtype(subtype, options, label, position):
    """Reclassify an option-less MCQ as paragraph_matching - or refuse to.

    An MCQ always ships its options, so an option-less mcq row is really a
    matching item mislabelled upstream. Seven such rows were independently
    verified against the raw workbook (Design Revision 2, section 4.1) and
    are safe to convert automatically. Any OTHER option-less mcq is a
    genuinely new, unverified anomaly - this raises rather than silently
    converting it, because a second real conversion rule has never been
    checked against source data.
    """
    if subtype != ReadingSubtype.MCQ or options:
        return subtype
    if (label, position) not in VERIFIED_MATCHING_ITEMS:
        raise ValueError(
            f"{label} Q{position}: MCQ with no options, but this is not "
            f"one of the 7 positions independently verified as "
            f"paragraph-matching items. A new, unverified source shape "
            f"has appeared - inspect the raw workbook row before adding "
            f"it to VERIFIED_MATCHING_ITEMS."
        )
    return ReadingSubtype.PARAGRAPH_MATCHING
