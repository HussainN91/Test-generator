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

META_LINE = "CEFR B1 | 40 marks | 40 minutes"


def docx_available() -> bool:
    """Mirrors assembly.export.docx_available: python-docx is optional."""
    try:
        import docx  # noqa: F401
    except ImportError:
        return False
    return True


def _section_heading(document, section):
    document.add_heading(f"{section['title']} ({section['marks']} marks)", level=1)
    instructions = document.add_paragraph(section["instructions"])
    instructions.runs[0].italic = True


def _write_question(document, number, question):
    """One question: bold numbered stem, options in shared-line tables,
    and an inline blank only where there is nothing to circle. Shared by
    the listening, reading and writing writers; speaking has its own
    prompt/bullet format and does not use this."""
    stem = f"{number}. {question.stem}"
    if needs_inline_blank(question.stem, question.options):
        stem = f"{stem}  {INLINE_BLANK}"
    paragraph = document.add_paragraph()
    run = paragraph.add_run(stem)
    run.bold = True

    rows = option_rows(question.options or [])
    if not rows:
        return

    table = document.add_table(rows=len(rows), cols=max(len(line) for line in rows))
    table.style = "Table Grid"
    _remove_table_borders(table)
    for row_index, line in enumerate(rows):
        for cell_index, (letter, option) in enumerate(line):
            table.rows[row_index].cells[cell_index].text = f"{letter}) {option}"


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


def _write_listening(document, section):
    from docx.shared import Inches

    number = 1
    for clip in section["clips"]:
        document.add_heading(f"Recording {clip['number']}", level=2)
        if clip["intro"]:
            intro = document.add_paragraph(clip["intro"])
            intro.runs[0].italic = True

        for question in clip["questions"]:
            _write_question(document, number, question)
            if question.image:
                try:
                    path = question.image.path
                except (NotImplementedError, ValueError):
                    path = None
                if path and os.path.exists(path):
                    document.add_picture(path, width=Inches(6))
                else:
                    missing = document.add_paragraph(
                        f"    [image missing: {question.image.name}]"
                    )
                    missing.runs[0].italic = True
            number += 1


def _write_reading(document, section):
    passage = section["passage"]
    document.add_heading(f"{passage.label} — {passage.title}", level=2)
    document.add_paragraph(passage.body)

    for _subtype, instruction, questions in reading_groups(section["questions"]):
        if instruction:
            group_instruction = document.add_paragraph(instruction)
            group_instruction.runs[0].italic = True
        for question in questions:
            _write_question(document, question.position, question)


def _write_writing(document, section):
    for position, question in enumerate(section["questions"], start=1):
        _write_question(document, position, question)


def _write_speaking(document, section):
    for position, prompt in enumerate(section["prompts"], start=1):
        document.add_heading(
            f"Task {position}: {prompt.get_task_display()} "
            f"({prompt.marks} marks)",
            level=2,
        )
        document.add_paragraph(prompt.prompt)
        for bullet in prompt.bullets or []:
            document.add_paragraph(f"    • {bullet}")


def student_docx(paper):
    """The paper as a student sees it: four sections, no answers."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    document = Document()
    title = document.add_heading(
        f"Grade {paper.grade} Diagnostic Test — Variant {paper.variant}", level=0
    )
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta = document.add_paragraph(META_LINE)
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    document.add_paragraph(
        "Name: ______________________    Class: __________    Date: __________"
    )

    listening, reading, writing, speaking = paper_sections(paper)
    _section_heading(document, listening)
    _write_listening(document, listening)

    document.add_page_break()
    _section_heading(document, reading)
    _write_reading(document, reading)

    document.add_page_break()
    _section_heading(document, writing)
    _write_writing(document, writing)

    document.add_page_break()
    _section_heading(document, speaking)
    _write_speaking(document, speaking)

    return document


def answer_key_docx(paper):
    """Listening, Reading and Writing answers. Examiner copy — not handed out."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    document = Document()
    title = document.add_heading(
        f"Answer Key — Grade {paper.grade} Variant {paper.variant}", level=0
    )
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta = document.add_paragraph(META_LINE)
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    warning = document.add_paragraph(
        "Examiner copy — do not hand this out with the test."
    )
    warning.runs[0].italic = True

    for section_title, rows in answer_key(paper):
        document.add_heading(section_title, level=1)
        table = document.add_table(rows=len(rows), cols=2)
        table.style = "Table Grid"
        for index, (label, answer) in enumerate(rows):
            table.rows[index].cells[0].text = label
            table.rows[index].cells[1].text = str(answer)

    return document


def examiner_docx(paper):
    """The speaking section run sheet: prompts, rubric, and a mark sheet.

    Separate from answer_key_docx because it is handed to a different
    person doing a different job — conducting the speaking section face to
    face, not marking a script — and needs a place to write marks down.
    """
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    _listening, _reading, _writing, speaking = paper_sections(paper)

    document = Document()
    title = document.add_heading(
        f"Speaking Examiner Copy — Grade {paper.grade} Variant {paper.variant}",
        level=0,
    )
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta = document.add_paragraph("5 tasks, 2 marks each, 10 marks total")
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    document.add_paragraph(
        "Student: ______________________    Date: __________"
    )

    rubrics = speaking["rubrics"]
    for position, prompt in enumerate(speaking["prompts"], start=1):
        document.add_heading(
            f"Task {position}: {prompt.get_task_display()} ({prompt.marks} marks)",
            level=1,
        )
        document.add_paragraph(prompt.prompt)
        for bullet in prompt.bullets or []:
            document.add_paragraph(f"    • {bullet}")

        rubric = rubrics.get(prompt.task)
        document.add_paragraph("Marking indicators:").runs[0].bold = True
        document.add_paragraph(
            rubric.indicators if rubric else
            "No rubric on file for this task — mark on fluency, accuracy "
            "and task completion."
        )
        document.add_paragraph(f"Mark awarded (0–{prompt.marks}): ______")

    document.add_page_break()
    document.add_heading("Mark sheet", level=1)
    table = document.add_table(rows=len(speaking["prompts"]) + 1, cols=3)
    table.style = "Table Grid"
    header = table.rows[0].cells
    header[0].text, header[1].text, header[2].text = "Task", "Description", "Mark"
    for index, prompt in enumerate(speaking["prompts"], start=1):
        row = table.rows[index].cells
        row[0].text = f"{index}. {prompt.get_task_display()}"
        row[1].text = prompt.prompt
        row[2].text = f"     / {prompt.marks}"
    total_row = table.add_row().cells
    total_row[0].text = ""
    total_row[1].text = "Total"
    total_row[2].text = "     / 10"

    return document
