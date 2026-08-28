"""Screens for a teacher's own activities: roster, sessions, attendance.

Mirrors step/tests/test_classes_views.py's style. Beyond "does it render",
these pin the design's load-bearing promises: logging a session with
everyone pre-ticked is a single submit with no absentee rows, unchecking
someone removes them cleanly, a re-edit never duplicates or orphans
attendance, and a CPD Offline staff list is genuinely shared across two
activities at the same school.
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from step import constants, generation
from step.models import (
    Activity, ActivityParticipant, Educator, Region, School, SchoolStaff, Session,
    SessionAttendance, Student, TeachingClass,
)

TODAY = date.today()


class ActivityListTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region, user=self.user)
        self.client.login(username="maria", password="pw")

    def test_requires_signing_in(self):
        self.client.logout()
        response = self.client.get(reverse("step:activity_list"))
        self.assertEqual(response.status_code, 302)

    def test_shows_only_my_own_activities(self):
        Activity.objects.create(
            educator=self.educator, kind=constants.ACTIVITY_KIND_ECA, title="Chess Club",
            schedule_rule={"weekdays": [0]}, started_on=TODAY,
        )
        other = Educator.objects.create(full_name="John Cruz", region=self.region)
        Activity.objects.create(
            educator=other, kind=constants.ACTIVITY_KIND_ECA, title="Debate Club",
            schedule_rule={"weekdays": [0]}, started_on=TODAY,
        )
        response = self.client.get(reverse("step:activity_list"))
        titles = [row["activity"].title for row in response.context["rows"]]
        self.assertEqual(titles, ["Chess Club"])

    def test_the_due_count_is_expected_sessions_today_or_earlier(self):
        activity = Activity.objects.create(
            educator=self.educator, kind=constants.ACTIVITY_KIND_ECA, title="Chess Club",
            schedule_rule={"weekdays": [0]}, started_on=TODAY,
        )
        Session.objects.create(activity=activity, scheduled_for=TODAY - timedelta(days=7), status=constants.SESSION_STATUS_EXPECTED)
        Session.objects.create(activity=activity, scheduled_for=TODAY, status=constants.SESSION_STATUS_EXPECTED)
        Session.objects.create(activity=activity, scheduled_for=TODAY + timedelta(days=7), status=constants.SESSION_STATUS_EXPECTED)
        Session.objects.create(activity=activity, scheduled_for=TODAY - timedelta(days=14), status=constants.SESSION_STATUS_HELD, held_on=TODAY)

        response = self.client.get(reverse("step:activity_list"))
        row = response.context["rows"][0]
        self.assertEqual(row["due_count"], 2)


class ActivityCreateTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region, user=self.user)
        self.school = School.objects.create(name="School 12")
        self.client.login(username="maria", password="pw")

    def test_creating_an_eca_activity_materialises_sessions_and_redirects_to_the_roster(self):
        response = self.client.post(reverse("step:activity_create"), {
            "title": "Chess Club", "kind": constants.ACTIVITY_KIND_ECA,
            "weekdays": ["0", "2"], "started_on": TODAY.isoformat(),
        })
        activity = Activity.objects.get(title="Chess Club")
        self.assertEqual(activity.educator, self.educator)
        self.assertEqual(activity.schedule_rule, {"weekdays": [0, 2]})
        self.assertTrue(Session.objects.filter(activity=activity).exists())
        self.assertRedirects(response, reverse("step:activity_participant_create", args=[activity.pk]))

    def test_cpd_offline_requires_a_school(self):
        response = self.client.post(reverse("step:activity_create"), {
            "title": "Staff Reading Group", "kind": constants.ACTIVITY_KIND_CPD_OFFLINE,
            "weekdays": ["1"], "started_on": TODAY.isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Activity.objects.exists())

    def test_cpd_offline_with_a_school_succeeds(self):
        response = self.client.post(reverse("step:activity_create"), {
            "title": "Staff Reading Group", "kind": constants.ACTIVITY_KIND_CPD_OFFLINE,
            "weekdays": ["1"], "started_on": TODAY.isoformat(), "school": str(self.school.pk),
        })
        activity = Activity.objects.get(title="Staff Reading Group")
        self.assertEqual(activity.school, self.school)
        self.assertRedirects(response, reverse("step:activity_participant_create", args=[activity.pk]))

    def test_a_missing_name_is_rejected(self):
        response = self.client.post(reverse("step:activity_create"), {
            "title": "", "kind": constants.ACTIVITY_KIND_ECA, "weekdays": ["0"],
            "started_on": TODAY.isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Activity.objects.exists())

    def test_no_weekday_chosen_is_rejected(self):
        response = self.client.post(reverse("step:activity_create"), {
            "title": "Chess Club", "kind": constants.ACTIVITY_KIND_ECA, "weekdays": [],
            "started_on": TODAY.isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Activity.objects.exists())


class ParticipantCreateEcaTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region, user=self.user)
        self.activity = Activity.objects.create(
            educator=self.educator, kind=constants.ACTIVITY_KIND_ECA, title="Chess Club",
            schedule_rule={"weekdays": [0]}, started_on=TODAY,
        )
        self.teaching_class = TeachingClass.objects.create(
            educator=self.educator, grade=9, slot=1, display_name="9A"
        )
        self.student_a = Student.objects.create(teaching_class=self.teaching_class, full_name="Aziz Karimov")
        self.student_b = Student.objects.create(teaching_class=self.teaching_class, full_name="Dilnoza Yusupova")
        self.client.login(username="maria", password="pw")

    def test_pulling_in_a_class_adds_every_current_student(self):
        self.client.post(
            reverse("step:activity_participant_create", args=[self.activity.pk]),
            {"from_class": str(self.teaching_class.pk)},
        )
        names = set(self.activity.participants.values_list("full_name", flat=True))
        self.assertEqual(names, {"Aziz Karimov", "Dilnoza Yusupova"})
        self.assertEqual(
            ActivityParticipant.objects.get(full_name="Aziz Karimov").student, self.student_a
        )

    def test_pulling_in_a_class_twice_does_not_duplicate(self):
        url = reverse("step:activity_participant_create", args=[self.activity.pk])
        self.client.post(url, {"from_class": str(self.teaching_class.pk)})
        self.client.post(url, {"from_class": str(self.teaching_class.pk)})
        self.assertEqual(self.activity.participants.count(), 2)

    def test_typing_a_name_adds_a_participant_with_no_student_link(self):
        self.client.post(
            reverse("step:activity_participant_create", args=[self.activity.pk]),
            {"full_name": "A Visiting Student"},
        )
        participant = ActivityParticipant.objects.get(full_name="A Visiting Student")
        self.assertIsNone(participant.student)


class ParticipantCreateCpdOfflineTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region, user=self.user)
        self.school = School.objects.create(name="School 12")
        self.activity = Activity.objects.create(
            educator=self.educator, kind=constants.ACTIVITY_KIND_CPD_OFFLINE, title="Staff Reading Group",
            school=self.school, schedule_rule={"weekdays": [1]}, started_on=TODAY,
        )
        self.client.login(username="maria", password="pw")

    def test_no_school_shows_a_message_rather_than_crashing(self):
        activity = Activity.objects.create(
            educator=self.educator, kind=constants.ACTIVITY_KIND_CPD_OFFLINE, title="No School Group",
            schedule_rule={"weekdays": [1]}, started_on=TODAY,
        )
        response = self.client.get(reverse("step:activity_participant_create", args=[activity.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["needs_school"])

    def test_typing_a_new_name_creates_schoolstaff_and_a_participant(self):
        self.client.post(
            reverse("step:activity_participant_create", args=[self.activity.pk]),
            {"full_name": "Elena Volkova"},
        )
        staff = SchoolStaff.objects.get(full_name="Elena Volkova", school=self.school)
        participant = ActivityParticipant.objects.get(activity=self.activity, full_name="Elena Volkova")
        self.assertEqual(participant.staff, staff)

    def test_the_schoolstaff_list_is_shared_across_two_activities_at_the_same_school(self):
        """The point of a school-scoped list (fix step plan §3.3): a name
        typed in on one activity is offered as a pick on another."""
        other_activity = Activity.objects.create(
            educator=self.educator, kind=constants.ACTIVITY_KIND_CPD_OFFLINE, title="Second Group",
            school=self.school, schedule_rule={"weekdays": [2]}, started_on=TODAY,
        )

        self.client.post(
            reverse("step:activity_participant_create", args=[self.activity.pk]),
            {"full_name": "Elena Volkova"},
        )
        self.assertEqual(SchoolStaff.objects.filter(school=self.school).count(), 1)
        staff = SchoolStaff.objects.get(full_name="Elena Volkova")

        response = self.client.get(reverse("step:activity_participant_create", args=[other_activity.pk]))
        choices = list(response.context["staff_choices"])
        self.assertIn(staff, choices)

        self.client.post(
            reverse("step:activity_participant_create", args=[other_activity.pk]),
            {"staff": [str(staff.pk)]},
        )
        # Reused, not duplicated.
        self.assertEqual(SchoolStaff.objects.filter(school=self.school).count(), 1)
        self.assertTrue(
            ActivityParticipant.objects.filter(activity=other_activity, staff=staff).exists()
        )

    def test_picking_an_already_added_staff_member_again_does_not_duplicate(self):
        staff = SchoolStaff.objects.create(school=self.school, full_name="Elena Volkova")
        url = reverse("step:activity_participant_create", args=[self.activity.pk])
        self.client.post(url, {"staff": [str(staff.pk)]})
        self.client.post(url, {"staff": [str(staff.pk)]})
        self.assertEqual(
            ActivityParticipant.objects.filter(activity=self.activity, staff=staff).count(), 1
        )


class ActivityDetailTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region, user=self.user)
        self.activity = Activity.objects.create(
            educator=self.educator, kind=constants.ACTIVITY_KIND_ECA, title="Chess Club",
            schedule_rule={"weekdays": [0]}, started_on=TODAY,
        )
        self.client.login(username="maria", password="pw")

    def test_another_teachers_activity_is_not_visible(self):
        other = Educator.objects.create(full_name="John Cruz", region=self.region)
        other_activity = Activity.objects.create(
            educator=other, kind=constants.ACTIVITY_KIND_ECA, title="Debate Club",
            schedule_rule={"weekdays": [0]}, started_on=TODAY,
        )
        response = self.client.get(reverse("step:activity_detail", args=[other_activity.pk]))
        self.assertEqual(response.status_code, 404)

    def test_missing_this_months_plan_obligation_says_so_plainly(self):
        response = self.client.get(reverse("step:activity_detail", args=[self.activity.pk]))
        self.assertIsNone(response.context["plan_obligation"])
        self.assertContains(response, "hasn't been created yet")

    def test_an_off_schedule_session_is_created_and_sends_the_teacher_to_log_it(self):
        target = TODAY + timedelta(days=3)
        response = self.client.post(
            reverse("step:activity_session_create", args=[self.activity.pk]),
            {"scheduled_for": target.isoformat()},
        )
        session = Session.objects.get(activity=self.activity, scheduled_for=target)
        self.assertEqual(session.status, constants.SESSION_STATUS_EXPECTED)
        self.assertRedirects(
            response, reverse("step:activity_session_log", args=[self.activity.pk, session.pk])
        )


class SessionLogTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region, user=self.user)
        self.activity = Activity.objects.create(
            educator=self.educator, kind=constants.ACTIVITY_KIND_ECA, title="Chess Club",
            schedule_rule={"weekdays": [0]}, started_on=TODAY,
        )
        self.a = ActivityParticipant.objects.create(activity=self.activity, full_name="Aziz Karimov")
        self.b = ActivityParticipant.objects.create(activity=self.activity, full_name="Dilnoza Yusupova")
        self.session = Session.objects.create(
            activity=self.activity, scheduled_for=TODAY, status=constants.SESSION_STATUS_EXPECTED
        )
        self.client.login(username="maria", password="pw")
        self.url = reverse("step:activity_session_log", args=[self.activity.pk, self.session.pk])

    def test_everyone_is_pre_checked_on_an_untouched_session(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context["checked_ids"], {self.a.pk, self.b.pk})

    def test_saving_with_everyone_present_creates_attendance_for_both_and_no_extra_rows(self):
        self.client.post(self.url, {
            "action": "held", "topic": "Openings", "notes": "", "evidence_url": "",
            "present": [str(self.a.pk), str(self.b.pk)],
        })
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, constants.SESSION_STATUS_HELD)
        self.assertEqual(self.session.held_on, TODAY)
        attendees = set(SessionAttendance.objects.filter(session=self.session).values_list("participant_id", flat=True))
        self.assertEqual(attendees, {self.a.pk, self.b.pk})

    def test_unchecking_someone_leaves_no_attendance_row_for_them(self):
        self.client.post(self.url, {
            "action": "held", "topic": "Openings", "notes": "", "evidence_url": "",
            "present": [str(self.a.pk)],
        })
        self.assertFalse(SessionAttendance.objects.filter(session=self.session, participant=self.b).exists())
        self.assertTrue(SessionAttendance.objects.filter(session=self.session, participant=self.a).exists())

    def test_a_second_edit_does_not_duplicate_or_orphan_attendance(self):
        self.client.post(self.url, {
            "action": "held", "topic": "Openings", "notes": "", "evidence_url": "",
            "present": [str(self.a.pk), str(self.b.pk)],
        })
        # Correcting a mistake: b was not actually there.
        self.client.post(self.url, {
            "action": "held", "topic": "Openings", "notes": "", "evidence_url": "",
            "present": [str(self.a.pk)],
        })
        rows = SessionAttendance.objects.filter(session=self.session)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().participant, self.a)

    def test_cancelling_takes_no_attendance(self):
        self.client.post(self.url, {"action": "cancel"})
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, constants.SESSION_STATUS_CANCELLED)
        self.assertEqual(SessionAttendance.objects.filter(session=self.session).count(), 0)

    def test_an_unreachable_link_does_not_block_saving(self):
        response = self.client.post(self.url, {
            "action": "held", "topic": "Openings", "notes": "",
            "evidence_url": "http://localhost:1/unreachable",
            "present": [str(self.a.pk)],
        }, follow=True)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, constants.SESSION_STATUS_HELD)
        self.assertEqual(self.session.evidence_url, "http://localhost:1/unreachable")
        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("may not be reachable" in m for m in messages))

    def test_topic_prefills_from_the_most_recently_held_session(self):
        earlier = Session.objects.create(
            activity=self.activity, scheduled_for=TODAY - timedelta(days=7),
            status=constants.SESSION_STATUS_HELD, held_on=TODAY - timedelta(days=7), topic="Endgames",
        )
        response = self.client.get(self.url)
        self.assertEqual(response.context["prefill_topic"], "Endgames")


class SyncActivityPlanWiringTests(TestCase):
    """generation.on_activity_created is wired into activity_create — see
    ActivityCreateTests above for the redirect/materialisation assertions;
    this only pins that the generation module is actually invoked end to end
    for a group started mid-month (through step.generation, not duplicated
    logic in the view)."""

    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region, user=self.user)
        self.client.login(username="maria", password="pw")

    def test_created_activity_has_sessions_within_the_generation_horizon(self):
        self.client.post(reverse("step:activity_create"), {
            "title": "Chess Club", "kind": constants.ACTIVITY_KIND_ECA,
            "weekdays": [str(TODAY.weekday())], "started_on": TODAY.isoformat(),
        })
        activity = Activity.objects.get(title="Chess Club")
        self.assertTrue(
            activity.sessions.filter(scheduled_for=TODAY, status=constants.SESSION_STATUS_EXPECTED).exists()
        )
