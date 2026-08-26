"""Print every listening answer for human checking, and record sign-off."""

from django.core.management.base import BaseCommand, CommandError

from diagnostics.constants import TaskType
from diagnostics.models import KeyVerification, ListeningQuestion


class Command(BaseCommand):
    help = "Show all listening answers for verification; --sign-off records approval."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sign-off", metavar="NAME", default=None,
            help="Record that NAME has checked every answer above.",
        )

    def handle(self, *args, **options):
        questions = ListeningQuestion.objects.select_related("clip").order_by(
            "clip__number", "position"
        )
        if not questions:
            raise CommandError("No listening questions imported yet.")

        current_clip = None
        for question in questions:
            if question.clip_id != current_clip:
                current_clip = question.clip_id
                label = TaskType(question.clip.task_type).label
                self.stdout.write("")
                self.stdout.write(self.style.MIGRATE_HEADING(
                    f"Clip {question.clip.number:>2} — {label}"
                ))
            alternatives = (
                f"   (also accept: {', '.join(question.acceptable_answers)})"
                if len(question.acceptable_answers) > 1 else ""
            )
            self.stdout.write(
                f"  Clip {question.clip.number:>2} Q{question.position}  "
                f"{question.answer}{alternatives}"
            )

        self.stdout.write("")
        self.stdout.write(f"Total: {questions.count()} answers.")

        name = options["sign_off"]
        if name:
            KeyVerification.objects.update_or_create(
                pk=1,
                defaults={
                    "verified_by": name,
                    "fingerprint": KeyVerification.current_fingerprint(),
                },
            )
            self.stdout.write(self.style.SUCCESS(f"Signed off by {name}."))
        elif KeyVerification.is_signed_off():
            record = KeyVerification.load()
            self.stdout.write(self.style.SUCCESS(
                f"Already signed off by {record.verified_by}."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "NOT signed off. Check every answer above against its audio, "
                "then re-run with --sign-off \"Your Name\"."
            ))
