"""Evidence is a list, not a field (spec §5.7), and revisions never overwrite
(spec §5.8). The revision history is the audit trail and the data behind
Feedback & Correction.
"""

import tempfile
from datetime import date

from django.test import TestCase, override_settings

from step import constants
from step.models import (
    Educator, Evidence, Obligation, ObligationType, Region, Submission,
)

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class SubmissionTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY,
        )
        self.obligation = Obligation.objects.create(
            type=self.type, educator=self.educator, period_kind=constants.PERIOD_MONTH,
            period_start=date(2026, 5, 1), due_date=date(2026, 5, 27),
        )

    def test_a_submission_starts_at_revision_one(self):
        submission = Submission.objects.create(obligation=self.obligation)
        self.assertEqual(submission.revision, 1)

    def test_one_submission_per_revision(self):
        from django.db import IntegrityError
        Submission.objects.create(obligation=self.obligation, revision=1)
        with self.assertRaises(IntegrityError):
            Submission.objects.create(obligation=self.obligation, revision=1)

    def test_latest_returns_the_highest_revision(self):
        Submission.objects.create(obligation=self.obligation, revision=1)
        second = Submission.objects.create(obligation=self.obligation, revision=2)
        self.assertEqual(self.obligation.latest_submission, second)

    def test_a_submission_carries_many_evidence_items(self):
        submission = Submission.objects.create(obligation=self.obligation)
        Evidence.objects.create(
            submission=submission, kind=constants.EVIDENCE_LINK_KIND, url="https://drive.example/1"
        )
        Evidence.objects.create(
            submission=submission, kind=constants.EVIDENCE_LINK_KIND, url="https://drive.example/2"
        )
        self.assertEqual(submission.evidence.count(), 2)

    def test_self_reported_evaluation_fields_default_empty(self):
        submission = Submission.objects.create(obligation=self.obligation)
        self.assertIsNone(submission.director_rating)
        self.assertEqual(submission.director_name, "")
        self.assertEqual(submission.outcome, "")

    def test_self_reported_fields_accept_the_two_mockup_signals(self):
        """The star rating and the binary outcome are separate signals (spec §6)."""
        submission = Submission.objects.create(
            obligation=self.obligation,
            director_rating=4,
            director_name="John Dela Cruz",
            outcome=constants.OUTCOME_SATISFACTORY_OR_BETTER,
        )
        submission.refresh_from_db()
        self.assertEqual(submission.director_rating, 4)
        self.assertEqual(submission.outcome, constants.OUTCOME_SATISFACTORY_OR_BETTER)

    def test_str_names_the_obligation_and_revision(self):
        submission = Submission.objects.create(obligation=self.obligation)
        self.assertIn("rev 1", str(submission))
