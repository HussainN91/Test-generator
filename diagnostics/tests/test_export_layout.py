"""The student paper is held to four printed pages, one per section.

Word decides where a page actually breaks, and nothing in this test suite can
run Word. What these tests guard is everything that *feeds* that decision —
the page geometry, the paragraph spacing, the one-section-per-page breaks and
the two-up picture grid. Those are the settings the four-page budget was
measured against (all 48 papers, Word 2016, A4 at 100%); if one of them is
quietly reverted the budget is gone, and the next person to notice would be a
teacher holding a five-page test.

The measured result is recorded here rather than re-derived: with these
settings every one of the 48 papers came out at exactly 4 pages, and the
tightest of them (the listening page, which also carries the title and the
mark band) had about six spare lines. That is the headroom any future change
to this module is spending.
"""

from django.test import TestCase

from diagnostics.export import (
    BODY_PT,
    MARGIN_SIDE,
    MARGIN_TOP,
    MARK_BAND,
    MAX_STUDENT_PAGES,
    PICTURES_PER_ROW,
    PICTURE_WIDTH,
    student_docx,
)
from diagnostics.tests.test_rendering import RenderingTestCase


class PageGeometryTests(RenderingTestCase):
    def setUp(self):
        super().setUp()
        self.document = student_docx(self.paper)

    def test_margins_are_the_narrow_print_margins(self):
        """Word's 1in/1.25in default spends 3.5 of a page's 8.5 inches of
        width on nothing. Widening them back costs a page."""
        section = self.document.sections[0]
        self.assertAlmostEqual(section.left_margin.inches, MARGIN_SIDE, places=3)
        self.assertAlmostEqual(section.right_margin.inches, MARGIN_SIDE, places=3)
        self.assertAlmostEqual(section.top_margin.inches, MARGIN_TOP, places=3)

    def test_normal_style_carries_no_paragraph_spacing(self):
        """8pt under every paragraph, times ~120 paragraphs, is worth more
        than a page on its own."""
        normal = self.document.styles["Normal"]
        self.assertEqual(normal.paragraph_format.space_after.pt, 0)
        self.assertEqual(normal.paragraph_format.space_before.pt, 0)
        self.assertEqual(normal.paragraph_format.line_spacing, 1.0)

    def test_body_text_is_not_shrunk_to_make_the_budget(self):
        """The budget is met by geometry, not by making the test harder to
        read. 11pt is Word's own default — the size the paper already used."""
        self.assertEqual(BODY_PT, 11)
        self.assertEqual(self.document.styles["Normal"].font.size.pt, 11)

    def test_one_page_break_between_each_pair_of_sections(self):
        """Four sections, three breaks. The breaks are what make the budget
        checkable: a section that outgrows its page shows up as a fifth page
        rather than as a quietly reflowed paper."""
        breaks = sum(
            paragraph._p.xml.count('w:type="page"')
            for paragraph in self.document.paragraphs
        )
        self.assertEqual(breaks, MAX_STUDENT_PAGES - 1)


class MarkBandTests(RenderingTestCase):
    """Space at the top of the paper to enter L/S/R/W separately."""

    def setUp(self):
        super().setUp()
        self.document = student_docx(self.paper)
        self.band = self.document.tables[0]

    def test_the_band_is_the_first_thing_after_the_title(self):
        headings = [cell.text for cell in self.band.rows[0].cells]
        self.assertEqual(
            headings,
            ["Listening / 10", "Speaking / 10", "Reading / 10",
             "Writing / 10", "TOTAL / 40"],
        )

    def test_every_skill_has_its_own_empty_box_to_write_in(self):
        """The second row is the part a teacher writes in — if it ever comes
        back with content in it, there is nowhere left to put the mark."""
        self.assertEqual(len(self.band.rows), 2)
        self.assertEqual(len(self.band.rows[1].cells), len(MARK_BAND) + 1)
        for cell in self.band.rows[1].cells:
            self.assertEqual(cell.text.strip(), "")

    def test_the_band_totals_the_four_sections(self):
        self.assertEqual(sum(marks for _skill, marks in MARK_BAND), 40)


class PageNumberTests(RenderingTestCase):
    def test_the_footer_carries_a_page_of_pages_field(self):
        document = student_docx(self.paper)
        footer = document.sections[0].footer.paragraphs[0]
        xml = footer._p.xml
        self.assertIn("PAGE", xml)
        self.assertIn("NUMPAGES", xml)

    def test_the_footer_names_the_paper(self):
        """A loose page off the photocopier has to be identifiable as this
        grade's paper A and not that grade's."""
        document = student_docx(self.paper)
        footer = document.sections[0].footer.paragraphs[0]
        self.assertIn(f"G{self.paper.grade}-{self.paper.variant}", footer.text)


class PictureGridTests(RenderingTestCase):
    """Five option strips printed full-width is nine inches of picture — on
    its own more than the listening section is allowed. Measured: two-up at
    3.35in gives 4 pages; one per row gives 5 pages even at 4.5in, so the
    grid is what buys the fourth page, not the picture width."""

    def _give_every_picture_question_an_image(self):
        question_set = self.paper.listening_set_1
        for question in question_set.questions.all():
            question.image = "diagnostics/listening/clip-01-q1.jpg"
            question.save(update_fields=["image"])
        return question_set

    def test_pictures_print_two_to_a_row(self):
        self.assertEqual(PICTURES_PER_ROW, 2)

    def test_two_pictures_and_their_cell_padding_fit_the_printable_width(self):
        """A4 minus both margins, less Word's default 0.08in of padding on
        each side of each cell. Overflowing this makes Word silently reflow
        the grid, which is how a 4-page paper becomes a 5-page one."""
        printable = 8.27 - 2 * MARGIN_SIDE
        used = PICTURES_PER_ROW * PICTURE_WIDTH + PICTURES_PER_ROW * 0.16
        self.assertLess(used, printable)

    def test_a_picture_clip_is_laid_out_as_a_grid_not_as_stacked_questions(self):
        question_set = self._give_every_picture_question_an_image()
        document = student_docx(self.paper)
        stems = [question.stem for question in question_set.questions.order_by("position")]
        top_level = "\n".join(p.text for p in document.paragraphs)
        for stem in stems:
            self.assertNotIn(
                stem, top_level,
                "picture question printed full-width instead of in the grid",
            )

    def test_the_grid_still_numbers_the_questions_in_order(self):
        question_set = self._give_every_picture_question_an_image()
        document = student_docx(self.paper)
        cells = [
            cell.text
            for table in document.tables
            for row in table.rows
            for cell in row.cells
        ]
        for position, question in enumerate(question_set.questions.order_by("position"), 1):
            self.assertTrue(
                any(text.startswith(f"{position}. {question.stem}") for text in cells),
                f"question {position} is not numbered {position} in the grid",
            )

    def test_a_question_with_no_image_on_disk_still_gets_its_cell(self):
        """One missing file must not push the paper back to full-width
        layout, which would put it over budget."""
        question_set = self._give_every_picture_question_an_image()
        orphan = question_set.questions.order_by("position").last()
        orphan.image = "diagnostics/listening/does-not-exist.jpg"
        orphan.save(update_fields=["image"])

        document = student_docx(self.paper)
        cells = [
            cell.text
            for table in document.tables
            for row in table.rows
            for cell in row.cells
        ]
        self.assertTrue(any("image missing" in text for text in cells))
        self.assertNotIn(orphan.stem, "\n".join(p.text for p in document.paragraphs))


class NoLevelJargonTests(TestCase):
    def test_the_meta_line_does_not_mention_a_cefr_level(self):
        """The client asked for CEFR to come off everything a teacher or
        student sees (2026-08-26). It stays on content.Vocabulary, which is
        an internal cross-reference nobody outside the admin reads."""
        from diagnostics.export import META_LINE

        self.assertNotIn("CEFR", META_LINE)
        self.assertNotIn("B1", META_LINE)
        self.assertIn("40 marks", META_LINE)

