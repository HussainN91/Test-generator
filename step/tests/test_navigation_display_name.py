"""diagnostics prints "Class N" for every class pack today. This is the one
place STEP's TeachingClass.display_name is allowed to leak into diagnostics —
a one-directional, read-only dependency (classes/gradebook spec, "Diagnostics
rename"). diagnostics gains no login and no editing here.
"""

from django.test import TestCase

from diagnostics.navigation import display_name_for
from step.models import Educator, Region, TeachingClass


class DisplayNameForTests(TestCase):
    def test_falls_back_to_class_n_when_no_teaching_class_exists(self):
        self.assertEqual(display_name_for(grade=9, number=2), "Class 2")

    def test_uses_the_teachers_own_name_when_a_teaching_class_exists(self):
        region = Region.objects.create(name="Samarkand", code="samarkand")
        educator = Educator.objects.create(full_name="Maria Santos", region=region)
        TeachingClass.objects.create(educator=educator, grade=9, slot=2, display_name="9B")
        self.assertEqual(display_name_for(grade=9, number=2), "9B")

    def test_a_class_in_a_different_grade_does_not_match(self):
        region = Region.objects.create(name="Samarkand", code="samarkand")
        educator = Educator.objects.create(full_name="Maria Santos", region=region)
        TeachingClass.objects.create(educator=educator, grade=10, slot=2, display_name="10B")
        self.assertEqual(display_name_for(grade=9, number=2), "Class 2")
