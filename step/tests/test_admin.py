"""Every model must be browsable, because until the STEP interface exists the
admin is the only way to see what the importer and generator produced. This
mirrors the same test in the diagnostics app.

Personal identifiers must not appear in list views (spec §4.4).
"""

from django.apps import apps
from django.contrib import admin
from django.test import TestCase

from step.models import Educator


class AdminRegistrationTests(TestCase):
    def test_every_step_model_is_registered(self):
        unregistered = [
            model._meta.label
            for model in apps.get_app_config("step").get_models()
            if not admin.site.is_registered(model)
        ]
        self.assertEqual(unregistered, [], f"not browsable in the admin: {unregistered}")


class PersonalIdentifierTests(TestCase):
    def test_passport_and_pinfl_are_not_in_the_educator_list_display(self):
        list_display = admin.site._registry[Educator].list_display
        self.assertNotIn("passport_no", list_display)
        self.assertNotIn("pinfl", list_display)

    def test_passport_and_pinfl_are_not_searchable(self):
        """Search terms end up in query strings and server logs (spec §4.4)."""
        search_fields = admin.site._registry[Educator].search_fields
        self.assertNotIn("passport_no", search_fields)
        self.assertNotIn("pinfl", search_fields)
