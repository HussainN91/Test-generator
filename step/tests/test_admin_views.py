"""Admin-facing screens: the action-queue dashboard, the review workflow, and
the teacher directory. Gated to the three staff roles (spec §5.6); an
Educator or an anonymous visitor must never reach any of it.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from step import constants, roles
from step.models import Educator, Region


class AccessControlTests(TestCase):
    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        self.region = Region.objects.create(name="Samarkand", code="samarkand")

    def _staff(self, username, role=constants.ROLE_ADMIN):
        user = get_user_model().objects.create_user(username, password="pw")
        roles.assign(user, role)
        return user

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse("step:admin-dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_an_educator_is_forbidden(self):
        user = get_user_model().objects.create_user("maria", password="pw")
        roles.assign(user, constants.ROLE_EDUCATOR)
        Educator.objects.create(full_name="Maria Santos", region=self.region, user=user)
        self.client.login(username="maria", password="pw")
        response = self.client.get(reverse("step:admin-dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_a_signed_in_user_with_no_role_at_all_is_forbidden(self):
        get_user_model().objects.create_user("nobody", password="pw")
        self.client.login(username="nobody", password="pw")
        response = self.client.get(reverse("step:admin-dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_each_of_the_three_staff_roles_is_admitted(self):
        for i, role in enumerate(
            [constants.ROLE_ADMIN, constants.ROLE_PROGRAMME_ADMIN, constants.ROLE_SYSTEM_ADMIN]
        ):
            self._staff(f"staff{i}", role)
            self.client.login(username=f"staff{i}", password="pw")
            response = self.client.get(reverse("step:admin-dashboard"))
            self.assertEqual(response.status_code, 200, f"{role} was refused the dashboard")
            self.client.logout()


class DashboardShellTests(TestCase):
    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        user = get_user_model().objects.create_user("admin1", password="pw")
        roles.assign(user, constants.ROLE_ADMIN)
        self.client.login(username="admin1", password="pw")

    def test_dashboard_renders_the_letterhead_and_admin_rail(self):
        response = self.client.get(reverse("step:admin-dashboard"))
        self.assertContains(response, "STEP")
        self.assertContains(response, "Administration")

    def test_dashboard_shows_the_signed_in_staff_members_name(self):
        response = self.client.get(reverse("step:admin-dashboard"))
        self.assertContains(response, "admin1")
