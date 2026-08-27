"""Admin-facing screens: the action-queue dashboard, the review workflow, and
the teacher directory. Gated to the three staff roles (spec §5.6); an
Educator or an anonymous visitor must never reach any of it.
"""

from datetime import date
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from step import constants, roles
from step.models import Educator, Evidence, Obligation, ObligationType, Region, Submission


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
        # One obligation -> singular. This assertion originally read "have
        # not submitted" and passed only because the verb never agreed with
        # the count at all; see ActionQueueGrammarTests for both cases.
        self._obligation(date(2026, 5, 27))
        response = self.client.get(reverse("step:admin-dashboard") + "?period=2026-05")
        self.assertContains(response, "has not submitted")

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


class ReviewQueueTests(TestCase):
    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        user = get_user_model().objects.create_user("admin1", password="pw")
        roles.assign(user, constants.ROLE_ADMIN)
        self.client.login(username="admin1", password="pw")
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
        )
        self.educator = Educator.objects.create(full_name="Teacher One", region=self.region)
        self.obligation = Obligation.objects.create(
            type=self.type, educator=self.educator, period_kind=constants.PERIOD_MONTH,
            period_start=date(2026, 5, 1), due_date=date(2026, 5, 27),
            status=constants.STATUS_SUBMITTED,
        )
        from step.models import Submission
        self.submission = Submission.objects.create(obligation=self.obligation, revision=1)

    def test_the_queue_lists_waiting_submissions(self):
        response = self.client.get(reverse("step:admin-review-queue"))
        self.assertContains(response, "Teacher One")

    def test_an_empty_queue_says_so_plainly(self):
        self.submission.delete()
        self.obligation.status = constants.STATUS_ACCEPTED
        self.obligation.save()
        response = self.client.get(reverse("step:admin-review-queue"))
        self.assertContains(response, "Nothing is waiting")

    def test_review_detail_shows_the_evidence_and_the_two_actions(self):
        response = self.client.get(reverse("step:admin-review-detail", args=[self.submission.pk]))
        self.assertContains(response, "Accept")
        self.assertContains(response, "Return")

    def test_accepting_marks_the_obligation_accepted(self):
        self.client.post(
            reverse("step:admin-review-detail", args=[self.submission.pk]),
            {"action": "accept"},
        )
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_ACCEPTED)

    def test_returning_without_a_comment_shows_a_plain_language_error_not_a_500(self):
        response = self.client.post(
            reverse("step:admin-review-detail", args=[self.submission.pk]),
            {"action": "return", "comment": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_SUBMITTED)

    def test_returning_with_a_comment_sends_it_back_to_the_teacher(self):
        self.client.post(
            reverse("step:admin-review-detail", args=[self.submission.pk]),
            {"action": "return", "comment": "Please attach the stamped page."},
        )
        self.obligation.refresh_from_db()
        self.submission.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_RETURNED)
        self.assertEqual(self.submission.review_comment, "Please attach the stamped page.")


class TeacherDirectoryTests(TestCase):
    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        user = get_user_model().objects.create_user("admin1", password="pw")
        roles.assign(user, constants.ROLE_ADMIN)
        self.client.login(username="admin1", password="pw")
        self.samarkand = Region.objects.create(name="Samarkand", code="samarkand")
        self.tashkent = Region.objects.create(name="Tashkent City", code="tashkent-city")
        Educator.objects.create(full_name="Maria Santos", region=self.samarkand)
        Educator.objects.create(full_name="John Okafor", region=self.tashkent)

    def test_the_directory_lists_all_teachers(self):
        response = self.client.get(reverse("step:admin-teachers"))
        self.assertContains(response, "Maria Santos")
        self.assertContains(response, "John Okafor")

    def test_search_narrows_by_name(self):
        response = self.client.get(reverse("step:admin-teachers") + "?q=Maria")
        self.assertContains(response, "Maria Santos")
        self.assertNotContains(response, "John Okafor")

    def test_region_filter_narrows_results(self):
        response = self.client.get(reverse("step:admin-teachers") + f"?region={self.tashkent.pk}")
        self.assertContains(response, "John Okafor")
        self.assertNotContains(response, "Maria Santos")

    def test_the_outstanding_status_filter_only_shows_teachers_with_something_due(self):
        obligation_type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
        )
        Obligation.objects.create(
            type=obligation_type, educator=Educator.objects.get(full_name="Maria Santos"),
            period_kind=constants.PERIOD_MONTH, period_start=date(2026, 5, 1),
            due_date=date(2026, 5, 27),
        )
        response = self.client.get(
            reverse("step:admin-teachers") + "?status=outstanding&period=2026-05"
        )
        self.assertContains(response, "Maria Santos")
        self.assertNotContains(response, "John Okafor")

    def test_passport_and_pinfl_never_appear(self):
        Educator.objects.create(
            full_name="Secret Person", region=self.samarkand,
            passport_no="AB1234567", pinfl="12345678901234",
        )
        response = self.client.get(reverse("step:admin-teachers"))
        self.assertNotContains(response, "AB1234567")
        self.assertNotContains(response, "12345678901234")

    def test_a_teachers_row_links_to_their_file(self):
        educator = Educator.objects.get(full_name="Maria Santos")
        response = self.client.get(reverse("step:admin-teachers"))
        self.assertContains(response, reverse("step:admin-teacher-detail", args=[educator.pk]))

    def test_the_teacher_file_lists_their_obligations_with_teacher_facing_wording(self):
        obligation_type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
        )
        educator = Educator.objects.get(full_name="Maria Santos")
        Obligation.objects.create(
            type=obligation_type, educator=educator, period_kind=constants.PERIOD_MONTH,
            period_start=date(2026, 5, 1), due_date=date(2020, 1, 1),
        )
        response = self.client.get(reverse("step:admin-teacher-detail", args=[educator.pk]))
        self.assertContains(response, "late")


class ActionQueueLinkTests(TestCase):
    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        user = get_user_model().objects.create_user("admin1", password="pw")
        roles.assign(user, constants.ROLE_ADMIN)
        self.client.login(username="admin1", password="pw")
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
        )
        Obligation.objects.create(
            type=self.type,
            educator=Educator.objects.create(full_name="Teacher One", region=self.region),
            period_kind=constants.PERIOD_MONTH, period_start=date(2026, 5, 1),
            due_date=date(2026, 5, 27),
        )

    def test_the_dashboards_outstanding_link_lands_on_a_directory_that_shows_that_teacher(self):
        dashboard = self.client.get(reverse("step:admin-dashboard") + "?period=2026-05")
        self.assertContains(dashboard, "status=outstanding&period=2026-05")
        directory = self.client.get(
            reverse("step:admin-teachers") + "?status=outstanding&period=2026-05"
        )
        self.assertContains(directory, "Teacher One")


class EvidenceRenderingTests(TestCase):
    """The review screen must survive every Evidence row the schema allows.

    `Evidence.file` is `blank=True`, so a row may legally carry `kind="file"`
    and no file at all — `seed_demo` produces exactly that. Django's template
    engine silences AttributeError and friends, but **not** the ValueError
    that `FieldFile.url` raises on an empty file, so an unguarded
    `{{ item.file.url }}` takes the whole page down with a 500.

    The original review tests all built submissions with no evidence, so they
    rendered the `{% empty %}` branch and never touched the line that breaks.
    These fixtures render a real row on purpose.
    """

    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        user = get_user_model().objects.create_user("admin1", password="pw")
        roles.assign(user, constants.ROLE_ADMIN)
        self.client.login(username="admin1", password="pw")
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
        )
        self.educator = Educator.objects.create(full_name="Teacher One", region=self.region)
        self.obligation = Obligation.objects.create(
            type=self.type, educator=self.educator, period_kind=constants.PERIOD_MONTH,
            period_start=date(2026, 5, 1), due_date=date(2026, 5, 27),
            status=constants.STATUS_SUBMITTED,
        )
        self.submission = Submission.objects.create(obligation=self.obligation, revision=1)

    def _url(self):
        return reverse("step:admin-review-detail", args=[self.submission.pk])

    def test_a_file_row_with_no_file_attached_renders_instead_of_500ing(self):
        """The exact shape `seed_demo` writes, and the one that crashed."""
        Evidence.objects.create(
            submission=self.submission, kind=constants.EVIDENCE_FILE_KIND,
            url="", caption="stamped-report.jpg",
        )
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "stamped-report.jpg")

    def test_a_file_row_with_no_file_says_so_rather_than_offering_a_dead_link(self):
        """A caption alone must not be dressed up as a working download."""
        Evidence.objects.create(
            submission=self.submission, kind=constants.EVIDENCE_FILE_KIND,
            url="", caption="stamped-report.jpg",
        )
        response = self.client.get(self._url())
        self.assertContains(response, "no file was attached")

    def test_a_file_row_with_a_real_file_still_links_to_it(self):
        Evidence.objects.create(
            submission=self.submission, kind=constants.EVIDENCE_FILE_KIND,
            file=SimpleUploadedFile("stamped.jpg", b"jpegbytes"), caption="Stamped page",
        )
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Stamped page")
        self.assertContains(response, "stamped")

    def test_a_link_row_still_links_to_its_url(self):
        Evidence.objects.create(
            submission=self.submission, kind=constants.EVIDENCE_LINK_KIND,
            url="https://drive.example.com/report", caption="Report",
        )
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "https://drive.example.com/report")

    def test_returning_without_a_comment_re_renders_even_with_a_fileless_row(self):
        """The error path re-renders the page, so it hits the same template.

        The pre-existing version of this test used an evidence-free
        submission, which is why a 500 here went unnoticed.
        """
        Evidence.objects.create(
            submission=self.submission, kind=constants.EVIDENCE_FILE_KIND,
            url="", caption="stamped-report.jpg",
        )
        response = self.client.post(self._url(), {"action": "return", "comment": ""})
        self.assertEqual(response.status_code, 200)
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_SUBMITTED)


class DirectoryFilterRobustnessTests(TestCase):
    """`?region=` arrives from a URL and may be anything at all.

    The neighbouring `?period=` and `?page=` parameters are both defended;
    `?region=` was not, and a non-numeric value reached `filter(region_id=...)`
    where it raised ValueError as a 500.
    """

    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        user = get_user_model().objects.create_user("admin1", password="pw")
        roles.assign(user, constants.ROLE_ADMIN)
        self.client.login(username="admin1", password="pw")
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        Educator.objects.create(full_name="Teacher One", region=self.region)

    def test_a_non_numeric_region_is_not_a_500(self):
        response = self.client.get(reverse("step:admin-teachers") + "?region=abc")
        self.assertEqual(response.status_code, 200)

    def test_a_non_numeric_region_is_ignored_rather_than_hiding_everyone(self):
        """A junk filter must not silently read as "nobody matched"."""
        response = self.client.get(reverse("step:admin-teachers") + "?region=abc")
        self.assertContains(response, "Teacher One")

    def test_an_unknown_but_numeric_region_still_narrows_to_nothing(self):
        response = self.client.get(reverse("step:admin-teachers") + "?region=999999")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Teacher One")

    def test_a_real_region_still_filters(self):
        response = self.client.get(
            reverse("step:admin-teachers") + f"?region={self.region.pk}"
        )
        self.assertContains(response, "Teacher One")


class ActionQueueGrammarTests(TestCase):
    """These sentences reach a ministry-facing screen, so they have to read
    like English at every count, not just the plural case."""

    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        user = get_user_model().objects.create_user("admin1", password="pw")
        roles.assign(user, constants.ROLE_ADMIN)
        self.client.login(username="admin1", password="pw")
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
        )

    def _outstanding(self, how_many):
        for n in range(how_many):
            Obligation.objects.create(
                type=self.type,
                educator=Educator.objects.create(full_name=f"Teacher {n}", region=self.region),
                period_kind=constants.PERIOD_MONTH, period_start=date(2026, 5, 1),
                due_date=date(2026, 5, 27),
            )

    def test_one_teacher_takes_a_singular_verb(self):
        self._outstanding(1)
        response = self.client.get(reverse("step:admin-dashboard") + "?period=2026-05")
        self.assertContains(response, "1 teacher has not submitted")

    def test_several_teachers_take_a_plural_verb(self):
        self._outstanding(2)
        response = self.client.get(reverse("step:admin-dashboard") + "?period=2026-05")
        self.assertContains(response, "2 teachers have not submitted")
