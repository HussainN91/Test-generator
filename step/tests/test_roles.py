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
