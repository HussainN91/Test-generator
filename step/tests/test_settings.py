"""The database must be switchable without a code change (spec §8).

SQLite stays the default so the existing 312-test suite keeps running on a
machine with no Postgres. The cutover is a deployment step.
"""

import importlib

from django.test import SimpleTestCase


class DatabaseConfigTests(SimpleTestCase):
    def test_defaults_to_sqlite(self):
        from django.conf import settings
        self.assertIn("sqlite3", settings.DATABASES["default"]["ENGINE"])

    def test_postgres_is_selected_by_environment(self):
        import os
        from config import settings as settings_module

        previous = os.environ.get("TESTGEN_DB_ENGINE")
        os.environ["TESTGEN_DB_ENGINE"] = "postgres"
        try:
            reloaded = importlib.reload(settings_module)
            self.assertIn("postgresql", reloaded.DATABASES["default"]["ENGINE"])
        finally:
            if previous is None:
                os.environ.pop("TESTGEN_DB_ENGINE", None)
            else:
                os.environ["TESTGEN_DB_ENGINE"] = previous
            importlib.reload(settings_module)


class StepSettingsTests(SimpleTestCase):
    def test_roster_match_keys_is_a_list(self):
        from django.conf import settings
        self.assertIsInstance(settings.STEP_ROSTER_MATCH_KEYS, list)
        self.assertTrue(settings.STEP_ROSTER_MATCH_KEYS)
