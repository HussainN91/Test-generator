"""The shape of a diagnostic paper, independent of any output format.

Every paper is the same four sections worth ten marks each. This module says
what is *in* those sections; management/commands/render_paper.py says what
they look like on a page, and a future HTML print view can read the same
dicts. Plain dicts and real model instances, deliberately — a renderer that
needs a question's image or a passage's word count should be able to reach
for it without a new field being plumbed through here first.

One rule this module exists to enforce: writing and speaking content is
reached through the ordering `PaperWritingQuestion`/`PaperSpeakingPrompt`
slots, never through `paper.writing_questions.all()`. The plain M2M accessor
ignores the through model's `position`, so it can hand back the same ten
questions in a different order on a different day — and question 4 of "G9-A"
would then mean two different things to two teachers holding the same paper.
"""

from __future__ import annotations

import re

from diagnostics.constants import OPTION_LETTERS
from diagnostics.models import SpeakingRubric

#: Every section is worth the same ten marks (spec 3.1): 40 total.
SECTION_MARKS = 10

LISTENING_TITLE = "Section 1: Listening"
READING_TITLE = "Section 2: Reading"
WRITING_TITLE = "Section 3: Writing"
SPEAKING_TITLE = "Section 4: Speaking"

LISTENING_INSTRUCTIONS = (
    "You will hear two recordings. Each recording is played twice. "
    "Circle your answer where choices are given; write on the line where "
    "they are not. There are 10 marks."
)
READING_INSTRUCTIONS = (
    "Read the passage, then answer the ten questions that follow. "
    "Circle your answer where choices are given; write on the line where "
    "they are not. There are 10 marks."
)
WRITING_INSTRUCTIONS = (
    "Circle the letter of the best option for each question. "
    "There are 10 marks."
)
SPEAKING_INSTRUCTIONS = (
    "The examiner will ask you the five tasks below in order. Use the "
    "prompts under each task to help you. There are 10 marks, 2 per task."
)

#: How many options share one printed line, by option count
#: (Design Revision 2, section 5.2). Four options split two and two; three
#: or fewer all fit on one line.
OPTIONS_PER_LINE = {2: 2, 3: 3, 4: 2}

#: Markers that mean a stem already carries its own gap. All 25 listening
#: gap-fill stems end with "______" because the extractor wrote them that
#: way - verified directly against the database (Design Revision 2,
#: section 5.4). Only the underscore-run pattern is kept: a direct query
#: confirmed zero real stems anywhere in the bank use an ellipsis run, a
#: dot run, or a numbered "(N)" reference as a gap marker. Matching on
#: those speculative patterns risks a worse failure than the one this
#: guards against - a stem that legitimately contains something like
#: "(1990)" would wrongly get no blank at all, leaving nowhere to write.
_EXISTING_GAP_RE = re.compile(r"_{3,}")

INLINE_BLANK = "_" * 12

#: One short instruction per reading subtype, printed once above its group
#: instead of a bracketed label after all ten stems (Design Revision 2,
#: section 5.6). Without this the removal of the answer line leaves a
#: student unable to tell a True/False item from an MCQ.
READING_GROUP_INSTRUCTIONS = {
    "true_false_ng": "Write TRUE, FALSE or NOT GIVEN on the line.",
    "mcq": "Circle the letter of the correct answer.",
    "completion": "Complete each sentence with a word from the passage.",
    "heading_matching": "Write the letter of the matching heading on the line.",
    "paragraph_matching": "Write the letter of the matching paragraph on the line.",
}


def docx_available() -> bool:
    """Mirrors assembly.export.docx_available: python-docx is optional."""
    try:
        import docx  # noqa: F401
    except ImportError:
        return False
    return True


def _lettered(options):
    """Pair options with A, B, C, D... Extra options beyond the known letters
    keep going with the next letter rather than being silently dropped."""
    pairs = []
    for index, option in enumerate(options):
        if index < len(OPTION_LETTERS):
            letter = OPTION_LETTERS[index]
        else:
            letter = chr(ord("A") + index)
        pairs.append((letter, option))
    return pairs


def lettered_options(question):
    """Public helper so renderers letter options the one agreed way."""
    return _lettered(question.options or [])


def option_rows(options):
    """Group lettered options into printed lines.

    Returns a list of lines, each a list of (letter, option) pairs, so the
    docx writer and the HTML template lay options out identically. A paper
    preview that differs from the printed paper is worse than no preview.
    """
    pairs = _lettered(options)
    if not pairs:
        return []
    per_line = OPTIONS_PER_LINE.get(len(pairs), 2)
    return [pairs[i:i + per_line] for i in range(0, len(pairs), per_line)]


def needs_inline_blank(stem, options):
    """Whether this question needs a ruled blank appended to its stem.

    The separate "Answer: ____" line is gone from every question (Design
    Revision 2, section 5.3) - students circle their choice. Questions with
    nothing to circle need somewhere to write instead, but only if the stem
    does not already contain its own gap.
    """
    if options:
        return False
    return not _EXISTING_GAP_RE.search(stem or "")


def _clip_section(clip):
    return {
        "number": clip.number,
        "intro": clip.intro_text,
        "audio": clip.audio_file,
        "questions": list(clip.questions.order_by("position")),
    }


def writing_questions_in_order(paper):
    return [
        slot.question
        for slot in paper.writing_slots.order_by("position").select_related("question")
    ]


def speaking_prompts_in_order(paper):
    return [
        slot.prompt
        for slot in paper.speaking_slots.order_by("position").select_related("prompt")
    ]


def paper_sections(paper):
    """Return the four sections of a paper, in order, as plain dicts."""
    rubrics = {rubric.task: rubric for rubric in SpeakingRubric.objects.all()}

    return [
        {
            "title": LISTENING_TITLE,
            "marks": SECTION_MARKS,
            "instructions": LISTENING_INSTRUCTIONS,
            "clips": [
                _clip_section(paper.listening_clip_1),
                _clip_section(paper.listening_clip_2),
            ],
        },
        {
            "title": READING_TITLE,
            "marks": SECTION_MARKS,
            "instructions": READING_INSTRUCTIONS,
            "passage": paper.reading_passage,
            "questions": list(paper.reading_passage.questions.order_by("position")),
        },
        {
            "title": WRITING_TITLE,
            "marks": SECTION_MARKS,
            "instructions": WRITING_INSTRUCTIONS,
            "questions": writing_questions_in_order(paper),
        },
        {
            "title": SPEAKING_TITLE,
            "marks": SECTION_MARKS,
            "instructions": SPEAKING_INSTRUCTIONS,
            "prompts": speaking_prompts_in_order(paper),
            "rubrics": rubrics,
        },
    ]


def reading_groups(questions):
    """Reading questions grouped into runs of the same subtype, in order.

    Returns [(subtype, instruction, [questions])]. Consecutive runs are kept
    separate rather than merged, so question numbering stays sequential down
    the page - a student following "questions 1-10" must never have to jump.
    """
    groups = []
    for question in questions:
        if groups and groups[-1][0] == question.subtype:
            groups[-1][2].append(question)
        else:
            groups.append((
                question.subtype,
                READING_GROUP_INSTRUCTIONS.get(question.subtype, ""),
                [question],
            ))
    return groups


def _with_alternatives(question):
    """The answer as a marker needs it: the key answer plus anything else
    that must be accepted, so a marker is never guessing whether a near-miss
    counts."""
    answer = question.answer
    extras = [
        alternative
        for alternative in (question.acceptable_answers or [])
        if alternative != answer
    ]
    if extras:
        return f"{answer}  (also accept: {', '.join(extras)})"
    return answer


def _writing_answer(question):
    """A bare letter is unmarkable if the options were reshuffled; print the
    letter and the text it points at."""
    letter = (question.answer or "").strip()
    for option_letter, option in _lettered(question.options or []):
        if option_letter.upper() == letter.upper():
            return f"{letter}) {option}"
    return letter


def _speaking_answer(prompt, rubrics):
    rubric = rubrics.get(prompt.task)
    if rubric:
        return f"{rubric.marks} marks — indicators: {rubric.indicators}"
    return (
        f"{prompt.marks} marks — no rubric on file for "
        f"{prompt.get_task_display()}; mark on fluency, accuracy and task "
        f"completion."
    )


def answer_key(paper):
    """Return [(section title, [(label, answer)])] for the marking sheet."""
    sections = paper_sections(paper)
    listening, reading, writing, speaking = sections

    listening_rows = []
    number = 1
    for clip in listening["clips"]:
        for question in clip["questions"]:
            listening_rows.append(
                (f"{number}. Clip {clip['number']} Q{question.position}",
                 _with_alternatives(question))
            )
            number += 1

    reading_rows = [
        (f"{question.position}.", _with_alternatives(question))
        for question in reading["questions"]
    ]

    writing_rows = [
        (f"{position}.", _writing_answer(question))
        for position, question in enumerate(writing["questions"], start=1)
    ]

    rubrics = speaking["rubrics"]
    speaking_rows = [
        (f"{position}. {prompt.get_task_display()}", _speaking_answer(prompt, rubrics))
        for position, prompt in enumerate(speaking["prompts"], start=1)
    ]

    return [
        (listening["title"], listening_rows),
        (reading["title"], reading_rows),
        (writing["title"], writing_rows),
        (speaking["title"], speaking_rows),
    ]
