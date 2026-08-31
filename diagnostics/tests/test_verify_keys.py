from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diagnostics.constants import TaskType
from diagnostics.models import (
    AudioClip, KeyVerification, ListeningQuestion, ListeningQuestionSet,
)


class VerifyListeningKeysTests(TestCase):
    def setUp(self):
        clip = AudioClip.objects.create(number=1, task_type=TaskType.PICTURE)
        question_set = ListeningQuestionSet.objects.create(clip=clip, number=1)
        for position in range(1, 6):
            ListeningQuestion.objects.create(
                question_set=question_set, position=position, stem="s", answer="A"
            )

    def test_report_lists_every_question(self):
        out = StringIO()
        call_command("verify_listening_keys", stdout=out)
        report = out.getvalue()
        for position in range(1, 6):
            self.assertIn(f"Clip  1 Q{position}", report)

    def test_report_alone_does_not_sign_off(self):
        call_command("verify_listening_keys", stdout=StringIO())
        self.assertFalse(KeyVerification.is_signed_off())

    def test_sign_off_records_who_and_when(self):
        call_command("verify_listening_keys", "--sign-off", "Munish", stdout=StringIO())
        self.assertTrue(KeyVerification.is_signed_off())
        self.assertEqual(KeyVerification.load().verified_by, "Munish")

    def test_sign_off_is_invalidated_when_an_answer_changes(self):
        call_command("verify_listening_keys", "--sign-off", "Munish", stdout=StringIO())
        question = ListeningQuestion.objects.first()
        question.answer = "C"
        question.save()
        self.assertFalse(KeyVerification.is_signed_off())
