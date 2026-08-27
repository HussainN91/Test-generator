"""State transitions live in one module so no view can invent its own.

The rules that matter: evidence requirements are enforced at submit time
(spec §5.7); a type with requires_review=False accepts immediately (spec §5.9);
returning sends the obligation back to the teacher and resubmitting bumps the
revision rather than editing history (spec §5.8).
"""

import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from step import constants, workflow
from step.models import (
    Educator, Obligation, ObligationType, ProgressEntry, Region, Student, Submission,
    TeachingClass,
)

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class SubmitTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.user = get_user_model().objects.create_user("maria", password="x")
        self.educator.user = self.user
        self.educator.save()

    def make_obligation(self, evidence_spec, requires_review=False, min_count=1):
        obligation_type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=evidence_spec,
            requires_review=requires_review, min_count=min_count,
        )
        return Obligation.objects.create(
            type=obligation_type, educator=self.educator, period_kind=constants.PERIOD_MONTH,
            period_start=date(2026, 5, 1), due_date=date(2026, 5, 27),
        )

    def test_submitting_with_no_evidence_when_none_is_required_succeeds(self):
        obligation = self.make_obligation(constants.EVIDENCE_NONE)
        submission = workflow.submit(obligation, user=self.user, evidence=[])
        obligation.refresh_from_db()
        self.assertEqual(submission.revision, 1)
        self.assertEqual(obligation.status, constants.STATUS_ACCEPTED)

    def test_a_link_requirement_rejects_a_file_only_submission(self):
        obligation = self.make_obligation(constants.EVIDENCE_LINK)
        with self.assertRaises(workflow.EvidenceRequired):
            workflow.submit(
                obligation, user=self.user,
                evidence=[{"kind": constants.EVIDENCE_FILE_KIND, "file": None, "caption": "x"}],
            )

    def test_either_accepts_a_link_alone(self):
        obligation = self.make_obligation(constants.EVIDENCE_EITHER)
        submission = workflow.submit(
            obligation, user=self.user,
            evidence=[{"kind": constants.EVIDENCE_LINK_KIND, "url": "https://x.example"}],
        )
        self.assertEqual(submission.evidence.count(), 1)

    def test_both_requires_a_link_and_a_file(self):
        obligation = self.make_obligation(constants.EVIDENCE_BOTH)
        with self.assertRaises(workflow.EvidenceRequired):
            workflow.submit(
                obligation, user=self.user,
                evidence=[{"kind": constants.EVIDENCE_LINK_KIND, "url": "https://x.example"}],
            )

    def test_min_count_is_enforced(self):
        obligation = self.make_obligation(constants.EVIDENCE_LINK, min_count=2)
        with self.assertRaises(workflow.EvidenceRequired):
            workflow.submit(
                obligation, user=self.user,
                evidence=[{"kind": constants.EVIDENCE_LINK_KIND, "url": "https://x.example"}],
            )

    def test_a_type_requiring_review_lands_in_the_queue(self):
        obligation = self.make_obligation(constants.EVIDENCE_NONE, requires_review=True)
        workflow.submit(obligation, user=self.user, evidence=[])
        obligation.refresh_from_db()
        self.assertEqual(obligation.status, constants.STATUS_SUBMITTED)

    def test_self_reported_evaluation_is_stored_on_the_submission(self):
        obligation = self.make_obligation(constants.EVIDENCE_NONE, requires_review=True)
        submission = workflow.submit(
            obligation, user=self.user, evidence=[],
            evaluation={
                "director_rating": 4,
                "director_name": "John Dela Cruz",
                "outcome": constants.OUTCOME_SATISFACTORY_OR_BETTER,
            },
        )
        self.assertEqual(submission.director_rating, 4)
        self.assertEqual(submission.outcome, constants.OUTCOME_SATISFACTORY_OR_BETTER)

    def test_submitting_an_already_accepted_obligation_is_refused(self):
        obligation = self.make_obligation(constants.EVIDENCE_NONE)
        workflow.submit(obligation, user=self.user, evidence=[])
        with self.assertRaises(workflow.InvalidTransition):
            workflow.submit(obligation, user=self.user, evidence=[])


@override_settings(MEDIA_ROOT=MEDIA)
class ReviewTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.teacher = get_user_model().objects.create_user("maria", password="x")
        self.educator.user = self.teacher
        self.educator.save()
        self.admin = get_user_model().objects.create_user("admin2", password="x")

        obligation_type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
            requires_review=True,
        )
        self.obligation = Obligation.objects.create(
            type=obligation_type, educator=self.educator, period_kind=constants.PERIOD_MONTH,
            period_start=date(2026, 5, 1), due_date=date(2026, 5, 27),
        )
        self.submission = workflow.submit(self.obligation, user=self.teacher, evidence=[])

    def test_accepting_settles_the_obligation(self):
        workflow.accept(self.submission, reviewer=self.admin)
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_ACCEPTED)
        self.assertEqual(self.submission.reviewed_by, self.admin)
        self.assertIsNotNone(self.submission.reviewed_at)

    def test_returning_sends_it_back_with_a_comment(self):
        workflow.retur_n = None  # guard against a typo'd name in implementation
        workflow.return_for_correction(
            self.submission, reviewer=self.admin, comment="Stamp not visible."
        )
        self.obligation.refresh_from_db()
        self.submission.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_RETURNED)
        self.assertEqual(self.submission.review_comment, "Stamp not visible.")

    def test_returning_without_a_comment_is_refused(self):
        with self.assertRaises(ValueError):
            workflow.return_for_correction(self.submission, reviewer=self.admin, comment="  ")

    def test_resubmitting_after_a_return_bumps_the_revision(self):
        workflow.return_for_correction(self.submission, reviewer=self.admin, comment="Redo")
        second = workflow.submit(self.obligation, user=self.teacher, evidence=[])
        self.assertEqual(second.revision, 2)
        self.assertEqual(Submission.objects.filter(obligation=self.obligation).count(), 2)

    def test_the_first_revision_survives_a_resubmission(self):
        workflow.return_for_correction(self.submission, reviewer=self.admin, comment="Redo")
        workflow.submit(self.obligation, user=self.teacher, evidence=[])
        first = Submission.objects.get(obligation=self.obligation, revision=1)
        self.assertEqual(first.review_comment, "Redo")

    def test_accepting_an_already_accepted_submission_is_refused(self):
        workflow.accept(self.submission, reviewer=self.admin)
        with self.assertRaises(workflow.InvalidTransition):
            workflow.accept(self.submission, reviewer=self.admin)


class ReviewQueueTests(TestCase):
    def test_the_queue_holds_only_submissions_awaiting_a_decision(self):
        region = Region.objects.create(name="Samarkand", code="samarkand")
        educator = Educator.objects.create(full_name="Maria Santos", region=region)
        needs = ObligationType.objects.create(
            name_template="Needs review", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
            requires_review=True,
        )
        auto = ObligationType.objects.create(
            name_template="Auto accepted", category=constants.CATEGORY_OTHER,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
        )
        for obligation_type in (needs, auto):
            obligation = Obligation.objects.create(
                type=obligation_type, educator=educator, period_kind=constants.PERIOD_MONTH,
                period_start=date(2026, 5, 1), due_date=date(2026, 5, 27),
            )
            workflow.submit(obligation, user=None, evidence=[])

        queue = workflow.review_queue()
        self.assertEqual(queue.count(), 1)
        self.assertEqual(queue.first().obligation.type, needs)


class SyncCheckpointTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.teaching_class = TeachingClass.objects.create(
            educator=self.educator, grade=9, slot=1, display_name="9A"
        )
        self.a = Student.objects.create(teaching_class=self.teaching_class, full_name="Aziz Karimov")
        self.b = Student.objects.create(teaching_class=self.teaching_class, full_name="Dilnoza Yusupova")

        self.boy_type = ObligationType.objects.create(
            name_template="Beginning-of-year diagnostic", category=constants.CATEGORY_ASSESSMENTS,
            cadence=constants.CADENCE_ANNUAL, evidence_spec=constants.EVIDENCE_NONE,
            form_slug=constants.FORM_SLUG_ASSESSMENT_CHECKPOINT,
        )
        self.obligation = Obligation.objects.create(
            type=self.boy_type, educator=self.educator, teaching_class=self.teaching_class,
            period_kind=constants.PERIOD_YEAR, period_start=date(2025, 9, 1), due_date=date(2025, 10, 1),
        )

    def test_incomplete_class_does_not_settle_the_obligation(self):
        ProgressEntry.objects.create(student=self.a, checkpoint=constants.CHECKPOINT_BOY, score=80)
        workflow.sync_checkpoint(self.teaching_class, constants.CHECKPOINT_BOY)
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_NOT_STARTED)

    def test_every_student_scored_settles_the_obligation(self):
        ProgressEntry.objects.create(student=self.a, checkpoint=constants.CHECKPOINT_BOY, score=80)
        ProgressEntry.objects.create(student=self.b, checkpoint=constants.CHECKPOINT_BOY, score=74)
        workflow.sync_checkpoint(self.teaching_class, constants.CHECKPOINT_BOY)
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_ACCEPTED)

    def test_settling_creates_no_submission(self):
        ProgressEntry.objects.create(student=self.a, checkpoint=constants.CHECKPOINT_BOY, score=80)
        ProgressEntry.objects.create(student=self.b, checkpoint=constants.CHECKPOINT_BOY, score=74)
        workflow.sync_checkpoint(self.teaching_class, constants.CHECKPOINT_BOY)
        self.assertEqual(self.obligation.submissions.count(), 0)

    def test_a_different_checkpoint_does_not_settle_this_one(self):
        ProgressEntry.objects.create(student=self.a, checkpoint=constants.CHECKPOINT_MOY, score=80)
        ProgressEntry.objects.create(student=self.b, checkpoint=constants.CHECKPOINT_MOY, score=74)
        workflow.sync_checkpoint(self.teaching_class, constants.CHECKPOINT_MOY)
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_NOT_STARTED)

    def test_a_class_with_no_students_never_settles(self):
        empty = TeachingClass.objects.create(educator=self.educator, grade=9, slot=2, display_name="9B")
        Obligation.objects.create(
            type=self.boy_type, educator=self.educator, teaching_class=empty,
            period_kind=constants.PERIOD_YEAR, period_start=date(2025, 9, 1), due_date=date(2025, 10, 1),
        )
        result = workflow.sync_checkpoint(empty, constants.CHECKPOINT_BOY)
        self.assertIsNone(result)

    def test_freeform_notes_do_not_count_toward_completion(self):
        ProgressEntry.objects.create(student=self.a, checkpoint=constants.CHECKPOINT_BOY, score=80)
        ProgressEntry.objects.create(student=self.b, comment="A freeform note, no checkpoint.")
        workflow.sync_checkpoint(self.teaching_class, constants.CHECKPOINT_BOY)
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_NOT_STARTED)
