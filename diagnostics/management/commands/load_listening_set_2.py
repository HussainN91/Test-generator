"""Load the authored second question set for all 20 clips.

Set 1 comes out of the client's .docx via import_listening. Set 2 is written
by hand from the transcripts (media/diagnostics/audio/transcripts-full.md)
and lives in diagnostics/authored/listening_set_2.json - the picture clips
reuse items 6 and 7, which were recorded but never turned into questions;
the rotating clips get five newly written questions each.

All-or-nothing: the payload is validated in full, every referenced image is
confirmed to exist, and only then is anything written, inside one
transaction. A half-loaded set 2 would let the group allocator issue a paper
with three listening questions on it.

Idempotent: re-running deletes and rebuilds set 2. It never touches set 1.
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from diagnostics.authored.listening_sets import (
    ContentError, validate_listening_set_file,
)
from diagnostics.models import AudioClip, ListeningQuestion, ListeningQuestionSet

DEFAULT_PAYLOAD = (
    Path(settings.BASE_DIR) / "diagnostics" / "authored" / "listening_set_2.json"
)
IMAGE_DIR_NAME = "diagnostics/listening"
SET_NUMBER = 2


class Command(BaseCommand):
    help = "Load the authored second listening question set for all 20 clips."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source", default=None,
            help=f"Override the payload path (default {DEFAULT_PAYLOAD}).",
        )
        parser.add_argument(
            "--skip-images", action="store_true",
            help="Do not attach picture-strip images. Tests only.",
        )

    def handle(self, *args, **options):
        source = Path(options["source"]) if options["source"] else DEFAULT_PAYLOAD
        skip_images = options["skip_images"]

        if not source.exists():
            raise CommandError(f"Missing authored payload: {source}")

        document = json.loads(source.read_text(encoding="utf-8"))
        try:
            validate_listening_set_file(document)
        except ContentError as error:
            raise CommandError(f"Authored content is malformed: {error}") from error

        if not skip_images:
            image_dir = Path(settings.MEDIA_ROOT) / IMAGE_DIR_NAME
            self._confirm_images_exist(document, image_dir)

        clips = {clip.number: clip for clip in AudioClip.objects.all()}
        missing = sorted(
            entry["number"] for entry in document["clips"]
            if entry["number"] not in clips
        )
        if missing:
            raise CommandError(
                f"Clips {missing} are not imported. Run import_listening first."
            )

        with transaction.atomic():
            for entry in document["clips"]:
                self._load_clip(clips[entry["number"]], entry, skip_images)

        loaded = ListeningQuestion.objects.filter(
            question_set__number=SET_NUMBER
        ).count()
        self.stdout.write(self.style.SUCCESS(
            f"Loaded set {SET_NUMBER} for "
            f"{ListeningQuestionSet.objects.filter(number=SET_NUMBER).count()} clips "
            f"({loaded} questions)."
        ))
        self.stdout.write(
            "The listening key sign-off has lapsed - the answer bank changed. "
            "Re-run verify_listening_keys once a human has checked the new answers."
        )

    def _confirm_images_exist(self, document, image_dir):
        """Confirm every referenced image exists up front, so a missing file
        fails the command before a single row is written.

        These images are the picture-strip files already composited by
        import_listening, permanently living at image_dir. Set 2 questions
        reference that same canonical file rather than owning a private
        copy, so only existence needs confirming here - the bytes are never
        read into memory or copied anywhere.
        """
        for entry in document["clips"]:
            for question in entry["questions"]:
                name = question.get("image")
                if not name:
                    continue
                path = image_dir / name
                if not path.exists():
                    raise CommandError(
                        f"Clip {entry['number']} Q{question['position']} references "
                        f"{name}, which does not exist under {image_dir}."
                    )

    def _load_clip(self, clip, entry, skip_images):
        question_set, _ = ListeningQuestionSet.objects.get_or_create(
            clip=clip, number=SET_NUMBER
        )
        # Only the DB rows are cleared here, deliberately via QuerySet.delete()
        # rather than iterating and calling question.image.delete(): the
        # ImageField below points straight at the shared, permanent source
        # file under IMAGE_DIR_NAME rather than a copy the question owns, so
        # deleting it here would delete the canonical image out from under
        # every other question/set that references it.
        question_set.questions.all().delete()

        for payload in entry["questions"]:
            question = ListeningQuestion.objects.create(
                question_set=question_set,
                position=payload["position"],
                stem=payload["stem"],
                options=payload.get("options") or [],
                answer=payload["answer"],
                acceptable_answers=payload.get("acceptable_answers") or [],
            )
            name = payload.get("image")
            if name and not skip_images:
                # Point at the existing file directly - it already lives at
                # its final destination, so there is nothing to copy. Using
                # ImageField.save() here would ask FileSystemStorage to save
                # bytes under a name that already exists, and storage never
                # overwrites: it silently renames to a *_XXXXXXXX suffix,
                # producing a stray duplicate on every run.
                question.image.name = f"{IMAGE_DIR_NAME}/{name}"
                question.save(update_fields=["image"])
