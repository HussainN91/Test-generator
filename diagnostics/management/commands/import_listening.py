"""Import the client's 20 listening clips into the database.

Sources, all read-only, all under settings.DIAGNOSTICS_SOURCE_DIR:
  - the .md   -> worksheet text and answer keys
  - the .docx -> the 25 picture-option images, in document order
  - the audio folder -> 20 MP3s

Idempotent: re-running replaces clip content in place.
"""

from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from diagnostics.constants import (
    CLIP_TASK_TYPES, IMAGE_SLOTS, LETTER_ANSWER_TYPES, TaskType,
)
from diagnostics.extraction.audio import map_audio_files
from diagnostics.extraction.docx_images import extract_images_in_document_order
from diagnostics.extraction.keys import (
    parse_gap_fill_key, parse_letter_key, split_alternatives,
)
from diagnostics.extraction.listening_content import extract_question_content
from diagnostics.extraction.worksheets import split_clips
from diagnostics.models import AudioClip, ListeningQuestion

MD_NAME = "Listening Question Bank -2026 EC.md"
DOCX_NAME = "Listening Question Bank -2026 EC.docx"
AUDIO_DIR_NAME = "Listening Diagnostic Audio files"


class Command(BaseCommand):
    help = "Import the 20 diagnostic listening clips, questions, keys and images."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source", default=None,
            help="Override settings.DIAGNOSTICS_SOURCE_DIR.",
        )

    def handle(self, *args, **options):
        source = options["source"]
        source_dir = (
            settings.DIAGNOSTICS_SOURCE_DIR if source is None else Path(source)
        )

        markdown_path = source_dir / MD_NAME
        docx_path = source_dir / DOCX_NAME
        audio_dir = source_dir / AUDIO_DIR_NAME

        for path in (markdown_path, docx_path):
            if not path.exists():
                raise CommandError(f"Missing source file: {path}")

        bodies = split_clips(markdown_path.read_text(encoding="utf-8"))
        if sorted(bodies) != list(range(1, 21)):
            raise CommandError(f"Expected clips 1-20, parsed {sorted(bodies)}")

        images = extract_images_in_document_order(docx_path)
        if len(images) != len(IMAGE_SLOTS):
            raise CommandError(
                f"Expected {len(IMAGE_SLOTS)} images, found {len(images)}"
            )
        images_by_slot = dict(zip(IMAGE_SLOTS, images))

        audio = map_audio_files(audio_dir) if audio_dir.exists() else {}
        if not audio:
            self.stdout.write(self.style.WARNING(f"No audio found under {audio_dir}"))

        with transaction.atomic():
            for number in range(1, 21):
                self._import_clip(
                    number, bodies[number], images_by_slot, audio.get(number)
                )

        self.stdout.write(self.style.SUCCESS(
            f"Imported {AudioClip.objects.count()} clips, "
            f"{ListeningQuestion.objects.count()} questions."
        ))

    def _import_clip(self, number, body, images_by_slot, audio_path):
        task_type = CLIP_TASK_TYPES[number]

        clip, _created = AudioClip.objects.update_or_create(
            number=number,
            defaults={"task_type": task_type, "intro_text": self._intro(body)},
        )

        if audio_path is not None and not clip.audio_file:
            clip.audio_file.save(
                f"clip-{number:02d}.mp3",
                ContentFile(audio_path.read_bytes()),
                save=True,
            )

        if task_type in LETTER_ANSWER_TYPES:
            answers = parse_letter_key(body)
            alternatives = [[] for _ in answers]
        else:
            answers = parse_gap_fill_key(body)
            alternatives = [split_alternatives(a) for a in answers]

        content = extract_question_content(number, task_type, body)

        for question in clip.questions.all():
            if question.image:
                question.image.delete(save=False)
        clip.questions.all().delete()
        for position, (answer, alts, item) in enumerate(
            zip(answers, alternatives, content), start=1
        ):
            question = ListeningQuestion.objects.create(
                clip=clip,
                position=position,
                stem=item["stem"],
                options=item["options"],
                answer=answer,
                acceptable_answers=alts,
            )
            slot = images_by_slot.get((number, position))
            if slot is not None:
                part_name, data = slot
                suffix = part_name.rsplit(".", 1)[-1]
                question.image.save(
                    f"clip-{number:02d}-q{position}.{suffix}",
                    ContentFile(data),
                    save=True,
                )

    @staticmethod
    def _intro(body):
        for line in body.splitlines():
            stripped = line.strip().lstrip("*# ").strip()
            if stripped.startswith("You will hear"):
                return stripped.rstrip("*").strip()
        return ""
