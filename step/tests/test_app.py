"""The app must be installed before anything else can be tested.

This exists because a missing INSTALLED_APPS entry fails later with confusing
errors about missing tables rather than a missing app.
"""

from django.apps import apps
from django.test import TestCase

from step import constants


class AppRegistrationTests(TestCase):
    def test_step_app_is_installed(self):
        self.assertTrue(apps.is_installed("step"))

    def test_app_config_label(self):
        self.assertEqual(apps.get_app_config("step").label, "step")


class ConstantsTests(TestCase):
    def test_statuses_are_distinct(self):
        values = [v for v, _ in constants.OBLIGATION_STATUS_CHOICES]
        self.assertEqual(len(values), len(set(values)))

    def test_not_started_is_the_initial_status(self):
        self.assertEqual(constants.STATUS_NOT_STARTED, "not_started")


class ClassesGradebookConstantsTests(TestCase):
    def test_checkpoint_and_skill_values_are_distinct(self):
        checkpoints = [v for v, _ in constants.CHECKPOINT_CHOICES]
        self.assertEqual(len(checkpoints), len(set(checkpoints)))
        skills = [v for v, _ in constants.SKILL_CHOICES]
        self.assertEqual(len(skills), len(set(skills)))

    def test_every_checkpoint_maps_to_an_obligation_type_name(self):
        checkpoints = {v for v, _ in constants.CHECKPOINT_CHOICES}
        self.assertEqual(set(constants.CHECKPOINT_OBLIGATION_NAME_TEMPLATES), checkpoints)

    def test_the_reverse_lookup_is_the_exact_inverse(self):
        for checkpoint, template in constants.CHECKPOINT_OBLIGATION_NAME_TEMPLATES.items():
            self.assertEqual(constants.NAME_TEMPLATE_TO_CHECKPOINT[template], checkpoint)
