"""Assemble the forty-eight diagnostic papers (16 variants x 3 grades).

Listening and reading come from `diagnostics.allocation.allocate`, a pure,
deterministic function: the bank (20 clips, 15 passages) cannot supply 16
distinct variants per grade, so content repeats up to the caps in
`REUSE_CAPS` instead of being hand-tabulated the way the old 12-paper table
was. Writing and speaking are sampled per paper from the shared banks,
excluding anything that has already hit its reuse cap within the same grade.

The whole build runs in one transaction and re-verifies the reuse-cap rule
before committing, so a violation rolls the entire build back rather than
leaving a half-valid bank on disk.

Safe by default: a paper that already has its full complement of sampled
writing/speaking content is left completely untouched. Sampling is random, so
re-sampling an existing paper would silently reissue different questions under
the same paper name - which, once papers have gone out to teachers, means two
people holding "G9-A" have different tests. Pass --resample to deliberately
redraw everything.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from diagnostics.allocation import allocate
from diagnostics.constants import CLIP_TASK_TYPES, GRADES, VARIANTS
from diagnostics.models import AudioClip, Paper, ReadingPassage
from diagnostics.sampling import SamplingError, sample_speaking_prompts, sample_writing_questions
from diagnostics.verification import find_reuse_violations


class Command(BaseCommand):
    help = "Build the 48 diagnostic papers from the imported content banks."

    def add_arguments(self, parser):
        parser.add_argument(
            "--resample",
            action="store_true",
            help=(
                "Redraw writing/speaking content for papers that already have "
                "it. Changes what students sit - only use before papers have "
                "been handed out."
            ),
        )

    def handle(self, *args, **options):
        resample = options["resample"]
        clips = {clip.number: clip for clip in AudioClip.objects.all()}
        needed_clips = set(CLIP_TASK_TYPES)
        missing = sorted(needed_clips - set(clips))
        if missing:
            raise CommandError(
                f"Missing listening clips {missing}. Run import_listening first."
            )

        passages = {p.label: p for p in ReadingPassage.objects.all()}

        sampled = 0
        left_alone = 0
        try:
            with transaction.atomic():
                for grade in GRADES:
                    for variant in VARIANTS:
                        picture, rotating, passage_label = allocate(grade, variant)
                        if passage_label not in passages:
                            raise CommandError(
                                f"G{grade}-{variant} needs reading passage "
                                f"{passage_label}, which is not imported. "
                                f"Run import_reading_bank first."
                            )
                        paper, _ = Paper.objects.update_or_create(
                            grade=grade,
                            variant=variant,
                            defaults={
                                "listening_clip_1": clips[picture],
                                "listening_clip_2": clips[rotating],
                                "reading_passage": passages[passage_label],
                                "is_published": True,
                            },
                        )
                        already_complete = (
                            paper.writing_questions.count() == 10
                            and paper.speaking_prompts.count() == 5
                        )
                        if already_complete and not resample:
                            left_alone += 1
                            continue
                        sample_writing_questions(paper)
                        sample_speaking_prompts(paper)
                        sampled += 1

                problems = find_reuse_violations()
                if problems:
                    raise CommandError(
                        "Build produced a reuse-cap violation, rolling back:\n  "
                        + "\n  ".join(problems)
                    )
        except SamplingError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(self.style.SUCCESS(
            f"Built {Paper.objects.count()} papers "
            f"({sampled} sampled, {left_alone} already complete and left unchanged)."
        ))
        if left_alone and not resample:
            self.stdout.write(
                "Pass --resample to redraw content for papers that already have it."
            )
