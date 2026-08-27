"""Admin-facing screens: the action-queue dashboard, the review workflow, and
the teacher directory. Gated to the three staff roles (spec §5.6); an
Educator or an anonymous visitor must never reach any of it.
"""

from datetime import date
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from step import constants, roles
from step.models import Educator, Obligation, ObligationType, Region


class AccessControlTests(TestCase):
    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        self.region = Region.objects.create(name="Samarkand", code="samarkand")

    def _staff(self, username, role=constants.ROLE_ADMIN):
        user = get_user_model().objects.create_user(username, password="pw")
        roles.assign(user, role)
        return user

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse("step:admin-dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_an_educator_is_forbidden(self):
        user = get_user_model().objects.create_user("maria", password="pw")
        roles.assign(user, constants.ROLE_EDUCATOR)
        Educator.objects.create(full_name="Maria Santos", region=self.region, user=user)
        self.client.login(username="maria", password="pw")
        response = self.client.get(reverse("step:admin-dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_a_signed_in_user_with_no_role_at_all_is_forbidden(self):
        get_user_model().objects.create_user("nobody", password="pw")
        self.client.login(username="nobody", password="pw")
        response = self.client.get(reverse("step:admin-dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_each_of_the_three_staff_roles_is_admitted(self):
        for i, role in enumerate(
            [constants.ROLE_ADMIN, constants.ROLE_PROGRAMME_ADMIN, constants.ROLE_SYSTEM_ADMIN]
        ):
            self._staff(f"staff{i}", role)
            self.client.login(username=f"staff{i}", password="pw")
            response = self.client.get(reverse("step:admin-dashboard"))
            self.assertEqual(response.status_code, 200, f"{role} was refused the dashboard")
            self.client.logout()


class DashboardShellTests(TestCase):
    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        user = get_user_model().objects.create_user("admin1", password="pw")
        roles.assign(user, constants.ROLE_ADMIN)
        self.client.login(username="admin1", password="pw")

    def test_dashboard_renders_the_letterhead_and_admin_rail(self):
        response = self.client.get(reverse("step:admin-dashboard"))
        self.assertContains(response, "STEP")
        self.assertContains(response, "Administration")

    def test_dashboard_shows_the_signed_in_staff_members_name(self):
        response = self.client.get(reverse("step:admin-dashboard"))
        self.assertContains(response, "admin1")


class ActionQueueTests(TestCase):
    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        user = get_user_model().objects.create_user("admin1", password="pw")
        roles.assign(user, constants.ROLE_ADMIN)
        self.client.login(username="admin1", password="pw")

        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
            requires_review=True,
        )

    def _obligation(self, due, status=constants.STATUS_NOT_STARTED):
        educator = Educator.objects.create(
            full_name=f"Teacher {Educator.objects.count() + 1}", region=self.region
        )
        return Obligation.objects.create(
            type=self.type, educator=educator, period_kind=constants.PERIOD_MONTH,
            period_start=date(2026, 5, 1), due_date=due, status=status,
        )

    def test_the_outstanding_count_reaches_the_dashboard(self):
        self._obligation(date(2026, 5, 27))
        self._obligation(date(2026, 5, 27))
        response = self.client.get(reverse("step:admin-dashboard") + "?period=2026-05")
        self.assertEqual(response.context["outstanding_count"], 2)

    def test_the_review_queue_count_reaches_the_dashboard(self):
        submitted = self._obligation(date(2026, 5, 27), status=constants.STATUS_SUBMITTED)
        from step.models import Submission
        Submission.objects.create(obligation=submitted, revision=1)
        response = self.client.get(reverse("step:admin-dashboard"))
        self.assertEqual(response.context["review_count"], 1)

    def test_headline_figures_come_from_submission_status(self):
        self._obligation(date(2026, 5, 27))
        response = self.client.get(reverse("step:admin-dashboard") + "?period=2026-05")
        self.assertEqual(response.context["headline"]["total"], 1)

    def test_the_action_queue_wording_is_on_the_page(self):
        self._obligation(date(2026, 5, 27))
        response = self.client.get(reverse("step:admin-dashboard") + "?period=2026-05")
        self.assertContains(response, "have not submitted")

    def test_a_malformed_period_is_a_404_not_a_500(self):
        response = self.client.get(reverse("step:admin-dashboard") + "?period=not-a-month")
        self.assertEqual(response.status_code, 404)


class AnalyticsWidgetsTests(TestCase):
    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        user = get_user_model().objects.create_user("admin1", password="pw")
        roles.assign(user, constants.ROLE_ADMIN)
        self.client.login(username="admin1", password="pw")
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
            requires_review=True,
        )
        educator = Educator.objects.create(full_name="Teacher One", region=self.region)
        obligation = Obligation.objects.create(
            type=self.type, educator=educator, period_kind=constants.PERIOD_MONTH,
            period_start=date(2026, 5, 1), due_date=date(2026, 5, 27),
        )
        self.obligation = obligation

    def test_all_widget_context_keys_are_present(self):
        response = self.client.get(reverse("step:admin-dashboard") + "?period=2026-05")
        for key in [
            "region_bars", "rating_donut", "outcome_donut", "trend_points", "trend_width",
            "status_rows", "timeliness", "completeness_rate",
        ]:
            self.assertIn(key, response.context, f"{key} missing from dashboard context")

    def test_a_region_bar_carries_a_precomputed_percent(self):
        response = self.client.get(reverse("step:admin-dashboard") + "?period=2026-05")
        bars = response.context["region_bars"]
        self.assertEqual(bars[0]["percent"], 100.0)

    def test_self_reported_widgets_are_labelled_on_the_page(self):
        response = self.client.get(reverse("step:admin-dashboard") + "?period=2026-05")
        self.assertContains(response, "chart--selfreported")

    def test_donut_segments_have_dasharray_and_dashoffset(self):
        from step import workflow
        workflow.submit(
            self.obligation, user=get_user_model().objects.get(username="admin1"),
            evidence=[], evaluation={"director_rating": 5},
        )
        response = self.client.get(reverse("step:admin-dashboard") + "?period=2026-05")
        segment = response.context["rating_donut"][0]
        self.assertIn("dasharray", segment)
        self.assertIn("dashoffset", segment)

    def test_changing_the_period_changes_the_headline_and_the_widgets_together(self):
        may = self.client.get(reverse("step:admin-dashboard") + "?period=2026-05")
        june = self.client.get(reverse("step:admin-dashboard") + "?period=2026-06")
        self.assertEqual(may.context["headline"]["total"], 1)
        self.assertEqual(june.context["headline"]["total"], 0)
        self.assertNotEqual(len(may.context["trend_points"]), 0)
