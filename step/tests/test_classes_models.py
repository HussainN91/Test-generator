"""TeachingClass, Student and ProgressEntry — the classes/gradebook data model.

(grade, slot) is globally unique, not scoped to the educator: diagnostics'
four class packs per grade are a fact about the paper bank, and one teacher
owns a given grade+slot in practice (classes/gradebook spec, "Why (grade,
slot) is globally unique"). Score and comment are one row per checkpoint,
not two, because the structured checkpoint record *is* the progress note.
"""

from django.db import IntegrityError
from django.test import TestCase

from step import constants
from step.models import Educator, ProgressEntry, Region, Student, TeachingClass


class TeachingClassTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)

    def test_a_class_needs_a_grade_a_slot_and_a_name(self):
        teaching_class = TeachingClass.objects.create(
            educator=self.educator, grade=9, slot=2, display_name="9B"
        )
        self.assertEqual(str(teaching_class), "9B")

    def test_grade_and_slot_are_globally_unique(self):
        TeachingClass.objects.create(educator=self.educator, grade=9, slot=2, display_name="9B")
        other = Educator.objects.create(full_name="John Cruz", region=self.region)
        with self.assertRaises(IntegrityError):
            TeachingClass.objects.create(educator=other, grade=9, slot=2, display_name="9B again")

    def test_the_same_slot_in_a_different_grade_is_fine(self):
        TeachingClass.objects.create(educator=self.educator, grade=9, slot=2, display_name="9B")
        TeachingClass.objects.create(educator=self.educator, grade=10, slot=2, display_name="10B")
        self.assertEqual(TeachingClass.objects.count(), 2)

    def test_deleting_the_educator_deletes_the_class(self):
        teaching_class = TeachingClass.objects.create(
            educator=self.educator, grade=9, slot=1, display_name="9A"
        )
        self.educator.delete()
        self.assertFalse(TeachingClass.objects.filter(pk=teaching_class.pk).exists())


class StudentTests(TestCase):
    def setUp(self):
        region = Region.objects.create(name="Samarkand", code="samarkand")
        educator = Educator.objects.create(full_name="Maria Santos", region=region)
        self.teaching_class = TeachingClass.objects.create(
            educator=educator, grade=9, slot=1, display_name="9A"
        )

    def test_a_student_belongs_to_one_class(self):
        student = Student.objects.create(teaching_class=self.teaching_class, full_name="Aziz Karimov")
        self.assertEqual(str(student), "Aziz Karimov")
        self.assertIn(student, self.teaching_class.students.all())

    def test_deleting_the_class_deletes_its_students(self):
        student = Student.objects.create(teaching_class=self.teaching_class, full_name="Aziz Karimov")
        self.teaching_class.delete()
        self.assertFalse(Student.objects.filter(pk=student.pk).exists())


class ProgressEntryTests(TestCase):
    def setUp(self):
        region = Region.objects.create(name="Samarkand", code="samarkand")
        educator = Educator.objects.create(full_name="Maria Santos", region=region)
        teaching_class = TeachingClass.objects.create(
            educator=educator, grade=9, slot=1, display_name="9A"
        )
        self.student = Student.objects.create(teaching_class=teaching_class, full_name="Aziz Karimov")

    def test_a_structured_checkpoint_entry_needs_no_grammar_point(self):
        entry = ProgressEntry.objects.create(
            student=self.student, checkpoint=constants.CHECKPOINT_BOY,
            score=78, skill=constants.SKILL_READING,
        )
        self.assertIsNone(entry.grammar_point)
        self.assertEqual(entry.comment, "")

    def test_only_one_structured_entry_per_student_and_checkpoint(self):
        ProgressEntry.objects.create(
            student=self.student, checkpoint=constants.CHECKPOINT_BOY, score=78
        )
        with self.assertRaises(IntegrityError):
            ProgressEntry.objects.create(
                student=self.student, checkpoint=constants.CHECKPOINT_BOY, score=81
            )

    def test_a_blank_checkpoint_freeform_note_may_repeat(self):
        ProgressEntry.objects.create(student=self.student, comment="Doing well with irregular verbs.")
        ProgressEntry.objects.create(student=self.student, comment="Struggling with articles.")
        self.assertEqual(self.student.progress_entries.count(), 2)

    def test_a_different_checkpoint_is_a_different_row(self):
        ProgressEntry.objects.create(
            student=self.student, checkpoint=constants.CHECKPOINT_BOY, score=78
        )
        ProgressEntry.objects.create(
            student=self.student, checkpoint=constants.CHECKPOINT_MOY, score=82
        )
        self.assertEqual(self.student.progress_entries.count(), 2)

    def test_deleting_the_student_deletes_their_entries(self):
        entry = ProgressEntry.objects.create(
            student=self.student, checkpoint=constants.CHECKPOINT_BOY, score=78
        )
        self.student.delete()
        self.assertFalse(ProgressEntry.objects.filter(pk=entry.pk).exists())
