"""Export a batch as .docx (spec 3.6).

python-docx is optional: if it is not installed the app still works and the
printable HTML view covers the same ground through the browser's print dialog.
Every export writes the tests first, then the answer keys, so a teacher can
print the pack and keep the last pages.
"""

from __future__ import annotations

import io

from bank.presentation import render_variant


def docx_available() -> bool:
    try:
        import docx  # noqa: F401
    except ImportError:
        return False
    return True


def batch_to_docx(batch) -> io.BytesIO:
    """Render every variant plus its answer key into a single Word document."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    document = Document()
    units = ", ".join(str(unit.number) for unit in batch.units.all())

    variants = list(batch.variants.prefetch_related("questions__item").all())

    for index, variant in enumerate(variants):
        if index:
            document.add_page_break()
        _write_test(document, batch, variant, units, WD_ALIGN_PARAGRAPH, Pt)

    document.add_page_break()
    heading = document.add_heading("Answer keys", level=1)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER

    for variant in variants:
        document.add_heading(f"Test {variant.label}", level=2)
        for position, question in render_variant(variant):
            document.add_paragraph(f"{position}. {question.answer}")

    stream = io.BytesIO()
    document.save(stream)
    stream.seek(0)
    return stream


def _write_test(document, batch, variant, units, alignment, Pt) -> None:
    title = document.add_heading(
        f"Grade {batch.grade.number} — English Test {variant.label}", level=1
    )
    title.alignment = alignment.CENTER

    meta = document.add_paragraph(f"Units: {units}    Name: ______________________    Date: __________")
    meta.alignment = alignment.CENTER
    for run in meta.runs:
        run.font.size = Pt(9)

    last_instruction = None
    for position, question in render_variant(variant):
        if question.instruction and question.instruction != last_instruction:
            instruction = document.add_paragraph(question.instruction)
            instruction.runs[0].italic = True
            last_instruction = question.instruction

        if question.pairs:
            document.add_paragraph(f"{position}.")
            table = document.add_table(rows=len(question.pairs), cols=2)
            table.style = "Table Grid"
            for row_index, row in enumerate(question.matching_rows):
                table.rows[row_index].cells[0].text = f"{row['number']}. {row['left']}"
                table.rows[row_index].cells[1].text = f"{row['letter']}. {row['right']}"
            document.add_paragraph(
                "Answers: " + "  ".join(f"{row['number']}. ____" for row in question.matching_rows)
            )
            continue

        document.add_paragraph(f"{position}. {question.prompt}")
        if question.options:
            for letter, option in question.lettered_options:
                document.add_paragraph(f"    {letter}. {option}")
        else:
            for _ in range(question.answer_lines):
                document.add_paragraph("    " + "_" * 60)
