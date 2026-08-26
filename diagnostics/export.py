"""Build the files a teacher actually downloads for one paper (spec 3.6).

Three independent .docx documents — each served directly to the browser by
its own download view, with no bundling and no ZIP:

    G9-A-Student.docx      four sections, images inline, no answers
    G9-A-AnswerKey.docx    every section's answers, examiner copy
    G9-A-Examiner.docx     the 5 speaking prompts + rubric + a mark sheet

The two listening recordings download separately too (diagnostics/views.py
streams `AudioClip.audio_file` straight from disk); this module only builds
documents.

The document builders (`student_docx`, `answer_key_docx`, `examiner_docx`)
used to live inline in management/commands/render_paper.py, where only that
command could reach them. They live here now so a download view can call the
same code the command does — one implementation of "what a paper looks like
on paper", not two that could drift apart.

python-docx is optional, exactly as it is for assembly/export.py: if it is
not installed, `docx_available()` says so and callers decide what to do
about it (the command raises, a view 404s).

The student paper is held to four printed pages, one per section. That is a
budget, not an aspiration: `MAX_STUDENT_PAGES` records it and
`diagnostics/tests/test_export_layout.py` asserts every section still fits
inside its page. The budget is met by page geometry rather than by shrinking
anything a student has to read — body text stays at Word's default 11pt and
the picture options keep their aspect ratio. What pays for it is narrower
margins, the removal of Word's default 8pt gap under every single paragraph,
and printing the five picture questions two to a row instead of five stacked
full-width images.
"""

from __future__ import annotations

import os

from diagnostics.rendering import (
    INLINE_BLANK,
    answer_key,
    needs_inline_blank,
    option_rows,
    paper_sections,
    reading_groups,
)

META_LINE = "40 marks | 40 minutes"

#: One printed page per section (client requirement, 2026-08-26). Asserted,
#: not assumed — see the module docstring.
MAX_STUDENT_PAGES = 4

#: Point sizes. BODY_PT is Word's own default: the four-page budget is met
#: without making the test harder to read.
BODY_PT = 11
TITLE_PT = 15
SECTION_PT = 12.5
SUBHEAD_PT = 11.5
INSTRUCTION_PT = 9.5
BAND_PT = 8.5
FOOTER_PT = 8.5

#: Inches. Word defaults to 1in top/bottom and 1.25in left/right, which
#: spends 3.5 of a page's 8.5 inches of width on nothing.
MARGIN_TOP = 0.55
MARGIN_BOTTOM = 0.5
MARGIN_SIDE = 0.6

#: Two picture questions to a row inside the printable width. Each strip
#: holds the three lettered options, so this is the size of one option
#: picture times three — the floor below which the pictures stop being
#: readable at arm's length.
PICTURE_WIDTH = 3.35
PICTURES_PER_ROW = 2

#: The mark boxes at the top of page one, in the order the client named
#: them. Speaking is marked live by an examiner and the other three from
#: the script, but all four totals are entered in the same place.
MARK_BAND = (
    ("Listening", 10),
    ("Speaking", 10),
    ("Reading", 10),
    ("Writing", 10),
)


def docx_available() -> bool:
    """Mirrors assembly.export.docx_available: python-docx is optional."""
    try:
        import docx  # noqa: F401
    except ImportError:
        return False
    return True


# --------------------------------------------------------------- page setup


def _spaced(paragraph, before=0, after=0, size=BODY_PT, bold=False, italic=False):
    """Set one paragraph's spacing and run formatting.

    Every paragraph in these documents goes through here rather than through
    a named Word style. Word's built-in Normal and Heading styles carry
    generous space-before/space-after — 8pt under every paragraph, 12pt above
    every Heading 1 — and at the ~120 paragraphs a paper runs to, that
    invisible padding alone is worth more than a page.
    """
    from docx.shared import Pt

    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)
    fmt.line_spacing = 1.0
    for run in paragraph.runs:
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.italic = italic
    return paragraph


def _page_setup(document):
    """Margins and the Normal style, applied before anything is written."""
    from docx.shared import Inches, Pt

    for section in document.sections:
        section.top_margin = Inches(MARGIN_TOP)
        section.bottom_margin = Inches(MARGIN_BOTTOM)
        section.left_margin = Inches(MARGIN_SIDE)
        section.right_margin = Inches(MARGIN_SIDE)

    normal = document.styles["Normal"].paragraph_format
    normal.space_before = Pt(0)
    normal.space_after = Pt(0)
    normal.line_spacing = 1.0
    document.styles["Normal"].font.size = Pt(BODY_PT)


def _page_numbers(document, label):
    """"<paper>  Page N of M" centred in the footer of every page.

    python-docx has no API for page-number fields, so the PAGE and NUMPAGES
    fields are appended to the footer paragraph as raw `w:fldSimple`
    elements. Word evaluates them on open and on print; a reader that does
    not (some previewers) shows the field's cached result, which is why the
    surrounding words are literal text rather than part of the field.
    """
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    paragraph = document.sections[0].footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.add_run(f"{label}    Page ")
    for instruction, trailing in ((" PAGE ", " of "), (" NUMPAGES ", "")):
        field = OxmlElement("w:fldSimple")
        field.set(qn("w:instr"), instruction)
        paragraph._p.append(field)
        if trailing:
            paragraph.add_run(trailing)
    _spaced(paragraph, size=FOOTER_PT)


def _document(label):
    """A blank document already set up for print: margins, Normal, footer."""
    from docx import Document

    document = Document()
    _page_setup(document)
    _page_numbers(document, label)
    return document


def _cell(cell, text=None, size=BODY_PT, bold=False, centre=False):
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    if text is not None:
        cell.text = text
    for paragraph in cell.paragraphs:
        _spaced(paragraph, size=size, bold=bold)
        if centre:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    return cell


def _marks_band(document):
    """The L/S/R/W mark boxes at the top of page one.

    A ruled box per skill plus a total, so the four section marks can be
    entered separately instead of being totalled in the margin (client
    requirement, 2026-08-26). The second row is deliberately empty and
    padded — that space is what a teacher writes in.
    """
    from docx.shared import Pt

    table = document.add_table(rows=2, cols=len(MARK_BAND) + 1)
    table.style = "Table Grid"
    headings = [f"{skill} / {marks}" for skill, marks in MARK_BAND]
    headings.append(f"TOTAL / {sum(marks for _skill, marks in MARK_BAND)}")
    for index, heading in enumerate(headings):
        _cell(table.rows[0].cells[index], heading, size=BAND_PT,
              bold=True, centre=True)
    for cell in table.rows[1].cells:
        paragraph = cell.paragraphs[0]
        paragraph.paragraph_format.space_before = Pt(11)
        paragraph.paragraph_format.space_after = Pt(0)
    _spaced(document.add_paragraph(), size=4, after=2)
    return table


def _title_block(document, title, meta, identity=None, warning=None):
    """Centred title, the meta line under it, and an optional identity line."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    heading = document.add_paragraph()
    heading.add_run(title)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _spaced(heading, size=TITLE_PT, bold=True, after=1)

    line = document.add_paragraph(meta)
    line.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _spaced(line, size=INSTRUCTION_PT, after=4)

    if warning:
        _spaced(document.add_paragraph(warning), size=INSTRUCTION_PT,
                italic=True, after=4)
    if identity:
        _spaced(document.add_paragraph(identity), size=BODY_PT, after=4)


# ---------------------------------------------------------------- the paper


def _section_heading(document, section):
    heading = document.add_paragraph()
    heading.add_run(f"{section['title']} ({section['marks']} marks)")
    _spaced(heading, size=SECTION_PT, bold=True, before=2, after=1)
    _spaced(document.add_paragraph(section["instructions"]),
            size=INSTRUCTION_PT, italic=True, after=3)


def _subheading(document, text, before=4):
    heading = document.add_paragraph()
    heading.add_run(text)
    _spaced(heading, size=SUBHEAD_PT, bold=True, before=before, after=0)
    return heading


def _stem_text(number, question):
    stem = f"{number}. {question.stem}"
    if needs_inline_blank(question.stem, question.options):
        stem = f"{stem}  {INLINE_BLANK}"
    return stem


def _write_question(document, number, question):
    """One question: bold numbered stem, options in shared-line tables,
    and an inline blank only where there is nothing to circle. Shared by
    the listening, reading and writing writers; speaking has its own
    prompt/bullet format and does not use this."""
    paragraph = document.add_paragraph()
    paragraph.add_run(_stem_text(number, question))
    _spaced(paragraph, bold=True, before=2, after=0)
    _write_options(document, question)


def _write_options(document, question):
    rows = option_rows(question.options or [])
    if not rows:
        return

    table = document.add_table(rows=len(rows), cols=max(len(line) for line in rows))
    table.style = "Table Grid"
    _remove_table_borders(table)
    for row_index, line in enumerate(rows):
        for cell_index, (letter, option) in enumerate(line):
            _cell(table.rows[row_index].cells[cell_index], f"{letter}) {option}")


def _remove_table_borders(table):
    """python-docx has no borderless table style, so the borders are
    cleared on the table's XML directly. Without this the option grid
    prints as a visible grid of boxes rather than aligned columns."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "none")
        element.set(qn("w:sz"), "0")
        borders.append(element)
    table._tbl.tblPr.append(borders)


def _image_path(question):
    """The picture's path on disk, or None if there isn't one to print."""
    if not question.image:
        return None
    try:
        path = question.image.path
    except (NotImplementedError, ValueError):
        return None
    return path if os.path.exists(path) else None


def _write_picture_grid(document, questions, start):
    """Picture questions two to a row, stem above strip.

    Five option strips printed full-width down a page is nine inches of
    picture — on its own more than the whole listening section is allowed.
    Two to a row costs each strip a little width and buys back most of a
    page. A question with no picture on file still gets its cell, showing
    its options instead, so one missing file cannot push the paper over
    budget.
    """
    from docx.shared import Inches

    rows = [
        questions[index:index + PICTURES_PER_ROW]
        for index in range(0, len(questions), PICTURES_PER_ROW)
    ]
    table = document.add_table(rows=len(rows) * 2, cols=PICTURES_PER_ROW)
    _remove_table_borders(table)

    for row_index, line in enumerate(rows):
        for column, question in enumerate(line):
            number = start + row_index * PICTURES_PER_ROW + column
            _cell(table.rows[row_index * 2].cells[column],
                  _stem_text(number, question), size=INSTRUCTION_PT, bold=True)

            cell = table.rows[row_index * 2 + 1].cells[column]
            paragraph = cell.paragraphs[0]
            path = _image_path(question)
            if path:
                paragraph.add_run().add_picture(path, width=Inches(PICTURE_WIDTH))
                _spaced(paragraph, after=3)
            elif question.image:
                paragraph.add_run(f"[image missing: {question.image.name}]")
                _spaced(paragraph, size=INSTRUCTION_PT, italic=True, after=3)
            else:
                _spaced(paragraph, after=0)
                _write_cell_options(cell, question)


def _write_cell_options(cell, question):
    """Options inside a grid cell, one per line — there is no room for the
    two-across layout the full-width writer uses."""
    for line in option_rows(question.options or []):
        for letter, option in line:
            _spaced(cell.add_paragraph(f"{letter}) {option}"),
                    size=INSTRUCTION_PT, after=0)


def _write_listening(document, section):
    number = 1
    for clip in section["clips"]:
        _subheading(document, f"Recording {clip['number']}")
        if clip["intro"]:
            _spaced(document.add_paragraph(clip["intro"]),
                    size=INSTRUCTION_PT, italic=True, after=2)

        questions = clip["questions"]
        if any(question.image for question in questions):
            _write_picture_grid(document, questions, number)
            number += len(questions)
            continue

        for question in questions:
            _write_question(document, number, question)
            number += 1


def _write_reading(document, section):
    passage = section["passage"]
    _subheading(document, f"{passage.label} — {passage.title}", before=3)
    _spaced(document.add_paragraph(passage.body), after=3)

    for _subtype, instruction, questions in reading_groups(section["questions"]):
        if instruction:
            _spaced(document.add_paragraph(instruction),
                    size=INSTRUCTION_PT, italic=True, before=3, after=1)
        for question in questions:
            _write_question(document, question.position, question)


def _write_writing(document, section):
    for position, question in enumerate(section["questions"], start=1):
        _write_question(document, position, question)


def _write_speaking(document, section):
    for position, prompt in enumerate(section["prompts"], start=1):
        _subheading(
            document,
            f"Task {position}: {prompt.get_task_display()} "
            f"({prompt.marks} marks)",
        )
        _spaced(document.add_paragraph(prompt.prompt), after=0)
        for bullet in prompt.bullets or []:
            _spaced(document.add_paragraph(f"    • {bullet}"),
                    size=INSTRUCTION_PT, after=0)


def student_docx(paper):
    """The paper as a student sees it: four sections, no answers.

    One section to a page, four pages. The page breaks are what makes the
    budget checkable — a section that outgrows its page shows up as a fifth
    page rather than as a quietly reflowed paper nobody notices until it is
    printed forty-eight times.
    """
    document = _document(f"G{paper.grade}-{paper.variant}")
    _title_block(
        document,
        f"Grade {paper.grade} Diagnostic Test — Paper {paper.variant}",
        META_LINE,
        identity=(
            "Name: ____________________________    "
            "Class: ____________    Date: ____________"
        ),
    )
    _marks_band(document)

    sections = paper_sections(paper)
    writers = (_write_listening, _write_reading, _write_writing, _write_speaking)
    for index, (section, writer) in enumerate(zip(sections, writers)):
        if index:
            document.add_page_break()
        _section_heading(document, section)
        writer(document, section)

    return document


def answer_key_docx(paper):
    """Listening, Reading and Writing answers. Examiner copy — not handed out."""
    document = _document(f"G{paper.grade}-{paper.variant} Answer Key")
    _title_block(
        document,
        f"Answer Key — Grade {paper.grade} Paper {paper.variant}",
        META_LINE,
        warning="Examiner copy — do not hand this out with the test.",
    )

    for section_title, rows in answer_key(paper):
        heading = document.add_paragraph()
        heading.add_run(section_title)
        _spaced(heading, size=SECTION_PT, bold=True, before=6, after=2)

        table = document.add_table(rows=len(rows), cols=2)
        table.style = "Table Grid"
        for index, (label, answer) in enumerate(rows):
            _cell(table.rows[index].cells[0], label)
            _cell(table.rows[index].cells[1], str(answer))

    return document


def examiner_docx(paper):
    """The speaking section run sheet: prompts, rubric, and a mark sheet.

    Separate from answer_key_docx because it is handed to a different
    person doing a different job — conducting the speaking section face to
    face, not marking a script — and needs a place to write marks down.
    """
    _listening, _reading, _writing, speaking = paper_sections(paper)

    document = _document(f"G{paper.grade}-{paper.variant} Speaking")
    _title_block(
        document,
        f"Speaking Examiner Copy — Grade {paper.grade} Paper {paper.variant}",
        "5 tasks, 2 marks each, 10 marks total",
        identity="Student: ______________________    Date: __________",
    )

    rubrics = speaking["rubrics"]
    for position, prompt in enumerate(speaking["prompts"], start=1):
        _subheading(
            document,
            f"Task {position}: {prompt.get_task_display()} ({prompt.marks} marks)",
            before=6,
        )
        _spaced(document.add_paragraph(prompt.prompt), after=0)
        for bullet in prompt.bullets or []:
            _spaced(document.add_paragraph(f"    • {bullet}"),
                    size=INSTRUCTION_PT, after=0)

        rubric = rubrics.get(prompt.task)
        _spaced(document.add_paragraph("Marking indicators:"),
                size=INSTRUCTION_PT, bold=True, before=3, after=0)
        _spaced(
            document.add_paragraph(
                rubric.indicators if rubric else
                "No rubric on file for this task — mark on fluency, accuracy "
                "and task completion."
            ),
            size=INSTRUCTION_PT, after=0,
        )
        _spaced(document.add_paragraph(f"Mark awarded (0–{prompt.marks}): ______"),
                before=2, after=0)

    document.add_page_break()
    heading = document.add_paragraph()
    heading.add_run("Mark sheet")
    _spaced(heading, size=SECTION_PT, bold=True, after=2)

    table = document.add_table(rows=len(speaking["prompts"]) + 1, cols=3)
    table.style = "Table Grid"
    for index, label in enumerate(("Task", "Description", "Mark")):
        _cell(table.rows[0].cells[index], label, bold=True)
    for index, prompt in enumerate(speaking["prompts"], start=1):
        row = table.rows[index].cells
        _cell(row[0], f"{index}. {prompt.get_task_display()}")
        _cell(row[1], prompt.prompt)
        _cell(row[2], f"     / {prompt.marks}")
    total_row = table.add_row().cells
    _cell(total_row[0], "")
    _cell(total_row[1], "Total", bold=True)
    _cell(total_row[2], "     / 10", bold=True)

    return document
