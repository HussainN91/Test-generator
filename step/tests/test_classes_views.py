"""The classes/gradebook screens. GOV.UK one-thing-per-page, matching the
convention `step/tests/test_views.py` already pins for the obligation
screens: a teacher can never see or touch another teacher's classes.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from step import constants
from step.models import Educator, Obligation, ObligationType, ProgressEntry, Region, Student, TeachingClass


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

    def test_creates_a_class_owned_by_the_signed_in_teacher(self):
        response = self.client.post(
            reverse("step:class_create"), {"grade": "9", "slot": "1", "display_name": "9A"}
        )
        teaching_class = TeachingClass.objects.get(display_name="9A")
        self.assertEqual(teaching_class.educator, self.educator)
        self.assertRedirects(response, reverse("step:class_detail", args=[teaching_class.pk]))

    def test_a_grade_outside_9_to_11_is_rejected(self):
        response = self.client.post(
            reverse("step:class_create"), {"grade": "12", "slot": "1", "display_name": "9A"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TeachingClass.objects.exists())

    def test_a_slot_outside_1_to_4_is_rejected(self):
        response = self.client.post(
            reverse("step:class_create"), {"grade": "9", "slot": "5", "display_name": "9A"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TeachingClass.objects.exists())

    def test_a_grade_and_slot_already_taken_is_rejected_with_a_plain_message(self):
        TeachingClass.objects.create(educator=self.educator, grade=9, slot=1, display_name="9A")
        response = self.client.post(
            reverse("step:class_create"), {"grade": "9", "slot": "1", "display_name": "9A again"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(TeachingClass.objects.count(), 1)


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
