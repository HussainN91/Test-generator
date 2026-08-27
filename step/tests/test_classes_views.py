"""The classes/gradebook screens. GOV.UK one-thing-per-page, matching the
convention `step/tests/test_views.py` already pins for the obligation
screens: a teacher can never see or touch another teacher's classes.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from step import constants
from step.models import (
    AcademicYear, Educator, Obligation, ObligationType, ProgressEntry, Region, Student,
    TeachingClass,
)


class ClassListTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region, user=self.user)
        self.client.login(username="maria", password="pw")

    def test_requires_signing_in(self):
        self.client.logout()
        response = self.client.get(reverse("step:class_list"))
        self.assertEqual(response.status_code, 302)

    def test_shows_only_my_own_classes(self):
        TeachingClass.objects.create(educator=self.educator, grade=9, slot=1, display_name="9A")
        other = Educator.objects.create(full_name="John Cruz", region=self.region)
        TeachingClass.objects.create(educator=other, grade=9, slot=2, display_name="9B")

        response = self.client.get(reverse("step:class_list"))
        names = [c.display_name for c in response.context["classes"]]
        self.assertEqual(names, ["9A"])


class ClassCreateTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region, user=self.user)
        self.client.login(username="maria", password="pw")

    def test_the_typed_name_supplies_the_grade_and_the_class_pack(self):
        """A teacher types the name they already use; nothing else is asked."""
        response = self.client.post(reverse("step:class_create"), {"display_name": "9A"})
        teaching_class = TeachingClass.objects.get(display_name="9A")
        self.assertEqual(teaching_class.educator, self.educator)
        self.assertEqual(teaching_class.grade, 9)
        self.assertEqual(teaching_class.slot, 1)
        self.assertRedirects(response, reverse("step:class_detail", args=[teaching_class.pk]))

    def test_the_letter_decides_which_pack_is_renamed(self):
        self.client.post(reverse("step:class_create"), {"display_name": "11C"})
        teaching_class = TeachingClass.objects.get(display_name="11C")
        self.assertEqual((teaching_class.grade, teaching_class.slot), (11, 3))

    def test_lower_case_is_accepted_and_stored_the_way_it_was_shown(self):
        """The field renders upper-case and the live readout promises
        upper-case, so storing "10 b" verbatim would rename the diagnostics
        pack to something the teacher never saw."""
        self.client.post(reverse("step:class_create"), {"display_name": "10 b"})
        teaching_class = TeachingClass.objects.get(grade=10, slot=2)
        self.assertEqual(teaching_class.display_name, "10 B")

    def test_a_grade_outside_9_to_11_is_rejected(self):
        response = self.client.post(reverse("step:class_create"), {"display_name": "12A"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TeachingClass.objects.exists())

    def test_a_class_letter_past_the_last_pack_is_rejected(self):
        response = self.client.post(reverse("step:class_create"), {"display_name": "9E"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TeachingClass.objects.exists())

    def test_a_name_that_is_not_a_class_at_all_is_rejected(self):
        response = self.client.post(reverse("step:class_create"), {"display_name": "my class"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TeachingClass.objects.exists())

    def test_an_empty_name_is_rejected(self):
        response = self.client.post(reverse("step:class_create"), {"display_name": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TeachingClass.objects.exists())

    def test_a_pack_already_taken_is_rejected_with_a_plain_message(self):
        TeachingClass.objects.create(educator=self.educator, grade=9, slot=1, display_name="9A")
        response = self.client.post(reverse("step:class_create"), {"display_name": "9a"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(TeachingClass.objects.count(), 1)

    def test_the_form_offers_an_example_to_copy(self):
        response = self.client.get(reverse("step:class_create"))
        self.assertContains(response, "9A")
        self.assertContains(response, "9B")

    def test_the_form_no_longer_asks_the_teacher_to_pick_a_pack_number(self):
        """The radio lists this replaced made the teacher answer a question
        the name already answers."""
        response = self.client.get(reverse("step:class_create"))
        self.assertNotContains(response, 'name="slot"')
        self.assertNotContains(response, 'name="grade"')


class ClassNameParsingTests(TestCase):
    """The parser behind the single field, exercised directly - a teacher's
    typo must come back as an instruction, never as a rule name."""

    def test_a_letter_maps_to_its_pack_number(self):
        from step.classes_views import parse_class_name

        for text, expected in [("9A", (9, 1)), ("9B", (9, 2)), ("11D", (11, 4))]:
            grade, slot, error = parse_class_name(text)
            self.assertIsNone(error)
            self.assertEqual((grade, slot), expected)

    def test_a_pack_number_is_accepted_as_well_as_a_letter(self):
        from step.classes_views import parse_class_name

        self.assertEqual(parse_class_name("10-2")[:2], (10, 2))

    def test_every_rejection_reads_as_an_instruction(self):
        from step.classes_views import parse_class_name

        for text in ["", "hello", "12A", "9E", "9"]:
            error = parse_class_name(text)[2]
            self.assertTrue(error)
            self.assertNotIn("slot", error.lower())
            self.assertNotIn("regex", error.lower())


class ClassDetailTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region, user=self.user)
        self.teaching_class = TeachingClass.objects.create(
            educator=self.educator, grade=9, slot=1, display_name="9A"
        )
        self.client.login(username="maria", password="pw")

    def test_another_teachers_class_is_not_visible(self):
        other = Educator.objects.create(full_name="John Cruz", region=self.region)
        other_class = TeachingClass.objects.create(educator=other, grade=9, slot=2, display_name="9B")
        response = self.client.get(reverse("step:class_detail", args=[other_class.pk]))
        self.assertEqual(response.status_code, 404)

    def test_shows_the_roster(self):
        Student.objects.create(teaching_class=self.teaching_class, full_name="Aziz Karimov")
        response = self.client.get(reverse("step:class_detail", args=[self.teaching_class.pk]))
        self.assertContains(response, "Aziz Karimov")

    def test_shows_checkpoint_completion_state(self):
        student = Student.objects.create(teaching_class=self.teaching_class, full_name="Aziz Karimov")
        obligation_type = ObligationType.objects.create(
            name_template="Beginning-of-year diagnostic", category=constants.CATEGORY_ASSESSMENTS,
            cadence=constants.CADENCE_ANNUAL, evidence_spec=constants.EVIDENCE_NONE,
            form_slug=constants.FORM_SLUG_ASSESSMENT_CHECKPOINT,
        )
        Obligation.objects.create(
            type=obligation_type, educator=self.educator, teaching_class=self.teaching_class,
            period_kind=constants.PERIOD_YEAR, period_start=date(2025, 9, 1), due_date=date(2025, 10, 1),
        )
        response = self.client.get(reverse("step:class_detail", args=[self.teaching_class.pk]))
        checkpoints = {row["checkpoint"]: row for row in response.context["checkpoints"]}
        self.assertEqual(checkpoints[constants.CHECKPOINT_BOY]["done"], 0)
        self.assertEqual(checkpoints[constants.CHECKPOINT_BOY]["total"], 1)


class StudentCreateTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region, user=self.user)
        self.teaching_class = TeachingClass.objects.create(
            educator=self.educator, grade=9, slot=1, display_name="9A"
        )
        self.client.login(username="maria", password="pw")

    def test_adds_a_student_to_the_class(self):
        response = self.client.post(
            reverse("step:student_create", args=[self.teaching_class.pk]), {"full_name": "Aziz Karimov"}
        )
        self.assertTrue(Student.objects.filter(teaching_class=self.teaching_class, full_name="Aziz Karimov").exists())
        self.assertRedirects(response, reverse("step:class_detail", args=[self.teaching_class.pk]))

    def test_cannot_add_a_student_to_another_teachers_class(self):
        other = Educator.objects.create(full_name="John Cruz", region=self.region)
        other_class = TeachingClass.objects.create(educator=other, grade=9, slot=2, display_name="9B")
        response = self.client.post(
            reverse("step:student_create", args=[other_class.pk]), {"full_name": "Aziz Karimov"}
        )
        self.assertEqual(response.status_code, 404)


class StudentDetailTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region, user=self.user)
        self.teaching_class = TeachingClass.objects.create(
            educator=self.educator, grade=9, slot=1, display_name="9A"
        )
        self.student = Student.objects.create(teaching_class=self.teaching_class, full_name="Aziz Karimov")
        self.client.login(username="maria", password="pw")

    def test_shows_the_students_entries(self):
        ProgressEntry.objects.create(
            student=self.student, checkpoint=constants.CHECKPOINT_BOY, score=80,
            skill=constants.SKILL_READING, comment="Good pace.",
        )
        response = self.client.get(reverse("step:student_detail", args=[self.student.pk]))
        self.assertContains(response, "Good pace.")

    def test_another_teachers_student_is_not_visible(self):
        other = Educator.objects.create(full_name="John Cruz", region=self.region)
        other_class = TeachingClass.objects.create(educator=other, grade=9, slot=2, display_name="9B")
        other_student = Student.objects.create(teaching_class=other_class, full_name="Someone Else")
        response = self.client.get(reverse("step:student_detail", args=[other_student.pk]))
        self.assertEqual(response.status_code, 404)


class NoteCreateTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region, user=self.user)
        self.teaching_class = TeachingClass.objects.create(
            educator=self.educator, grade=9, slot=1, display_name="9A"
        )
        self.student = Student.objects.create(teaching_class=self.teaching_class, full_name="Aziz Karimov")
        self.client.login(username="maria", password="pw")

    def test_adds_a_freeform_note_with_no_checkpoint_and_no_score(self):
        self.client.post(
            reverse("step:note_create", args=[self.student.pk]),
            {"skill": constants.SKILL_WRITING, "comment": "Needs work on tenses."},
        )
        entry = ProgressEntry.objects.get(student=self.student)
        self.assertEqual(entry.checkpoint, "")
        self.assertIsNone(entry.score)
        self.assertEqual(entry.comment, "Needs work on tenses.")

    def test_a_note_may_repeat_freely(self):
        for _ in range(2):
            self.client.post(reverse("step:note_create", args=[self.student.pk]), {"comment": "A note."})
        self.assertEqual(ProgressEntry.objects.filter(student=self.student).count(), 2)

    def test_an_empty_note_is_rejected(self):
        self.client.post(reverse("step:note_create", args=[self.student.pk]), {"comment": "  "})
        self.assertEqual(ProgressEntry.objects.count(), 0)


class GradebookSheetTests(TestCase):
    """The class page IS the mark sheet.

    Marks used to be reachable only through an obligation on another screen,
    which meant the class page showed a roster and not a single grade. These
    pin the sheet: a month of per-skill marks, edited where they are read.
    """

    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(
            full_name="Maria Santos", region=self.region, user=self.user
        )
        self.teaching_class = TeachingClass.objects.create(
            educator=self.educator, grade=9, slot=1, display_name="9A"
        )
        self.student = Student.objects.create(
            teaching_class=self.teaching_class, full_name="Aziz Karimov"
        )
        self.year = AcademicYear.objects.create(
            label="2025-26", start=date(2025, 9, 1), end=date(2026, 5, 31), is_current=True
        )
        self.client.login(username="maria", password="pw")
        self.url = reverse("step:class_detail", args=[self.teaching_class.pk])

    def test_the_sheet_offers_every_month_of_the_academic_year(self):
        response = self.client.get(self.url)
        months = response.context["months"]
        self.assertEqual(months[0], date(2025, 9, 1))
        self.assertEqual(months[-1], date(2026, 5, 1))
        self.assertEqual(len(months), 9)

    def test_a_month_outside_the_academic_year_is_refused(self):
        self.assertEqual(self.client.get(self.url, {"month": "2030-01"}).status_code, 404)

    def test_a_malformed_month_is_refused(self):
        self.assertEqual(self.client.get(self.url, {"month": "banana"}).status_code, 404)

    def test_a_mark_is_saved_per_skill_for_the_open_month(self):
        self.client.post(
            self.url + "?month=2025-10",
            {
                "form": "monthly",
                "m_%s_reading" % self.student.pk: "72",
                "m_%s_writing" % self.student.pk: "65",
            },
        )
        reading = ProgressEntry.objects.get(
            student=self.student, period=date(2025, 10, 1), skill=constants.SKILL_READING
        )
        writing = ProgressEntry.objects.get(
            student=self.student, period=date(2025, 10, 1), skill=constants.SKILL_WRITING
        )
        self.assertEqual(reading.score, 72)
        self.assertEqual(writing.score, 65)
        self.assertEqual(reading.checkpoint, "")

    def test_the_same_skill_in_two_months_is_two_separate_marks(self):
        for month, score in (("2025-10", "70"), ("2025-11", "80")):
            self.client.post(
                self.url + "?month=" + month,
                {"form": "monthly", "m_%s_reading" % self.student.pk: score},
            )
        scores = sorted(
            ProgressEntry.objects.filter(
                student=self.student, skill=constants.SKILL_READING
            ).values_list("score", flat=True)
        )
        self.assertEqual(scores, [70, 80])

    def test_clearing_a_box_removes_the_mark_rather_than_storing_a_zero(self):
        """An empty cell and a recorded zero are different claims about a child."""
        self.client.post(
            self.url + "?month=2025-10",
            {"form": "monthly", "m_%s_reading" % self.student.pk: "72"},
        )
        self.client.post(
            self.url + "?month=2025-10",
            {"form": "monthly", "m_%s_reading" % self.student.pk: ""},
        )
        self.assertFalse(
            ProgressEntry.objects.filter(
                student=self.student, period=date(2025, 10, 1), skill=constants.SKILL_READING
            ).exists()
        )

    def test_a_score_above_100_is_refused_server_side(self):
        self.client.post(
            self.url + "?month=2025-10",
            {"form": "monthly", "m_%s_reading" % self.student.pk: "140"},
        )
        self.assertFalse(
            ProgressEntry.objects.filter(student=self.student, period=date(2025, 10, 1)).exists()
        )

    def test_a_non_numeric_score_is_refused(self):
        self.client.post(
            self.url + "?month=2025-10",
            {"form": "monthly", "m_%s_reading" % self.student.pk: "good"},
        )
        self.assertFalse(
            ProgressEntry.objects.filter(student=self.student, period=date(2025, 10, 1)).exists()
        )

    def test_the_average_is_shown_but_never_stored(self):
        self.client.post(
            self.url + "?month=2025-10",
            {
                "form": "monthly",
                "m_%s_reading" % self.student.pk: "70",
                "m_%s_writing" % self.student.pk: "80",
            },
        )
        response = self.client.get(self.url, {"month": "2025-10"})
        self.assertEqual(response.context["rows"][0]["average"], 75)
        self.assertFalse(
            ProgressEntry.objects.filter(student=self.student, score=75).exists()
        )

    def test_another_teachers_class_cannot_be_marked(self):
        other = Educator.objects.create(full_name="John Cruz", region=self.region)
        other_class = TeachingClass.objects.create(
            educator=other, grade=9, slot=2, display_name="9B"
        )
        theirs = Student.objects.create(teaching_class=other_class, full_name="Someone Else")
        response = self.client.post(
            reverse("step:class_detail", args=[other_class.pk]),
            {"form": "monthly", "m_%s_reading" % theirs.pk: "90"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(ProgressEntry.objects.filter(student=theirs).exists())


class CheckpointsOnTheSheetTests(TestCase):
    """The three programme checkpoints stay real obligations, but the teacher
    fills them in on the class page instead of being sent elsewhere."""

    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(
            full_name="Maria Santos", region=self.region, user=self.user
        )
        self.teaching_class = TeachingClass.objects.create(
            educator=self.educator, grade=9, slot=1, display_name="9A"
        )
        self.student = Student.objects.create(
            teaching_class=self.teaching_class, full_name="Aziz Karimov"
        )
        self.obligation_type = ObligationType.objects.create(
            name_template="Beginning-of-year diagnostic",
            category=constants.CATEGORY_ASSESSMENTS,
            cadence=constants.CADENCE_ANNUAL,
            evidence_spec=constants.EVIDENCE_NONE,
            form_slug=constants.FORM_SLUG_ASSESSMENT_CHECKPOINT,
        )
        self.obligation = Obligation.objects.create(
            type=self.obligation_type, educator=self.educator,
            teaching_class=self.teaching_class, period_kind=constants.PERIOD_YEAR,
            period_start=date(2025, 9, 1), due_date=date(2025, 10, 1),
        )
        self.client.login(username="maria", password="pw")
        self.url = reverse("step:class_detail", args=[self.teaching_class.pk])

    def test_a_checkpoint_mark_saves_from_the_class_page(self):
        self.client.post(
            self.url,
            {"form": "checkpoints", "c_%s_boy" % self.student.pk: "88"},
        )
        entry = ProgressEntry.objects.get(
            student=self.student, checkpoint=constants.CHECKPOINT_BOY
        )
        self.assertEqual(entry.score, 88)

    def test_scoring_every_student_settles_the_obligation_without_leaving_the_page(self):
        self.client.post(
            self.url,
            {"form": "checkpoints", "c_%s_boy" % self.student.pk: "88"},
        )
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_ACCEPTED)

    def test_a_blank_checkpoint_box_is_left_alone_rather_than_cleared(self):
        """Deleting here would silently un-settle an obligation staff may
        already have seen."""
        self.client.post(self.url, {"form": "checkpoints", "c_%s_boy" % self.student.pk: "88"})
        self.client.post(self.url, {"form": "checkpoints", "c_%s_boy" % self.student.pk: ""})
        self.assertTrue(
            ProgressEntry.objects.filter(
                student=self.student, checkpoint=constants.CHECKPOINT_BOY
            ).exists()
        )

    def test_a_checkpoint_score_out_of_range_is_refused(self):
        self.client.post(self.url, {"form": "checkpoints", "c_%s_boy" % self.student.pk: "101"})
        self.assertFalse(
            ProgressEntry.objects.filter(
                student=self.student, checkpoint=constants.CHECKPOINT_BOY
            ).exists()
        )

    def test_a_monthly_mark_does_not_satisfy_a_checkpoint(self):
        """The two live in the same table; they must not be confused for
        one another."""
        AcademicYear.objects.create(
            label="2025-26", start=date(2025, 9, 1), end=date(2026, 5, 31), is_current=True
        )
        self.client.post(
            self.url + "?month=2025-10",
            {"form": "monthly", "m_%s_reading" % self.student.pk: "95"},
        )
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_NOT_STARTED)


class StudentYearViewTests(TestCase):
    """One child's year, month by month - the question a flat feed of entries
    could not answer."""

    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(
            full_name="Maria Santos", region=self.region, user=self.user
        )
        self.teaching_class = TeachingClass.objects.create(
            educator=self.educator, grade=9, slot=1, display_name="9A"
        )
        self.student = Student.objects.create(
            teaching_class=self.teaching_class, full_name="Aziz Karimov"
        )
        AcademicYear.objects.create(
            label="2025-26", start=date(2025, 9, 1), end=date(2026, 5, 31), is_current=True
        )
        self.client.login(username="maria", password="pw")
        self.url = reverse("step:student_detail", args=[self.student.pk])

    def test_every_month_of_the_year_is_listed_even_when_unmarked(self):
        rows = self.client.get(self.url).context["month_rows"]
        self.assertEqual(len(rows), 9)
        self.assertFalse(rows[0]["marked"])

    def test_a_monthly_mark_lands_in_its_own_month(self):
        ProgressEntry.objects.create(
            student=self.student, period=date(2025, 11, 1),
            skill=constants.SKILL_READING, score=64,
        )
        rows = {row["month"]: row for row in self.client.get(self.url).context["month_rows"]}
        november = rows[date(2025, 11, 1)]
        self.assertTrue(november["marked"])
        self.assertEqual(november["average"], 64)
        self.assertFalse(rows[date(2025, 10, 1)]["marked"])

    def test_a_note_is_not_mistaken_for_a_mark(self):
        ProgressEntry.objects.create(
            student=self.student, comment="Needs to speak up more.",
            skill=constants.SKILL_SPEAKING,
        )
        context = self.client.get(self.url).context
        self.assertEqual(len(context["notes"]), 1)
        self.assertFalse(any(row["marked"] for row in context["month_rows"]))

    def test_a_checkpoint_comment_is_still_shown(self):
        """Checkpoint entries carry comments from the roster-scoring form;
        rendering only the score would silently drop them."""
        ProgressEntry.objects.create(
            student=self.student, checkpoint=constants.CHECKPOINT_BOY,
            score=80, comment="Good pace.",
        )
        self.assertContains(self.client.get(self.url), "Good pace.")
