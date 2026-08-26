from django.conf import settings
from django.test import TestCase

from diagnostics.extraction.worksheets import split_clips, strip_image_data

LISTENING_MD = settings.DIAGNOSTICS_SOURCE_DIR / "Listening Question Bank -2026 EC.md"


class StripImageDataTests(TestCase):
    def test_removes_the_base64_appendix(self):
        text = "body text\n\n[image1]: <data:image/png;base64,AAAA>\n"
        self.assertEqual(strip_image_data(text).strip(), "body text")

    def test_leaves_text_without_an_appendix_alone(self):
        self.assertEqual(strip_image_data("just body"), "just body")


class SplitClipsTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not LISTENING_MD.exists():
            raise AssertionError(f"Source file missing: {LISTENING_MD}")
        cls.clips = split_clips(LISTENING_MD.read_text(encoding="utf-8"))

    def test_finds_twenty_clips(self):
        self.assertEqual(sorted(self.clips), list(range(1, 21)))

    def test_no_clip_body_contains_base64(self):
        for number, body in self.clips.items():
            self.assertNotIn("base64", body, f"clip {number} still holds image data")

    def test_bodies_are_substantial(self):
        for number, body in self.clips.items():
            self.assertGreater(len(body), 100, f"clip {number} body looks truncated")

    def test_intro_is_captured_where_present(self):
        self.assertIn("interview with a teenager called Simon", self.clips[2])
