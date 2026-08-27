"""The educator screens.

Beyond "does it render", these pin the three things the design actually
promises (spine spec §7.1): the most urgent obligation is surfaced as the one
next action, a teacher can never see or touch another teacher's work, and
errors come back as instructions rather than as rule names.
"""

import tempfile
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from step import constants, workflow
from step.models import Educator, Obligation, ObligationType, Region

MEDIA = tempfile.mkdtemp()
TODAY = date.today()


@override_settings(MEDIA_ROOT=MEDIA)
class EducatorScreenTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(
            full_name="Maria Santos", region=self.region, user=self.user, email="m@example.com"
        )
        self.monthly = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_FILE,
            requires_review=True,
        )
        self.eca = ObligationType.objects.create(
            name_template="ECA Plan", category=constants.CATEGORY_ECA,
            cadence=constants.CADENCE_TERMLY, evidence_spec=constants.EVIDENCE_LINK,
        )
        self.client.login(username="maria", password="pw")

    def make(self, obligation_type, days, status=constants.STATUS_NOT_STARTED, educator=None):
        due = TODAY + timedelta(days=days)
        return Obligation.objects.create(
            type=obligation_type, educator=educator or self.educator,
            period_kind=constants.PERIOD_MONTH,
            period_start=due.replace(day=1), due_date=due, status=status,
        )

    # --- Access ---------------------------------------------------------

    def test_dashboard_requires_signing_in(self):
        self.client.logout()
        response = self.client.get(reverse("step:dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_a_user_with_no_roster_row_is_told_rather_than_shown_a_blank_page(self):
        get_user_model().objects.create_user("stranger", password="pw")
        self.client.logout()
        self.client.login(username="stranger", password="pw")
        self.assertEqual(self.client.get(reverse("step:dashboard")).status_code, 404)

    # --- The one next action -------------------------------------------

    def test_the_most_urgent_obligation_is_the_one_offered(self):
        self.make(self.eca, 20)
        soonest = self.make(self.monthly, -2)
        response = self.client.get(reverse("step:dashboard"))
        self.assertEqual(response.context["next_item"]["obligation"], soonest)

    def test_nothing_outstanding_offers_no_next_action(self):
        self.make(self.monthly, -2, status=constants.STATUS_ACCEPTED)
        response = self.client.get(reverse("step:dashboard"))
        self.assertIsNone(response.context["next_item"])
        self.assertContains(response, "up to date")

    def test_outstanding_work_sorts_above_finished_work(self):
        self.make(self.monthly, -40, status=constants.STATUS_ACCEPTED)
        outstanding = self.make(self.eca, 25)
        response = self.client.get(reverse("step:dashboard"))
        self.assertEqual(response.context["items"][0]["obligation"], outstanding)

    # --- Filtering ------------------------------------------------------

    def test_category_filter_narrows_the_queue(self):
        self.make(self.monthly, 3)
        self.make(self.eca, 4)
        response = self.client.get(reverse("step:dashboard"), {"category": "eca"})
        self.assertEqual(len(response.context["items"]), 1)
        self.assertEqual(response.context["active_category"], "eca")

    def test_the_rail_marks_the_open_category_as_current(self):
        """The highlight must follow the filter.

        An earlier rail marked "All obligations" current for the whole section
        and gave the category links no aria-current at all, so the marker never
        moved when you opened a section.
        """
        self.make(self.eca, 4)
        body = self.client.get(reverse("step:dashboard"), {"category": "eca"}).content.decode()

        self.assertRegex(body, r'href="/step/\?category=eca"\s+aria-current="page"')
        # ...and "All obligations" must have surrendered it.
        self.assertNotRegex(body, r'href="/step/"\s+aria-current="page"')

    def test_the_rail_marks_all_obligations_current_when_unfiltered(self):
        self.make(self.eca, 4)
        body = self.client.get(reverse("step:dashboard")).content.decode()
        self.assertRegex(body, r'href="/step/"\s+aria-current="page"')

    def test_exactly_one_rail_link_is_current_at_a_time(self):
        self.make(self.monthly, 3)
        for query in [{}, {"category": "eca"}, {"category": "monthly_reporting"}]:
            body = self.client.get(reverse("step:dashboard"), query).content.decode()
            self.assertEqual(
                body.count('aria-current="page"'), 1,
                f"expected one current rail link for {query}",
            )

    def test_the_rail_offers_every_category(self):
        """Generated from the same list as the tabs, so the two cannot drift."""
        body = self.client.get(reverse("step:dashboard")).content.decode()
        for key, _label in constants.CATEGORY_CHOICES:
            self.assertIn(f'href="/step/?category={key}"', body)

    def test_the_rail_renders_on_pages_other_than_the_dashboard(self):
        """The rail needs `categories` everywhere, not just on the dashboard."""
        for name in ["step:submissions", "step:feedback"]:
            body = self.client.get(reverse(name)).content.decode()
            self.assertIn('href="/step/?category=eca"', body, f"rail incomplete on {name}")

    def test_an_unknown_category_is_ignored_rather_than_erroring(self):
        self.make(self.monthly, 3)
        response = self.client.get(reverse("step:dashboard"), {"category": "wizardry"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_category"], "")
        self.assertEqual(len(response.context["items"]), 1)

    # --- Isolation ------------------------------------------------------

    def test_a_teacher_cannot_open_another_teachers_obligation(self):
        other_user = get_user_model().objects.create_user("john", password="pw")
        other = Educator.objects.create(full_name="John", region=self.region, user=other_user)
        theirs = self.make(self.monthly, 3, educator=other)
        response = self.client.get(reverse("step:obligation", args=[theirs.pk]))
        self.assertEqual(response.status_code, 404)

    def test_a_teacher_cannot_submit_against_another_teachers_obligation(self):
        other_user = get_user_model().objects.create_user("john", password="pw")
        other = Educator.objects.create(full_name="John", region=self.region, user=other_user)
        theirs = self.make(self.monthly, 3, educator=other)
        response = self.client.post(reverse("step:obligation", args=[theirs.pk]), {})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(theirs.submissions.count(), 0)

    # --- Submitting -----------------------------------------------------

    def test_submitting_a_link_records_it(self):
        obligation = self.make(self.eca, 3)
        self.client.post(
            reverse("step:obligation", args=[obligation.pk]),
            {"link": "https://drive.example/plan"},
            follow=True,
        )
        obligation.refresh_from_db()
        self.assertEqual(obligation.status, constants.STATUS_ACCEPTED)
        self.assertEqual(obligation.latest_submission.evidence.count(), 1)

    def test_submitting_without_required_evidence_explains_what_to_do(self):
        obligation = self.make(self.eca, 3)
        response = self.client.post(
            reverse("step:obligation", args=[obligation.pk]), {}, follow=True
        )
        obligation.refresh_from_db()
        self.assertEqual(obligation.status, constants.STATUS_NOT_STARTED)
        body = response.content.decode()
        self.assertIn("Please add a link", body)
        # An instruction, not a rule name.
        self.assertNotIn("evidence_spec", body)
        self.assertNotIn("(s)", body)

    def test_the_form_disappears_once_something_is_awaiting_review(self):
        obligation = self.make(self.monthly, 3)
        workflow.submit(
            obligation, user=self.user,
            evidence=[{"kind": constants.EVIDENCE_FILE_KIND, "caption": "x"}],
        )
        response = self.client.get(reverse("step:obligation", args=[obligation.pk]))
        self.assertFalse(response.context["can_submit"])

    def test_evaluation_without_the_required_proof_is_refused_not_half_saved(self):
        """The stamped photo is the only verification the director data has
        (spec §5.10), so a rating with no proof must not be recorded at all."""
        obligation = self.make(self.monthly, 3)
        self.client.post(
            reverse("step:obligation", args=[obligation.pk]),
            {
                "director_rating": "4", "director_name": "John Dela Cruz",
                "outcome": constants.OUTCOME_SATISFACTORY_OR_BETTER,
            },
            follow=True,
        )
        obligation.refresh_from_db()
        self.assertEqual(obligation.status, constants.STATUS_NOT_STARTED)
        self.assertEqual(obligation.submissions.count(), 0)

    def test_self_reported_evaluation_is_stored_and_labelled_on_the_page(self):
        obligation = self.make(self.monthly, 3)
        self.client.post(
            reverse("step:obligation", args=[obligation.pk]),
            {
                "director_rating": "4", "director_name": "John Dela Cruz",
                "outcome": constants.OUTCOME_SATISFACTORY_OR_BETTER,
                "file": SimpleUploadedFile("stamp.jpg", b"jpeg", content_type="image/jpeg"),
            },
            follow=True,
        )
        obligation.refresh_from_db()
        submission = obligation.latest_submission
        self.assertEqual(submission.director_rating, 4)
        self.assertEqual(submission.director_name, "John Dela Cruz")

        response = self.client.get(reverse("step:obligation", args=[obligation.pk]))
        # It reaches a ministry, so it must never appear unlabelled.
        self.assertContains(response, "Entered by teacher")

    # --- Feedback -------------------------------------------------------

    def test_returned_work_appears_under_feedback_with_the_reason(self):
        obligation = self.make(self.monthly, 3)
        submission = workflow.submit(
            obligation, user=self.user,
            evidence=[{"kind": constants.EVIDENCE_FILE_KIND, "caption": "x"}],
        )
        workflow.return_for_correction(
            submission, reviewer=self.user, comment="The stamp is not visible."
        )
        response = self.client.get(reverse("step:feedback"))
        self.assertContains(response, "The stamp is not visible.")

    def test_feedback_is_empty_when_nothing_came_back(self):
        self.make(self.monthly, 3)
        response = self.client.get(reverse("step:feedback"))
        self.assertContains(response, "Nothing needs correcting")

    def test_the_menu_counts_items_needing_correction(self):
        obligation = self.make(self.monthly, 3)
        submission = workflow.submit(
            obligation, user=self.user,
            evidence=[{"kind": constants.EVIDENCE_FILE_KIND, "caption": "x"}],
        )
        workflow.return_for_correction(submission, reviewer=self.user, comment="Redo")
        response = self.client.get(reverse("step:dashboard"))
        self.assertEqual(response.context["returned_count"], 1)

    # --- Submissions ----------------------------------------------------

    def test_every_revision_is_listed_not_just_the_latest(self):
        obligation = self.make(self.monthly, 3)
        first = workflow.submit(
            obligation, user=self.user,
            evidence=[{"kind": constants.EVIDENCE_FILE_KIND, "caption": "x"}],
        )
        workflow.return_for_correction(first, reviewer=self.user, comment="Redo")
        workflow.submit(
            obligation, user=self.user,
            evidence=[{"kind": constants.EVIDENCE_FILE_KIND, "caption": "y"}],
        )
        response = self.client.get(reverse("step:submissions"))
        self.assertEqual(len(response.context["rows"]), 2)

    def test_submissions_page_is_empty_before_anything_is_sent(self):
        response = self.client.get(reverse("step:submissions"))
        self.assertContains(response, "Nothing sent yet")


@override_settings(MEDIA_ROOT=MEDIA)
class TemplateHygieneTests(TestCase):
    """Django's {# #} comment is single-line only; a multi-line one renders as
    visible text. That happened once and must not happen again."""

    def setUp(self):
        region = Region.objects.create(name="Samarkand", code="samarkand")
        user = get_user_model().objects.create_user("maria", password="pw")
        Educator.objects.create(full_name="Maria Santos", region=region, user=user)
        self.client.login(username="maria", password="pw")

    def test_no_template_comment_syntax_reaches_the_page(self):
        for name in ["step:dashboard", "step:submissions", "step:feedback"]:
            body = self.client.get(reverse(name)).content.decode()
            self.assertNotIn("{#", body, f"raw comment leaked on {name}")
            self.assertNotIn("{% comment", body, f"raw comment leaked on {name}")
            self.assertNotIn("endcomment", body, f"raw comment leaked on {name}")
