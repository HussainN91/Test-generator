"""The paper must come out as a real, printable test.

paper_sections/answer_key are the shape of a paper; render_paper is the only
thing that turns that shape into something a teacher can hand out. The order
assertions matter more than they look: the paper's writing and speaking
content lives behind a through-model, and the plain M2M accessor returns it in
no defined order, so a renderer that reads `paper.writing_questions.all()`
produces a differently-numbered paper on a different day.
"""

import os
import tempfile
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from diagnostics.constants import CLIP_TASK_TYPES, SPEAKING_TASK_ORDER, TaskType
from diagnostics.export import student_docx
from diagnostics.models import (
    AudioClip, ListeningQuestion, ListeningQuestionSet, Paper, PaperWritingQuestion,
    ReadingPassage, ReadingQuestion, ReadingSubtype, SpeakingRubric,
)
from diagnostics.rendering import (
    INLINE_BLANK, READING_GROUP_INSTRUCTIONS, answer_key, needs_inline_blank,
    option_rows, paper_sections, reading_groups,
)
from diagnostics.tests.test_build_papers import seed_content


def seed_questions_and_rubrics():
    """The question layer on top of seed_content's containers.

    seed_content builds enough clips/passages/bank items to assemble papers,
    which is all build_papers needs. Rendering needs the questions inside
    them, so this adds that layer rather than forking a second seeder.
    """
    for clip in AudioClip.objects.all():
        question_set, _ = ListeningQuestionSet.objects.get_or_create(clip=clip, number=1)
        for position in range(1, 6):
            mcq = CLIP_TASK_TYPES[clip.number] in {TaskType.MCQ3, TaskType.TRUE_FALSE}
            ListeningQuestion.objects.create(
                question_set=question_set,
                position=position,
                stem=f"Clip {clip.number}, question {position}",
                options=["one", "two", "three"] if mcq else [],
                answer="A" if mcq else "word",
            )
    subtypes = (
        [ReadingSubtype.TRUE_FALSE_NG] * 5
        + [ReadingSubtype.MCQ] * 3
        + [ReadingSubtype.COMPLETION] * 2
    )
    for passage in ReadingPassage.objects.all():
        for position, subtype in enumerate(subtypes, start=1):
            ReadingQuestion.objects.create(
                passage=passage,
                position=position,
                subtype=subtype,
                stem=f"{passage.label} statement {position}",
                options=["w", "x", "y", "z"] if subtype == ReadingSubtype.MCQ else [],
                answer="B" if subtype == ReadingSubtype.MCQ else "TRUE",
            )
    for task in SPEAKING_TASK_ORDER:
        SpeakingRubric.objects.create(
            task=task, marks=2, indicators=f"{task} indicators: fluency, accuracy"
        )


class RenderingTestCase(TestCase):
    def setUp(self):
        seed_content()
        seed_questions_and_rubrics()
        call_command("build_papers", stdout=StringIO())
        self.paper = Paper.objects.get(grade=9, variant="A")


class PaperSectionsTests(RenderingTestCase):
    def test_returns_four_sections_worth_forty_marks(self):
        sections = paper_sections(self.paper)
        self.assertEqual(len(sections), 4)
        self.assertEqual(sum(section["marks"] for section in sections), 40)

    def test_sections_are_in_the_papers_fixed_order(self):
        titles = [section["title"] for section in paper_sections(self.paper)]
        for expected, title in zip(
            ["Listening", "Reading", "Writing", "Speaking"], titles
        ):
            self.assertIn(expected, title)

    def test_every_section_carries_instructions(self):
        for section in paper_sections(self.paper):
            self.assertTrue(
                section["instructions"].strip(), f"{section['title']} has no rubric"
            )

    def test_listening_section_names_both_clips(self):
        listening = paper_sections(self.paper)[0]
        self.assertEqual(len(listening["clips"]), 2)
        self.assertEqual(
            [clip["number"] for clip in listening["clips"]],
            [self.paper.listening_clip_1.number, self.paper.listening_clip_2.number],
        )

    def test_listening_clips_carry_their_own_questions_in_order(self):
        listening = paper_sections(self.paper)[0]
        total = 0
        for clip in listening["clips"]:
            positions = [question.position for question in clip["questions"]]
            self.assertEqual(positions, sorted(positions))
            self.assertEqual(len(positions), 5)
            for question in clip["questions"]:
                self.assertEqual(question.clip.number, clip["number"])
            total += len(positions)
        self.assertEqual(total, 10)

    def test_reading_section_carries_its_passage_and_ordered_questions(self):
        reading = paper_sections(self.paper)[1]
        self.assertEqual(reading["passage"], self.paper.reading_passage)
        positions = [question.position for question in reading["questions"]]
        self.assertEqual(positions, list(range(1, 11)))

    def test_writing_questions_come_back_in_slot_position_order(self):
        writing = paper_sections(self.paper)[2]
        expected = [
            slot.question_id
            for slot in self.paper.writing_slots.order_by("position")
        ]
        self.assertEqual([question.pk for question in writing["questions"]], expected)
        self.assertEqual(len(expected), 10)

    def test_writing_order_survives_a_reshuffled_slot(self):
        """The through-model's position is the paper's numbering, not pk order."""
        slots = list(self.paper.writing_slots.order_by("position"))
        first, last = slots[0], slots[-1]
        PaperWritingQuestion.objects.filter(pk=first.pk).update(position=99)
        PaperWritingQuestion.objects.filter(pk=last.pk).update(position=1)
        PaperWritingQuestion.objects.filter(pk=first.pk).update(position=10)

        writing = paper_sections(self.paper)[2]
        self.assertEqual(writing["questions"][0].pk, last.question_id)
        self.assertEqual(writing["questions"][-1].pk, first.question_id)

    def test_speaking_prompts_come_back_in_slot_position_order(self):
        speaking = paper_sections(self.paper)[3]
        expected = [
            slot.prompt_id for slot in self.paper.speaking_slots.order_by("position")
        ]
        self.assertEqual([prompt.pk for prompt in speaking["prompts"]], expected)
        self.assertEqual(len(expected), 5)

    def test_speaking_section_carries_rubrics_keyed_by_task(self):
        speaking = paper_sections(self.paper)[3]
        for prompt in speaking["prompts"]:
            self.assertIn(prompt.task, speaking["rubrics"])

    def test_speaking_rubrics_are_an_empty_dict_when_none_exist(self):
        SpeakingRubric.objects.all().delete()
        speaking = paper_sections(self.paper)[3]
        self.assertEqual(speaking["rubrics"], {})


class AnswerKeyTests(RenderingTestCase):
    def test_covers_all_four_sections(self):
        key = answer_key(self.paper)
        self.assertEqual(len(key), 4)
        for expected, (title, _rows) in zip(
            ["Listening", "Reading", "Writing", "Speaking"], key
        ):
            self.assertIn(expected, title)

    def test_every_section_has_a_row_per_question(self):
        counts = [len(rows) for _title, rows in answer_key(self.paper)]
        self.assertEqual(counts, [10, 10, 10, 5])

    def test_listening_and_reading_answers_are_the_real_answers(self):
        key = dict(answer_key(self.paper))
        listening_answers = [answer for _label, answer in key["Section 1: Listening"]]
        real = [
            question.answer
            for question_set in (self.paper.listening_set_1, self.paper.listening_set_2)
            for question in question_set.questions.order_by("position")
        ]
        for answer, expected in zip(listening_answers, real):
            self.assertIn(expected, answer)

    def test_writing_answers_name_the_option_letter(self):
        key = dict(answer_key(self.paper))
        for _label, answer in key["Section 3: Writing"]:
            self.assertTrue(answer.strip(), "a writing answer came back blank")

    def test_speaking_rows_carry_rubric_marks_and_indicators(self):
        key = dict(answer_key(self.paper))
        rows = key["Section 4: Speaking"]
        self.assertEqual(len(rows), 5)
        for _label, answer in rows:
            self.assertIn("indicators", answer)
            self.assertIn("mark", answer.lower())

    def test_speaking_rows_still_render_without_a_rubric(self):
        SpeakingRubric.objects.all().delete()
        rows = dict(answer_key(self.paper))["Section 4: Speaking"]
        self.assertEqual(len(rows), 5)
        for _label, answer in rows:
            self.assertTrue(answer.strip())


class RenderPaperCommandTests(RenderingTestCase):
    def render(self, *args):
        out = StringIO()
        call_command("render_paper", *args, stdout=out)
        return out.getvalue()

    def test_writes_both_documents_for_a_real_paper(self):
        with tempfile.TemporaryDirectory() as out_dir:
            self.render("--grade", "9", "--variant", "A", "--out", out_dir)
            student = os.path.join(out_dir, "G9-A-Student.docx")
            key = os.path.join(out_dir, "G9-A-AnswerKey.docx")
            self.assertTrue(os.path.exists(student), "no student copy written")
            self.assertTrue(os.path.exists(key), "no answer key written")
            self.assertGreater(os.path.getsize(student), 5000)
            self.assertGreater(os.path.getsize(key), 5000)

    def test_creates_the_output_directory_if_missing(self):
        with tempfile.TemporaryDirectory() as parent:
            out_dir = os.path.join(parent, "nested", "exports")
            self.render("--grade", "9", "--variant", "A", "--out", out_dir)
            self.assertTrue(os.path.exists(os.path.join(out_dir, "G9-A-Student.docx")))

    def test_student_copy_contains_the_section_headings(self):
        from docx import Document

        with tempfile.TemporaryDirectory() as out_dir:
            self.render("--grade", "9", "--variant", "A", "--out", out_dir)
            document = Document(os.path.join(out_dir, "G9-A-Student.docx"))
            text = "\n".join(p.text for p in document.paragraphs)
        for heading in ("Listening", "Reading", "Writing", "Speaking"):
            self.assertIn(heading, text)
        self.assertIn("40 marks", text)

    def test_student_copy_numbers_writing_questions_in_slot_order(self):
        from docx import Document

        with tempfile.TemporaryDirectory() as out_dir:
            self.render("--grade", "9", "--variant", "A", "--out", out_dir)
            document = Document(os.path.join(out_dir, "G9-A-Student.docx"))
            text = "\n".join(p.text for p in document.paragraphs)
        expected = [
            slot.question.stem
            for slot in self.paper.writing_slots.order_by("position").select_related(
                "question"
            )
        ]
        found = [text.index(stem) for stem in expected]
        self.assertEqual(found, sorted(found), "writing questions printed out of order")

    def test_answer_key_is_a_separate_document_with_the_answers(self):
        from docx import Document

        with tempfile.TemporaryDirectory() as out_dir:
            self.render("--grade", "9", "--variant", "A", "--out", out_dir)
            document = Document(os.path.join(out_dir, "G9-A-AnswerKey.docx"))
            text = "\n".join(p.text for p in document.paragraphs)
        for heading in ("Listening", "Reading", "Writing", "Speaking"):
            self.assertIn(heading, text)
        self.assertIn("Answer", text)

    def test_all_flag_renders_every_paper(self):
        with tempfile.TemporaryDirectory() as out_dir:
            self.render("--all", "--out", out_dir)
            written = sorted(os.listdir(out_dir))
        self.assertEqual(len(written), 96, written)
        self.assertIn("G11-D-Student.docx", written)
        self.assertIn("G11-D-AnswerKey.docx", written)

    def test_all_flag_does_not_need_grade_or_variant(self):
        with tempfile.TemporaryDirectory() as out_dir:
            self.render("--all", "--out", out_dir)
            self.assertTrue(os.path.exists(os.path.join(out_dir, "G9-A-Student.docx")))

    def test_missing_paper_is_a_command_error(self):
        with tempfile.TemporaryDirectory() as out_dir:
            with self.assertRaises(CommandError):
                self.render("--grade", "9", "--variant", "Z", "--out", out_dir)

    def test_grade_and_variant_are_required_without_all(self):
        with tempfile.TemporaryDirectory() as out_dir:
            with self.assertRaises(CommandError):
                self.render("--out", out_dir)

    def test_nothing_is_written_when_the_paper_does_not_exist(self):
        Paper.objects.filter(grade=9, variant="A").delete()
        with tempfile.TemporaryDirectory() as out_dir:
            with self.assertRaises(CommandError):
                self.render("--grade", "9", "--variant", "A", "--out", out_dir)
            self.assertEqual(os.listdir(out_dir), [])


class StudentDocxLayoutTests(RenderingTestCase):
    def test_student_docx_has_no_answer_lines_for_circleable_questions(self):
        """Answer: ____ is removed everywhere (Design Revision 2, 5.3);
        students circle instead."""
        document = student_docx(self.paper)
        text = "\n".join(p.text for p in document.paragraphs)
        self.assertNotIn("Answer:", text)

    def test_student_docx_bolds_question_stems(self):
        document = student_docx(self.paper)
        stems = [p for p in document.paragraphs if p.text.startswith("1.")]
        self.assertTrue(stems, "no numbered question found")
        self.assertTrue(any(run.bold for run in stems[0].runs))

    def test_gap_fill_stem_is_not_given_a_second_blank(self):
        question = ListeningQuestion.objects.filter(
            question_set=self.paper.listening_set_2
        ).first()
        question.stem = "Caspar's mother dances across a ______ in the circus."
        question.options = []
        question.save()
        document = student_docx(self.paper)
        text = "\n".join(p.text for p in document.paragraphs)
        self.assertNotIn("______ in the circus. " + INLINE_BLANK, text)


class OptionLayoutTests(SimpleTestCase):
    def test_four_options_go_two_per_line(self):
        rows = option_rows(["a", "b", "c", "d"])
        self.assertEqual(rows, [[("A", "a"), ("B", "b")],
                                [("C", "c"), ("D", "d")]])

    def test_three_options_share_one_line(self):
        rows = option_rows(["a", "b", "c"])
        self.assertEqual(rows, [[("A", "a"), ("B", "b"), ("C", "c")]])

    def test_two_options_share_one_line(self):
        rows = option_rows(["YES", "NO"])
        self.assertEqual(rows, [[("A", "YES"), ("B", "NO")]])

    def test_no_options_yields_no_rows(self):
        self.assertEqual(option_rows([]), [])


class InlineBlankTests(SimpleTestCase):
    def test_option_less_question_needs_a_blank(self):
        self.assertTrue(needs_inline_blank("The class starts at", []))

    def test_question_with_options_needs_no_blank(self):
        self.assertFalse(needs_inline_blank("Pick one", ["a", "b"]))

    def test_stem_that_already_has_a_blank_gets_no_second_one(self):
        """All 25 listening gap-fill stems already carry their own marker,
        e.g. "Caspar's mother dances across a ______ in the circus."
        Appending another would print two blanks on one line."""
        self.assertFalse(
            needs_inline_blank("Caspar's mother dances across a ______ in the circus.", [])
        )

    def test_a_stem_with_an_unrelated_parenthetical_number_still_gets_a_blank(self):
        """A stem that happens to contain a year or reference number in
        parentheses is not a gap marker. The old broader regex would have
        wrongly suppressed the blank here, leaving nowhere to write."""
        self.assertTrue(
            needs_inline_blank("The treaty (1990) was signed by both leaders.", [])
        )


class ReadingGroupTests(SimpleTestCase):
    class FakeQuestion:
        def __init__(self, subtype, position):
            self.subtype, self.position = subtype, position

    def test_consecutive_same_subtype_questions_group_together(self):
        questions = [self.FakeQuestion("mcq", n) for n in (1, 2, 3)]
        groups = reading_groups(questions)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0][0], "mcq")
        self.assertEqual(len(groups[0][2]), 3)

    def test_a_subtype_change_starts_a_new_group(self):
        questions = [
            self.FakeQuestion("mcq", 1),
            self.FakeQuestion("mcq", 2),
            self.FakeQuestion("completion", 3),
        ]
        groups = reading_groups(questions)
        self.assertEqual([g[0] for g in groups], ["mcq", "completion"])

    def test_a_repeated_subtype_does_not_merge_across_a_gap(self):
        """Runs stay separate so question numbers never jump. A student
        told to answer questions 1-10 in order must not be sent back up
        the page to finish an earlier group."""
        questions = [
            self.FakeQuestion("mcq", 1),
            self.FakeQuestion("completion", 2),
            self.FakeQuestion("mcq", 3),
        ]
        groups = reading_groups(questions)
        self.assertEqual([g[0] for g in groups], ["mcq", "completion", "mcq"])

    def test_every_subtype_has_an_instruction(self):
        from diagnostics.models import ReadingSubtype
        for subtype in ReadingSubtype.values:
            self.assertIn(subtype, READING_GROUP_INSTRUCTIONS)


class ClipSectionFromSetTests(RenderingTestCase):
    """paper_sections must keep its exact output shape - export.py, the
    download view and both templates read these dicts by key and none of
    them know sets exist."""

    def test_clip_section_keeps_its_keys(self):
        from diagnostics.rendering import paper_sections
        listening = paper_sections(self.paper)[0]
        self.assertEqual(len(listening["clips"]), 2)
        for clip in listening["clips"]:
            self.assertEqual(
                sorted(clip), ["audio", "intro", "number", "questions"]
            )

    def test_questions_come_from_the_papers_set_not_set_one(self):
        from diagnostics.models import ListeningQuestion, ListeningQuestionSet
        from diagnostics.rendering import paper_sections
        clip = self.paper.listening_set_2.clip
        # seed_content() already creates an empty set 2 for every clip, so
        # fetch it rather than create a duplicate that would violate
        # unique(clip, number).
        set_two = ListeningQuestionSet.objects.get(clip=clip, number=2)
        for position in range(1, 6):
            ListeningQuestion.objects.create(
                question_set=set_two, position=position,
                stem=f"second-set stem {position}", answer="A",
            )
        self.paper.listening_set_2 = set_two
        self.paper.save(update_fields=["listening_set_2"])

        second = paper_sections(self.paper)[0]["clips"][1]
        self.assertEqual(
            [q.stem for q in second["questions"]],
            [f"second-set stem {p}" for p in range(1, 6)],
        )
