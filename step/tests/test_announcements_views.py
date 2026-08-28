"""The teacher's side of the CPD Online vertical.

There is no obligation, no evidence and no review here, so the only things
worth pinning are the ones that could actually go wrong: an answer must never
duplicate (the unique constraint), a closed announcement must genuinely refuse
the write rather than merely hide its button, and one teacher must never see or
overwrite another's answer.
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from step.models import Announcement, AnnouncementResponse, Educator, Region

TODAY = date.today()


class AnnouncementScreenTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(
            full_name="Maria Santos", region=self.region, user=self.user, email="m@example.com"
        )
        self.client.force_login(self.user)

    def make(self, **kwargs):
        fields = {"title": "October CPD webinar", "body": "Join on Zoom at 15:00."}
        fields.update(kwargs)
        return Announcement.objects.create(**fields)

    def other_teacher(self):
        user = get_user_model().objects.create_user("jonas", password="pw")
        return Educator.objects.create(
            full_name="Jonas Weber", region=self.region, user=user, email="j@example.com"
        )

    # --- The dashboard ---------------------------------------------------

    def test_the_dashboard_shows_an_active_announcement(self):
        self.make()
        response = self.client.get(reverse("step:dashboard"))
        self.assertContains(response, "October CPD webinar")
        self.assertContains(response, 'id="ann-h"')

    def test_the_dashboard_does_not_show_a_withdrawn_announcement(self):
        self.make(is_active=False)
        response = self.client.get(reverse("step:dashboard"))
        self.assertNotContains(response, "October CPD webinar")
        self.assertEqual(response.context["announcements"], [])

    def test_no_announcements_means_no_section_at_all(self):
        response = self.client.get(reverse("step:dashboard"))
        self.assertNotContains(response, 'id="ann-h"')
        self.assertEqual(response.context["announcements"], [])

    def test_an_unanswered_announcement_that_asks_for_one_needs_an_answer(self):
        self.make(requires_response=True)
        response = self.client.get(reverse("step:dashboard"))
        row = response.context["announcements"][0]
        self.assertTrue(row["needs_answer"])
        self.assertIsNone(row["response"])
        self.assertContains(response, "Needs your answer")

    def test_an_already_answered_announcement_does_not_need_an_answer(self):
        announcement = self.make(requires_response=True)
        AnnouncementResponse.objects.create(
            announcement=announcement, educator=self.educator, attending=True
        )
        response = self.client.get(reverse("step:dashboard"))
        row = response.context["announcements"][0]
        self.assertFalse(row["needs_answer"])
        self.assertTrue(row["response"].attending)
        self.assertNotContains(response, "Needs your answer")

    def test_pure_news_never_needs_an_answer(self):
        self.make(requires_response=False)
        response = self.client.get(reverse("step:dashboard"))
        self.assertFalse(response.context["announcements"][0]["needs_answer"])

    def test_the_docket_still_leads_on_obligations(self):
        """An announcement must not displace the one unmissable element."""
        self.make(requires_response=True)
        response = self.client.get(reverse("step:dashboard"))
        self.assertIsNone(response.context["next_item"])
        self.assertContains(response, "up to date")

    def test_more_announcements_do_not_cost_more_queries(self):
        """The N+1 guard: responses are fetched once, not once per announcement."""
        def render_cost():
            with CaptureQueriesContext(connection) as captured:
                self.client.get(reverse("step:dashboard"))
            return len(captured)

        announcement = self.make(title="Session 0", requires_response=True)
        AnnouncementResponse.objects.create(
            announcement=announcement, educator=self.educator, attending=True
        )
        one = render_cost()

        for index in range(1, 5):
            extra = self.make(title=f"Session {index}", requires_response=True)
            AnnouncementResponse.objects.create(
                announcement=extra, educator=self.educator, attending=True
            )
        self.assertEqual(render_cost(), one)

    # --- The announcements page ------------------------------------------

    def test_the_list_renders_for_a_signed_in_teacher(self):
        self.make(body="Join on Zoom at 15:00.")
        response = self.client.get(reverse("step:announcements"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Join on Zoom at 15:00.")

    def test_the_list_requires_signing_in(self):
        self.client.logout()
        response = self.client.get(reverse("step:announcements"))
        self.assertEqual(response.status_code, 302)

    def test_the_list_offers_the_rsvp_only_where_one_is_asked_for(self):
        self.make(requires_response=True)
        response = self.client.get(reverse("step:announcements"))
        self.assertContains(response, "I will attend")

        Announcement.objects.all().delete()
        self.make(requires_response=False)
        response = self.client.get(reverse("step:announcements"))
        self.assertNotContains(response, "I will attend")

    def test_a_returning_teacher_sees_which_answer_they_picked(self):
        announcement = self.make(requires_response=True)
        AnnouncementResponse.objects.create(
            announcement=announcement, educator=self.educator, attending=False
        )
        response = self.client.get(reverse("step:announcements"))
        self.assertFalse(response.context["rows"][0]["response"].attending)
        self.assertContains(response, "You said you will not attend")

    # --- Answering --------------------------------------------------------

    def test_answering_records_one_row(self):
        announcement = self.make(requires_response=True)
        response = self.client.post(
            reverse("step:announcement_respond", args=[announcement.pk]), {"attending": "yes"}
        )
        self.assertEqual(response.status_code, 302)
        rows = AnnouncementResponse.objects.filter(announcement=announcement)
        self.assertEqual(rows.count(), 1)
        self.assertTrue(rows.first().attending)
        self.assertEqual(rows.first().educator, self.educator)

    def test_changing_the_answer_updates_the_same_row(self):
        announcement = self.make(requires_response=True)
        url = reverse("step:announcement_respond", args=[announcement.pk])
        self.client.post(url, {"attending": "yes"})
        self.client.post(url, {"attending": "no"})
        rows = AnnouncementResponse.objects.filter(announcement=announcement, educator=self.educator)
        self.assertEqual(rows.count(), 1)
        self.assertFalse(rows.first().attending)

    def test_an_answer_is_still_possible_on_the_last_day(self):
        announcement = self.make(requires_response=True, respond_by=TODAY)
        self.client.post(
            reverse("step:announcement_respond", args=[announcement.pk]), {"attending": "yes"}
        )
        self.assertEqual(AnnouncementResponse.objects.count(), 1)

    def test_answering_after_the_closing_date_writes_nothing(self):
        announcement = self.make(requires_response=True, respond_by=TODAY - timedelta(days=1))
        response = self.client.post(
            reverse("step:announcement_respond", args=[announcement.pk]), {"attending": "yes"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AnnouncementResponse.objects.count(), 0)

    def test_a_closed_announcement_will_not_let_an_existing_answer_change(self):
        announcement = self.make(requires_response=True, respond_by=TODAY - timedelta(days=1))
        AnnouncementResponse.objects.create(
            announcement=announcement, educator=self.educator, attending=True
        )
        self.client.post(
            reverse("step:announcement_respond", args=[announcement.pk]), {"attending": "no"}
        )
        self.assertTrue(AnnouncementResponse.objects.get().attending)

    def test_there_is_nothing_to_answer_on_pure_news(self):
        announcement = self.make(requires_response=False)
        response = self.client.post(
            reverse("step:announcement_respond", args=[announcement.pk]), {"attending": "yes"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AnnouncementResponse.objects.count(), 0)

    def test_a_withdrawn_announcement_cannot_be_answered(self):
        announcement = self.make(requires_response=True, is_active=False)
        self.client.post(
            reverse("step:announcement_respond", args=[announcement.pk]), {"attending": "yes"}
        )
        self.assertEqual(AnnouncementResponse.objects.count(), 0)

    def test_a_missing_answer_writes_nothing(self):
        announcement = self.make(requires_response=True)
        self.client.post(reverse("step:announcement_respond", args=[announcement.pk]), {})
        self.assertEqual(AnnouncementResponse.objects.count(), 0)

    def test_answering_is_post_only(self):
        announcement = self.make(requires_response=True)
        response = self.client.get(reverse("step:announcement_respond", args=[announcement.pk]))
        self.assertEqual(response.status_code, 404)

    # --- One teacher, one answer -----------------------------------------

    def test_a_teacher_does_not_see_another_teacher_s_answer(self):
        announcement = self.make(requires_response=True)
        AnnouncementResponse.objects.create(
            announcement=announcement, educator=self.other_teacher(), attending=False
        )
        response = self.client.get(reverse("step:announcements"))
        self.assertIsNone(response.context["rows"][0]["response"])
        self.assertTrue(response.context["rows"][0]["needs_answer"])
        self.assertNotContains(response, "You said you will not attend")

    def test_answering_never_overwrites_another_teacher_s_answer(self):
        announcement = self.make(requires_response=True)
        other = self.other_teacher()
        AnnouncementResponse.objects.create(
            announcement=announcement, educator=other, attending=False
        )
        self.client.post(
            reverse("step:announcement_respond", args=[announcement.pk]), {"attending": "yes"}
        )
        self.assertEqual(AnnouncementResponse.objects.count(), 2)
        self.assertFalse(AnnouncementResponse.objects.get(educator=other).attending)
        self.assertTrue(AnnouncementResponse.objects.get(educator=self.educator).attending)
