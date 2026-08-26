"""Extract the 50-prompt speaking bank and its marking rubric.

Sources, verified 2026-08-24/25 against every row of the real sheets:

  - 'Speaking QB' tab: 5 sections (A-E) of 10 numbered prompts each (1-50
    numbered CONTINUOUSLY across the whole sheet - section A holds 1-10,
    B holds 11-20, C 21-30, D 31-40, E 41-50; numbering never restarts),
    mapped to the 5 fixed SpeakingTask values in section order.

  - 'Speaking Assessment Rubrics' tab: one row per task with its mark
    value and skill-indicator description (rows 7-11, 'Q1'..'Q5' in
    column A).

The 'Speaking QB' sheet is NOT uniform in how each numbered item is laid
out - confirmed by reading every row of the sheet directly, not assumed:

  - Section B's (11-20) numbered line already IS the complete prompt
    sentence, e.g. "11. Describe a memorable day at school." - it ends
    in terminal punctuation ('.', '?', '!').

  - Sections A, C, D, E's numbered line is instead a short topic LABEL
    with no terminal punctuation, e.g. "1. Personal Introduction" or
    "31. Planning a School Event". The real prompt sentence is the next
    content line, e.g. "Speak for 30-45 seconds." / "You and the
    examiner are planning an English Week event."

  Which of the two shapes applies is detected per item by whether the
  numbered line's text ends with sentence punctuation - not by section,
  since that's the only reliable per-item signal.

  - Every item then has zero or more short instruction "marker" lines
    (things like "Include:", "Ask:", "Follow-up:", "Situation:", "Then:")
    that introduce the bullet points/follow-up questions that follow, and
    are dropped rather than kept as prompt or bullet text. These were
    enumerated by scanning every colon-terminated line in the whole sheet
    (MARKER_PHRASES below) rather than guessed or matched generically by
    "ends with ':'" - there were exactly 19 such lines, 17 of which are
    short generic lead-ins with no content of their own, and 2 of which
    are real scenario/instruction content that merely happen to end in a
    colon because they introduce named options and have NO other
    sentence anywhere in their item to serve as the prompt:

      - item 32: "You and your partner need to choose one club:"
      - item 38: "Choose the best activity:"

    Both were confirmed directly against the raw sheet rows (no other
    content line precedes them in their item). A blanket "any
    colon-terminated line is a marker" rule would silently turn item 38
    into a broken one-word prompt ("football" - its first bullet option),
    since nothing would be left to serve as the prompt once its one real
    lead-in line was dropped. Both are therefore deliberately excluded
    from MARKER_PHRASES so they survive as prompt text. Every other
    colon-terminated line in the sheet was checked and always appears
    after some other line has already established the item's prompt, so
    dropping those 17 is safe.

  - After marker lines are dropped, the first remaining content line is
    the prompt (or, for section-B-shaped items, the numbered line itself
    is already the prompt and ALL remaining lines are bullets) and any
    further lines are bullets/follow-up questions.
"""

import re

import openpyxl

SECTION_HEADER_RE = re.compile(r"^SECTION\s+([A-E])", re.IGNORECASE)
NUMBERED_ITEM_RE = re.compile(r"^(\d{1,2})\.\s*(.+)$")
SENTENCE_END_RE = re.compile(r"[.?!]$")

SECTION_TO_TASK = {
    "A": "introduction", "B": "experience", "C": "description",
    "D": "role_play", "E": "opinion",
}

#: Short generic instruction lead-ins that introduce a bullet/follow-up
#: list and carry no content of their own - verified against every
#: colon-terminated line in the 'Speaking QB' sheet (see module
#: docstring). Deliberately excludes "You and your partner need to choose
#: one club:" (item 32) and "Choose the best activity:" (item 38), which
#: are each the sole real prompt content for their item despite the colon.
MARKER_PHRASES = frozenset({
    "ask the student to describe:", "ask the student to explain:", "ask:",
    "choose between:",
    "discuss how you can help the student:", "discuss possible solutions:",
    "discuss:", "explain:", "follow-up:", "include:", "situation:",
    "talk about:", "the student should identify:",
    "the student should mention:", "then ask:", "then:", "you should say:",
})


def extract_speaking_prompts(path):
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    sheet = workbook["Speaking QB"]
    rows = [row[0].value if row else None for row in sheet.iter_rows(max_col=1)]

    section_bounds = []
    for i, text in enumerate(rows):
        if isinstance(text, str):
            match = SECTION_HEADER_RE.match(text.strip())
            if match:
                section_bounds.append((i, SECTION_TO_TASK[match.group(1).upper()]))
    section_bounds.append((len(rows), None))

    prompts = []
    for (start, task), (end, _) in zip(section_bounds, section_bounds[1:]):
        prompts.extend(_parse_section(rows[start:end], task))
    _check_prompt_sanity(prompts)
    return prompts


def _check_prompt_sanity(prompts):
    """Guard against the MARKER_PHRASES trap that broke item 38 during
    development: excluding a real content line by mistake there silently
    turned its prompt into "football" - a single bullet option promoted
    to prompt because the real lead-in got dropped as a "marker". A
    suspiciously short prompt (<= 2 words) is the signature of that
    failure mode, and a bullet that still ends in ':' means a marker line
    leaked through un-dropped. Neither should ever happen against the
    current sheet; if a future re-extraction trips this, it's new
    information (a genuine extraction bug, or new source data with a
    similar quirk) worth investigating rather than silently accepting.
    """
    for item in prompts:
        if len(item["prompt"].split()) <= 2:
            raise ValueError(
                f"Suspiciously short speaking prompt for task {item['task']!r}: "
                f"{item['prompt']!r} - likely a marker line was dropped without "
                f"anything real left to serve as the prompt. Investigate before "
                f"trusting this import."
            )
        if any(bullet.endswith(":") for bullet in item["bullets"]):
            raise ValueError(
                f"A marker-looking bullet (ending in ':') leaked through for "
                f"task {item['task']!r}, prompt {item['prompt']!r}: {item['bullets']!r}."
            )


def _parse_section(rows, task):
    items = []
    title = None
    lines = []

    def flush():
        if title is None:
            return
        if SENTENCE_END_RE.search(title):
            # The numbered line is already the complete prompt (section B
            # shape); everything collected after it (markers already
            # dropped during collection) is bullets.
            prompt = title
            bullets = lines
        elif lines:
            # The numbered line is a bare topic label (sections A/C/D/E
            # shape); the first real content line is the prompt.
            prompt = lines[0]
            bullets = lines[1:]
        else:
            # No content line ever showed up - fall back to the label
            # itself rather than losing the item.
            prompt = title
            bullets = []
        items.append({"task": task, "prompt": prompt, "bullets": bullets})

    for text in rows:
        if not isinstance(text, str) or not text.strip():
            continue
        text = text.strip()

        numbered = NUMBERED_ITEM_RE.match(text)
        if numbered:
            flush()
            title = numbered.group(2)
            lines = []
            continue

        if title is None:
            # Preamble before the section's first numbered item (section
            # header, "Questions N-M", "Purpose: ..."), not part of any
            # item - skip.
            continue

        if text.lower() in MARKER_PHRASES:
            continue

        lines.append(text)

    flush()
    return items


def extract_rubric(path):
    """Return {task: {"marks": int, "indicators": str}} for the 5 fixed tasks."""
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    sheet = workbook["Speaking Assessment Rubrics"]

    task_order = ["introduction", "experience", "description", "role_play", "opinion"]
    rubric = {}
    for row in sheet.iter_rows(min_row=7, max_row=11, values_only=True):
        question_label, _task_desc, indicators, marks = row[0], row[1], row[2], row[3]
        if not question_label or not str(question_label).upper().startswith("Q"):
            continue
        index = int(str(question_label).upper().lstrip("Q")) - 1
        if 0 <= index < len(task_order):
            rubric[task_order[index]] = {"marks": int(marks), "indicators": indicators}
    return rubric
