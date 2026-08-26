"""Creates the four STEP role groups. Idempotent; runs on every deployment."""

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from step import constants


class Command(BaseCommand):
    help = "Create the STEP role groups. Safe to re-run."

    def handle(self, *args, **options):
        for name in constants.ROLE_NAMES:
            Group.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS(f"Ensured {len(constants.ROLE_NAMES)} role groups."))
