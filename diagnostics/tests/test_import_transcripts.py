"""The transcripts are the only record of what each recording actually says,
and for clips 11-20 the markdown file is the sole copy. The importer is
therefore written to fail loudly rather than half-fill the bank."""

from io import StringIO
from pathlib import Path
import tempfile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from diagnostics.models import AudioClip

SAMPLE = """# Listening clip transcripts

Some preamble that is not a clip.

---

## Clip 1  [picture]

**1. Which dish did Mark cook?**
Interviewer: So you've won.

**2. Where is the book?**
Girl: Excuse me.

---

## Clip 2  [mcq3]

Interviewer: Hello everyone.

---
"""


class ImportTranscriptsTests(TestCase):
    def setUp(self):
        self.clip_1 = AudioClip.objects.create(number=1, task_type="picture")
        self.clip_2 = AudioClip.objects.create(number=2, task_type="mcq3")
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        )
        handle.write(SAMPLE)
        handle.close()
        self.source = Path(handle.name)

    def _run(self):
        call_command("import_transcripts", source=str(self.source), stdout=StringIO())

    def test_each_clip_gets_its_own_body(self):
        self._run()
        self.clip_1.refresh_from_db()
        self.clip_2.refresh_from_db()
        self.assertIn("Which dish did Mark cook?", self.clip_1.transcript)
        self.assertIn("Interviewer: Hello everyone.", self.clip_2.transcript)

    def test_a_clips_body_stops_at_the_next_clip(self):
        """Clip 1 must not swallow clip 2's text - the whole point of the
        page is checking a question against the right recording."""
        self._run()
        self.clip_1.refresh_from_db()
        self.assertNotIn("Hello everyone", self.clip_1.transcript)

    def test_preamble_is_not_stored_on_any_clip(self):
        self._run()
        for clip in AudioClip.objects.all():
            self.assertNotIn("Some preamble", clip.transcript)

    def test_rerunning_changes_nothing(self):
        self._run()
        before = {c.number: c.transcript for c in AudioClip.objects.all()}
        self._run()
        after = {c.number: c.transcript for c in AudioClip.objects.all()}
        self.assertEqual(before, after)

    def test_a_missing_file_is_a_command_error(self):
        with self.assertRaisesMessage(CommandError, "no-such-file.md"):
            call_command(
                "import_transcripts", source="no-such-file.md", stdout=StringIO()
            )

    def test_a_transcript_for_an_unimported_clip_is_reported_not_ignored(self):
        """A transcript with nowhere to go means the clip bank and the
        transcript file disagree, which the operator needs told."""
        AudioClip.objects.filter(number=2).delete()
        out = StringIO()
        call_command("import_transcripts", source=str(self.source), stdout=out)
        self.assertIn("2", out.getvalue())

    def test_reports_how_many_clips_it_filled(self):
        out = StringIO()
        call_command("import_transcripts", source=str(self.source), stdout=out)
        self.assertIn("2", out.getvalue())
