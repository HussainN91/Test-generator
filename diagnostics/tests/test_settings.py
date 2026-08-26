"""The app must be installed and its source/media paths configured."""

from django.apps import apps
from django.conf import settings
from django.test import TestCase


class AppInstallationTests(TestCase):
    def test_diagnostics_app_is_installed(self):
        self.assertTrue(apps.is_installed("diagnostics"))

    def test_media_root_is_configured(self):
        self.assertTrue(str(settings.MEDIA_ROOT).endswith("media"))
        self.assertEqual(settings.MEDIA_URL, "/media/")

    def test_diagnostics_source_dir_is_configured(self):
        self.assertTrue(hasattr(settings, "DIAGNOSTICS_SOURCE_DIR"))
