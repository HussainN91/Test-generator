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
