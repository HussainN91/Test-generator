"""Load the clip transcripts from the authored markdown into the database.

The file is gitignored and, for clips 11-20, the only copy that exists, so
this command is how those words stop being a single point of failure: once
imported they are covered by the ordinary database backup.

Idempotent: each run overwrites every clip's transcript from the file. It
never touches questions, sets or papers.
"""

import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from diagnostics.models import AudioClip

DEFAULT_SOURCE = (
    Path(settings.MEDIA_ROOT) / "diagnostics" / "audio" / "transcripts-full.md"
)

#: A clip's body runs from its own "## Clip N" heading to the next "## " at
#: the start of a line, or the end of the file. Non-greedy so clip 1 cannot
#: swallow clip 2, which would silently show a reviewer the wrong recording.
CLIP_RE = re.compile(
    r"^##\s*Clip\s+(\d+)\b.*?$(.*?)(?=^##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)


class Command(BaseCommand):
    help = "Import clip transcripts from the authored markdown file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source", default=None,
            help=f"Override the markdown path (default {DEFAULT_SOURCE}).",
        )

    def handle(self, *args, **options):
        source = Path(options["source"]) if options["source"] else DEFAULT_SOURCE
        if not source.exists():
            raise CommandError(f"Missing transcript file: {source}")

        text = source.read_text(encoding="utf-8")
        bodies = {
            int(number): body.strip()
            for number, body in CLIP_RE.findall(text)
        }
        if not bodies:
            raise CommandError(
                f"No '## Clip N' headings found in {source}; the file is not "
                f"in the expected format."
            )

        clips = {clip.number: clip for clip in AudioClip.objects.all()}

        with transaction.atomic():
            filled = 0
            for number, body in sorted(bodies.items()):
                clip = clips.get(number)
                if clip is None:
                    continue
                clip.transcript = body
                clip.save(update_fields=["transcript"])
                filled += 1

        self.stdout.write(self.style.SUCCESS(
            f"Imported transcripts for {filled} clips."
        ))

        homeless = sorted(set(bodies) - set(clips))
        if homeless:
            self.stdout.write(self.style.WARNING(
                f"Transcripts for clips {homeless} have no imported AudioClip. "
                f"Run import_listening first if that is unexpected."
            ))

        empty = sorted(number for number, clip in clips.items() if not clip.transcript)
        if empty:
            self.stdout.write(self.style.WARNING(
                f"Clips {empty} have no transcript in the file."
            ))
