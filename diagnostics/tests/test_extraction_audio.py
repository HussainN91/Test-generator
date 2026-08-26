from django.conf import settings
from django.test import TestCase

from diagnostics.extraction.audio import clip_number_from_filename, map_audio_files

AUDIO_DIR = settings.DIAGNOSTICS_SOURCE_DIR / "Listening Diagnostic Audio files"


class FilenameTests(TestCase):
    def test_handles_every_naming_style_in_the_folder(self):
        self.assertEqual(clip_number_from_filename("Audio 1.mp3"), 1)
        self.assertEqual(clip_number_from_filename("Audio4.mp3"), 4)
        self.assertEqual(clip_number_from_filename("Audio10.mp3"), 10)
        self.assertEqual(clip_number_from_filename("Audio 20.mp3"), 20)

    def test_returns_none_for_unrelated_files(self):
        self.assertIsNone(clip_number_from_filename("notes.txt"))


class MappingTests(TestCase):
    def test_maps_all_twenty_clips(self):
        if not AUDIO_DIR.exists():
            self.skipTest(f"Audio folder not present: {AUDIO_DIR}")
        mapping = map_audio_files(AUDIO_DIR)
        self.assertEqual(sorted(mapping), list(range(1, 21)))
