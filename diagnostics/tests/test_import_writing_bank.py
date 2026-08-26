from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diagnostics.models import WritingQuestion


class ImportWritingBankTests(TestCase):
    def test_imports_two_hundred_questions(self):
        call_command("import_writing_bank", stdout=StringIO())
        self.assertEqual(WritingQuestion.objects.count(), 200)

    def test_idempotent(self):
        call_command("import_writing_bank", stdout=StringIO())
        call_command("import_writing_bank", stdout=StringIO())
        self.assertEqual(WritingQuestion.objects.count(), 200)
