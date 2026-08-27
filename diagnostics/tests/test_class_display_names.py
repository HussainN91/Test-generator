"""The grade and class-pack screens must show a teacher's own class name once
one exists — see diagnostics.navigation.display_name_for and the
classes/gradebook spec's "Diagnostics rename"."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from step.models import Educator, Region, TeachingClass


class GradeDetailDisplayNameTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("staff1", password="pw", is_staff=True)
        self.client.force_login(self.user)

    def test_an_unclaimed_pack_still_shows_class_n(self):
        response = self.client.get(reverse("diagnostics:grade_detail", args=[9]))
        self.assertContains(response, "Class 2")

    def test_a_claimed_pack_shows_the_teachers_name(self):
        region = Region.objects.create(name="Samarkand", code="samarkand")
        educator = Educator.objects.create(full_name="Maria Santos", region=region)
        TeachingClass.objects.create(educator=educator, grade=9, slot=2, display_name="9B")
        response = self.client.get(reverse("diagnostics:grade_detail", args=[9]))
        self.assertContains(response, "9B")


class ClassPackDisplayNameTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("staff2", password="pw", is_staff=True)
        self.client.force_login(self.user)

    def test_the_class_pack_page_shows_the_teachers_name(self):
        region = Region.objects.create(name="Samarkand", code="samarkand")
        educator = Educator.objects.create(full_name="Maria Santos", region=region)
        TeachingClass.objects.create(educator=educator, grade=9, slot=1, display_name="9A")
        response = self.client.get(reverse("diagnostics:class_pack", args=[9, 1]))
        self.assertContains(response, "9A")
