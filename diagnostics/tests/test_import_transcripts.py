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
        self.source = self._write(SAMPLE)

    def _write(self, text):
        """Write `text` to a fresh temp .md file and clean it up afterwards."""
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        )
        handle.write(text)
        handle.close()
        path = Path(handle.name)
        self.addCleanup(path.unlink)
        return path

    def _run(self, source=None):
        call_command(
            "import_transcripts",
            source=str(source or self.source),
            stdout=StringIO(),
        )

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
        self.assertIn("clips [2] have no imported AudioClip", out.getvalue())

    def test_reports_how_many_clips_it_filled(self):
        out = StringIO()
        call_command("import_transcripts", source=str(self.source), stdout=out)
        self.assertIn("Imported transcripts for 2 clips", out.getvalue())

    def test_a_heading_typo_missing_the_space_after_hashes_is_still_a_boundary(self):
        """"##Clip 2" (no space after the hashes) is a plausible hand-typing
        slip. It must still end clip 1's body and start its own - not get
        silently absorbed into clip 1 and vanish from the bank."""
        source = self._write(SAMPLE.replace("## Clip 2", "##Clip 2"))
        self._run(source)
        self.clip_1.refresh_from_db()
        self.clip_2.refresh_from_db()
        self.assertNotIn("Hello everyone", self.clip_1.transcript)
        self.assertIn("Interviewer: Hello everyone.", self.clip_2.transcript)

    def test_a_duplicate_heading_is_a_command_error(self):
        """Two "## Clip 1" sections (a copy-paste slip while editing) must
        not silently keep only the last one - the operator needs told which
        clip number is duplicated so they can fix the source file."""
        duplicated = SAMPLE.replace(
            "## Clip 2  [mcq3]\n\nInterviewer: Hello everyone.",
            "## Clip 1  [picture]\n\nInterviewer: Hello everyone.",
        )
        source = self._write(duplicated)
        with self.assertRaisesMessage(CommandError, "[1]"):
            call_command("import_transcripts", source=str(source), stdout=StringIO())
