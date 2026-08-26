from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diagnostics.models import SpeakingPrompt, SpeakingRubric


class ImportSpeakingBankTests(TestCase):
    def test_imports_fifty_prompts_and_five_rubric_rows(self):
        call_command("import_speaking_bank", stdout=StringIO())
        self.assertEqual(SpeakingPrompt.objects.count(), 50)
        self.assertEqual(SpeakingRubric.objects.count(), 5)

    def test_idempotent(self):
        call_command("import_speaking_bank", stdout=StringIO())
        call_command("import_speaking_bank", stdout=StringIO())
        self.assertEqual(SpeakingPrompt.objects.count(), 50)
