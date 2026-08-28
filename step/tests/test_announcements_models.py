"""Announcements and RSVP — the CPD Online vertical.

The Ministry runs CPD Online; STEP only broadcasts and collects an RSVP
(fix step plan.md §5). There is deliberately no obligation row and no
review here — these tests pin the one guarantee that matters: one answer
per teacher per announcement, changeable, never duplicated.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from step.models import Announcement, AnnouncementResponse, Educator, Region


class AnnouncementTests(TestCase):
    def test_defaults_are_the_least_surprising_ones(self):
        announcement = Announcement.objects.create(title="New CPD session", body="Details here.")
        self.assertTrue(announcement.is_active)
        self.assertFalse(announcement.requires_response)
        self.assertIsNone(announcement.respond_by)
        self.assertIsNone(announcement.created_by)

    def test_deleting_the_creator_does_not_delete_the_announcement(self):
        user = get_user_model().objects.create_user("admin", password="x")
        announcement = Announcement.objects.create(
            title="New CPD session", body="Details here.", created_by=user
        )
        user.delete()
        announcement.refresh_from_db()
        self.assertIsNone(announcement.created_by)

    def test_str_is_the_title(self):
        announcement = Announcement.objects.create(title="New CPD session", body="Details here.")
        self.assertEqual(str(announcement), "New CPD session")


class AnnouncementResponseTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.announcement = Announcement.objects.create(
            title="New CPD session", body="Details here.", requires_response=True,
            respond_by=date(2026, 9, 30),
        )

    def test_a_teacher_can_rsvp_attending(self):
        response = AnnouncementResponse.objects.create(
            announcement=self.announcement, educator=self.educator, attending=True
        )
        self.assertTrue(response.attending)

    def test_a_teacher_can_rsvp_not_attending(self):
        response = AnnouncementResponse.objects.create(
            announcement=self.announcement, educator=self.educator, attending=False
        )
        self.assertFalse(response.attending)

    def test_one_response_per_teacher_per_announcement(self):
        AnnouncementResponse.objects.create(
            announcement=self.announcement, educator=self.educator, attending=True
        )
        with self.assertRaises(IntegrityError):
            AnnouncementResponse.objects.create(
                announcement=self.announcement, educator=self.educator, attending=False
            )

    def test_two_teachers_can_each_answer_the_same_announcement(self):
        other = Educator.objects.create(full_name="Jonas Weber", region=self.region)
        AnnouncementResponse.objects.create(
            announcement=self.announcement, educator=self.educator, attending=True
        )
        AnnouncementResponse.objects.create(
            announcement=self.announcement, educator=other, attending=False
        )
        self.assertEqual(self.announcement.responses.count(), 2)

    def test_a_teacher_can_change_their_answer(self):
        response = AnnouncementResponse.objects.create(
            announcement=self.announcement, educator=self.educator, attending=True
        )
        response.attending = False
        response.save(update_fields=["attending"])
        response.refresh_from_db()
        self.assertFalse(response.attending)
