"""Extract the 200-question writing bank from the real content workbook.

Source: 'Writing QB with key' tab. Layout, verified 2026-08-24/25 against
every row of the real sheet: four labelled sections (A. GRAMMAR, B.
VOCABULARY, C. JUMBLED PARAGRAPHS, D. FILL IN THE BLANKS), 50 questions
each.

Grammar/vocabulary/fill_blank are uniform throughout: one 'N. stem' row
followed by one 'A) opt B) opt C) opt D) opt' row.

The jumbled-paragraphs section is NOT uniform - it silently switches format
partway through, confirmed by reading every row of the section directly
(not assumed):

  - Q101-120 ("format 1"): the question number stands alone in its own
    cell as a bare int, followed by four separate 'A. sentence' / 'B.
    sentence' / 'C. sentence' / 'D. sentence' rows (the un-ordered
    sentences), followed by one options row 'A) B-C-D-A B) C-B-A-D
    C) B-D-C-A D) D-B-C-A' where each lettered option is a full candidate
    re-ordering of the four sentences. This is a genuine 4-option MCQ:
    "options" here means resequencing choices.

  - Q121-150 ("format 2"): a single row "121. A: sentence. B: sentence.
    C: sentence. D: sentence." followed by a separate 'Answer: X-X-X-X'
    row giving ONE reference correct order directly - there is no
    4-candidate-ordering row at all for these 30 questions, despite an
    instruction row right before them (row ~501, "Use the same four-option
    ordering format with the following sequences.") claiming otherwise.
    That instruction does not match the actual data; nothing was invented
    to satisfy it. Since there's no real 4-option resequencing choice to
    extract here, "options" for these items is the four sentences
    themselves (label stripped), and the answer is which sentence the
    master key says comes first - see below.

The answer key is a separate block near the end of the sheet ('Answer
key:' marker followed by four 'Q'/'Ans' mini-tables, 50 rows each, grouped
A. Grammar/B. Vocabulary/C. Jumbled Paragraphs/D. Fill in the Blanks and
numbered 1-200 continuously). ALL answers, for every subtype including
jumbled, are taken from this master block, never from any inline "Answer:"
text in the question sections - confirmed the master key is present and
complete for every one of the 200 question numbers.

For jumbled format-1 items, the master key's letter picks which of the
four full-reordering candidates (A/B/C/D) is correct - this is a normal
MCQ-letter answer. For jumbled format-2 items, cross-checking the master
key against each item's inline 'Answer: W-X-Y-Z' order string shows the
master key's letter equals the first letter of that order string in 28 of
30 cases. Two exceptions, both confirmed directly against the raw sheet
(not extraction artifacts - the inline row, its 'Answer:' row, and the
master key's own (Q, Ans) cell were each read independently for both):

  - Q123: inline says 'B-A-C-D' (opens with B), master key says 'A'.
  - Q135: inline says 'D-A-B-C' (opens with D), master key says 'C'.

(An earlier pass over this data had only found the Q135 case; Q123 was
caught by the runtime mismatch-count safeguard in
_check_jumbled_inline_mismatches below during later verification, which is
exactly what that safeguard is for.)

So for format-2 items the master key's letter means "which sentence, by
its original A/B/C/D label, opens the correct paragraph" - and that is
exactly what gets stored as the answer against the sentence-only options
list. The master key is authoritative per the brief above, so these two
inconsistent rows are carried through as-is rather than silently
"corrected" from the inline text.
"""

import re

import openpyxl

#: Only used to find the 4 real section headers, and to detect (and then
#: deliberately stop before) the master key's look-alike sub-headers such
#: as "A. Grammar - 1-50", which match this same shape. See
#: _find_section_boundaries for how that collision is avoided.
SECTION_HEADER_RE = re.compile(
    r"^([A-D])\.\s*(GRAMMAR|VOCABULARY|JUMBLED PARAGRAPHS|FILL IN THE BLANKS)", re.IGNORECASE
)
QUESTION_LINE_RE = re.compile(r"^(\d{1,3})\.\s*(.+)$")
OPTIONS_LINE_RE = re.compile(
    r"A\)\s*(.+?)\s*B\)\s*(.+?)\s*C\)\s*(.+?)\s*D\)\s*(.+?)$"
)
#: Jumbled format-1 raw sentence row: "A. Finally, she submitted...".
JUMBLED_SENTENCE_RE = re.compile(r"^([A-D])\.\s*(.+)$")
#: Jumbled format-2 single-row question: "121. A: ... B: ... C: ... D: ...".
JUMBLED_INLINE_RE = re.compile(
    r"^(\d{1,3})\.\s*A:\s*(.+?)\s*B:\s*(.+?)\s*C:\s*(.+?)\s*D:\s*(.+)$"
)

SECTION_TO_SUBTYPE = {
    "GRAMMAR": "grammar", "VOCABULARY": "vocabulary",
    "JUMBLED PARAGRAPHS": "jumbled", "FILL IN THE BLANKS": "fill_blank",
}


def extract_writing_items(path):
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    sheet = workbook["Writing QB with key"]
    # The master key table uses up to 5 (Q, Ans) column-pairs (10 columns)
    # for the grammar/vocabulary/fill_blank sections - verified directly
    # against the real sheet, which is wider than the 3-pair (6-column)
    # table used for the jumbled section. 16 columns gives headroom.
    rows = [[cell.value for cell in row[:16]] for row in sheet.iter_rows(values_only=False)]
    col0 = [r[0] for r in rows]

    key_start = _find_answer_key_start(col0)
    section_bounds = _find_section_boundaries(col0[:key_start])
    section_bounds.append((key_start, None))

    items_by_subtype = {}
    for (start, subtype), (end, _) in zip(section_bounds, section_bounds[1:]):
        if subtype == "jumbled":
            items_by_subtype[subtype] = _parse_jumbled_section(col0[start:end])
        else:
            items_by_subtype[subtype] = _parse_simple_section(col0[start:end], subtype)

    key_by_number = _parse_master_key(rows[key_start:])

    all_items = []
    for subtype in ("grammar", "vocabulary", "jumbled", "fill_blank"):
        for item in items_by_subtype[subtype]:
            item["answer"] = key_by_number.get(item["number"], "")
            del item["number"]
            all_items.append(item)

    _check_jumbled_inline_mismatches(all_items)
    for item in all_items:
        item.pop("_inline_answer_letter", None)
    return all_items


def _check_jumbled_inline_mismatches(all_items):
    """Guard the format-2 jumbled data quirks described in the module
    docstring: cross-checking each format-2 item's inline 'Answer: W-X-Y-Z'
    first letter against the master key's answer currently finds exactly 2
    disagreements (Q123, Q135) out of 30 format-2 items - both verified,
    isolated source data inconsistencies, not extraction bugs. If a future
    re-extraction ever turns up more than these 2 known mismatches, that's
    new information (either further real data inconsistencies or a genuine
    extraction bug) that deserves investigation rather than silent
    acceptance.
    """
    mismatch_count = sum(
        1
        for item in all_items
        if item["subtype"] == "jumbled"
        and "_inline_answer_letter" in item
        and item["_inline_answer_letter"] != item["answer"]
    )
    if mismatch_count > 2:
        raise ValueError(
            f"Expected at most 2 jumbled inline/master-key answer mismatches "
            f"(the known item-123 and item-135 data quirks), found {mismatch_count}. "
            f"A new discrepancy appeared - investigate before trusting this import."
        )


def _find_answer_key_start(col0):
    for i, text in enumerate(col0):
        if isinstance(text, str) and "answer key" in text.lower():
            return i
    return len(col0)


def _find_section_boundaries(col0):
    """Locate the 4 real section headers. Restricted to rows before the
    master answer-key block, because the key's own sub-headers ('A.
    Grammar - 1-50', 'B. Vocabulary - 51-100', ...) match the exact same
    SECTION_HEADER_RE shape as the real ones - without this cutoff the
    scan finds 8 "sections" and the 4 phantom ones (built from key rows
    that don't look like questions) silently overwrite every real subtype
    with an empty list. Confirmed by direct inspection of the real sheet.
    """
    bounds = []
    for i, text in enumerate(col0):
        if isinstance(text, str):
            match = SECTION_HEADER_RE.match(text.strip())
            if match:
                bounds.append((i, SECTION_TO_SUBTYPE[match.group(2).upper()]))
    return bounds


def _parse_simple_section(col0, subtype):
    """Grammar / vocabulary / fill_blank: uniform 'N. stem' + 'A) .. D) ..'."""
    items = []
    pending_number = None
    pending_stem = None

    for text in col0:
        if not isinstance(text, str) or not text.strip():
            continue
        text = text.strip()

        options_match = OPTIONS_LINE_RE.search(text)
        if options_match and pending_number is not None:
            items.append({
                "number": pending_number,
                "subtype": subtype,
                "stem": pending_stem,
                "options": list(options_match.groups()),
            })
            pending_number = None
            pending_stem = None
            continue

        question_match = QUESTION_LINE_RE.match(text)
        if question_match:
            pending_number = int(question_match.group(1))
            pending_stem = question_match.group(2)
            continue

    return items


def _parse_jumbled_section(col0):
    items = []
    pending_number = None
    pending_sentences = []

    for text in col0:
        if text is None:
            continue

        if isinstance(text, int):
            # Format 1's bare question-number cell: start a new item.
            pending_number = text
            pending_sentences = []
            continue

        if not isinstance(text, str) or not text.strip():
            continue
        text = text.strip()

        if text.lower().startswith("answer:"):
            # Format 2's inline order string, e.g. "Answer: D-A-B-C" - the
            # master key rules (see module docstring), so this is never
            # used as the stored answer. Its first letter is stashed on the
            # item that was just appended so extract_writing_items can
            # cross-check it against the master key as a safeguard against
            # new/unnoticed discrepancies (see _check_jumbled_inline_mismatches).
            inline_answer_match = re.match(r"answer:\s*([A-D])", text, re.IGNORECASE)
            if inline_answer_match and items:
                items[-1]["_inline_answer_letter"] = inline_answer_match.group(1).upper()
            continue

        inline_match = JUMBLED_INLINE_RE.match(text)
        if inline_match:
            qnum = int(inline_match.group(1))
            sentences = inline_match.groups()[1:]
            items.append({
                "number": qnum,
                "subtype": "jumbled",
                "stem": "\n".join(
                    f"{letter}. {sentence}"
                    for letter, sentence in zip("ABCD", sentences)
                ),
                "options": list(sentences),
            })
            pending_number = None
            pending_sentences = []
            continue

        sentence_match = JUMBLED_SENTENCE_RE.match(text) if pending_number is not None else None
        if sentence_match and len(pending_sentences) < 4:
            pending_sentences.append(text)
            continue

        options_match = OPTIONS_LINE_RE.search(text)
        if options_match and pending_number is not None and len(pending_sentences) == 4:
            items.append({
                "number": pending_number,
                "subtype": "jumbled",
                "stem": "\n".join(pending_sentences),
                "options": list(options_match.groups()),
            })
            pending_number = None
            pending_sentences = []
            continue

        # Anything else (section header, instruction prose, the bare
        # "121-150" transition marker) is noise between questions - skip.

    return items


def _parse_master_key(rows):
    """The answer-key block: 'Q'/'Ans' header rows followed by data rows
    holding up to 5 (Q, Ans) column-pairs each for grammar/vocabulary/
    fill_blank, or 3 pairs for jumbled. Q numbers run 1-200 continuously
    across all four subtypes, so no section bookkeeping is needed here -
    just collect every (int Q, str Ans) pair directly.
    """
    key_by_number = {}
    for row in rows:
        for col in range(0, len(row) - 1, 2):
            q, a = row[col], row[col + 1]
            if isinstance(q, int) and isinstance(a, str) and a.strip():
                key_by_number[q] = a.strip()
    return key_by_number
