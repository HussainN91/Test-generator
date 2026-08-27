"""Where signing in puts you.

The site is three tools behind one login, so the destination is a role
question, not a constant. These pin the answer for each kind of account,
including the one that used to be stranded: a superuser, who could reach the
Django admin and diagnostics but got a 403 from every STEP staff screen and a
404 from the teacher dashboard.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from step import constants, roles
from step.models import Educator, Region


class SignInLandingTests(TestCase):
    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        self.region = Region.objects.create(name="Samarkand", code="samarkand")

    def _land(self, user):
        self.client.force_login(user)
        return self.client.get(reverse("post_login"))

    def test_a_superuser_lands_on_the_administration_dashboard(self):
        boss = get_user_model().objects.create_superuser("root", password="pw")
        self.assertRedirects(
            self._land(boss), reverse("step:admin-dashboard"), fetch_redirect_response=False
        )

    def test_programme_staff_land_on_the_administration_dashboard(self):
        staff = get_user_model().objects.create_user("olim", password="pw")
        roles.assign(staff, constants.ROLE_PROGRAMME_ADMIN)
        self.assertRedirects(
            self._land(staff), reverse("step:admin-dashboard"), fetch_redirect_response=False
        )

    def test_a_teacher_lands_on_their_own_dashboard(self):
        user = get_user_model().objects.create_user("maria", password="pw")
        roles.assign(user, constants.ROLE_EDUCATOR)
        Educator.objects.create(full_name="Maria Santos", region=self.region, user=user)
        self.assertRedirects(
            self._land(user), reverse("step:dashboard"), fetch_redirect_response=False
        )

    def test_a_rostered_teacher_with_no_group_still_lands_on_their_dashboard(self):
        """The roster importer links the record without assigning the group;
        only self-signup does. The record is enough."""
        user = get_user_model().objects.create_user("dilnoza", password="pw")
        Educator.objects.create(full_name="Dilnoza R.", region=self.region, user=user)
        self.assertRedirects(
            self._land(user), reverse("step:dashboard"), fetch_redirect_response=False
        )

    def test_everyone_else_lands_on_the_test_generator(self):
        user = get_user_model().objects.create_user("nobody", password="pw")
        self.assertRedirects(self._land(user), reverse("builder"), fetch_redirect_response=False)

    def test_the_sign_in_form_itself_carries_you_through_to_administration(self):
        """The real journey, not just a direct visit to the dispatcher: the
        login form hands off to /after-sign-in/, which forwards by role."""
        get_user_model().objects.create_superuser("root2", password="pw")
        response = self.client.post(
            reverse("login"), {"username": "root2", "password": "pw"}, follow=True
        )
        self.assertEqual(response.redirect_chain[-1][0], reverse("step:admin-dashboard"))
        self.assertEqual(response.status_code, 200)


class StaffOnTheTeacherDashboardTests(TestCase):
    """A staff account has no roster row by design, so /step/ used to 404 at
    them. It should point them at their own screens instead."""

    def setUp(self):
        call_command("seed_roles", stdout=StringIO())

    def test_a_superuser_visiting_step_is_sent_to_administration(self):
        boss = get_user_model().objects.create_superuser("root", password="pw")
        self.client.force_login(boss)
        self.assertRedirects(
            self.client.get(reverse("step:dashboard")),
            reverse("step:admin-dashboard"),
            fetch_redirect_response=False,
        )

    def test_a_user_who_is_neither_still_gets_told_they_are_unlinked(self):
        stray = get_user_model().objects.create_user("stray", password="pw")
        self.client.force_login(stray)
        self.assertEqual(self.client.get(reverse("step:dashboard")).status_code, 404)


class AdminAreaAccessTests(TestCase):
    def setUp(self):
        call_command("seed_roles", stdout=StringIO())

    def test_a_superuser_is_no_longer_forbidden_from_the_admin_screens(self):
        boss = get_user_model().objects.create_superuser("root", password="pw")
        self.client.force_login(boss)
        self.assertEqual(self.client.get(reverse("step:admin-dashboard")).status_code, 200)

    def test_a_plain_account_is_still_forbidden(self):
        user = get_user_model().objects.create_user("nobody", password="pw")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("step:admin-dashboard")).status_code, 403)
