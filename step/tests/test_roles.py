"""Roles decide who accrues obligations, so getting them wrong creates
phantom work for staff (spec §5.6). Django Groups are used so permission
checks stay conventional.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase

from step import constants, roles


class SeedRolesTests(TestCase):
    def test_creates_the_four_groups(self):
        call_command("seed_roles", stdout=StringIO())
        self.assertEqual(
            sorted(Group.objects.values_list("name", flat=True)),
            sorted(constants.ROLE_NAMES),
        )

    def test_running_twice_does_not_duplicate(self):
        call_command("seed_roles", stdout=StringIO())
        call_command("seed_roles", stdout=StringIO())
        self.assertEqual(Group.objects.count(), 4)


class RoleHelperTests(TestCase):
    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        self.user = get_user_model().objects.create_user("maria", password="x")

    def test_a_user_with_no_group_has_no_role(self):
        self.assertEqual(roles.role_names(self.user), set())
        self.assertFalse(roles.is_educator(self.user))
        self.assertFalse(roles.is_staff_role(self.user))

    def test_assigning_a_role_is_reflected(self):
        roles.assign(self.user, constants.ROLE_EDUCATOR)
        self.assertTrue(roles.is_educator(self.user))
        self.assertFalse(roles.is_staff_role(self.user))

    def test_staff_roles_are_recognised(self):
        roles.assign(self.user, constants.ROLE_PROGRAMME_ADMIN)
        self.assertTrue(roles.is_staff_role(self.user))
        self.assertFalse(roles.is_educator(self.user))

    def test_assigning_an_unknown_role_raises(self):
        with self.assertRaises(ValueError):
            roles.assign(self.user, "Wizard")

    def test_a_superuser_counts_as_a_system_administrator(self):
        """The account that deploys the site must not be locked out of the
        staff screens it is responsible for."""
        boss = get_user_model().objects.create_superuser("root", password="x")
        self.assertIn(constants.ROLE_SYSTEM_ADMIN, roles.role_names(boss))
        self.assertTrue(roles.is_staff_role(boss))

    def test_a_superuser_is_not_thereby_an_educator(self):
        """Staff never accrue obligations (spec §5.6), so the implicit role
        must not leak into the educator side."""
        boss = get_user_model().objects.create_superuser("root2", password="x")
        self.assertFalse(roles.is_educator(boss))

    def test_plain_is_staff_does_not_grant_a_step_role(self):
        """Django's `is_staff` only opens the Django admin. STEP's staff
        screens stay group-gated for everyone but superusers."""
        djangoish = get_user_model().objects.create_user("desk", password="x", is_staff=True)
        self.assertEqual(roles.role_names(djangoish), set())
        self.assertFalse(roles.is_staff_role(djangoish))

    def test_only_programme_admin_can_publish_announcements(self):
        """fix step plan §5.2 — narrower than `is_staff_role`, deliberately:
        the other two staff roles reach every other staff screen but not
        this one."""
        roles.assign(self.user, constants.ROLE_PROGRAMME_ADMIN)
        self.assertTrue(roles.can_publish_announcements(self.user))

    def test_the_other_two_staff_roles_cannot_publish_announcements(self):
        roles.assign(self.user, constants.ROLE_ADMIN)
        self.assertFalse(roles.can_publish_announcements(self.user))

    def test_a_superuser_cannot_publish_announcements_without_the_role(self):
        """Provisional reading of §5.2 (read literally: Programme Admin
        only) — unlike every other staff gate, the deploying superuser is
        NOT implicitly admitted here. Flagged to the orchestrator as a
        one-line flip if that reading is wrong."""
        boss = get_user_model().objects.create_superuser("root3", password="x")
        self.assertFalse(roles.can_publish_announcements(boss))
