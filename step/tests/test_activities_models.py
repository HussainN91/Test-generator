"""Activity -> Session -> Attendance: recurring delivery with a roster.

ECA Programme and CPD Offline are not paperwork owed by a date, they are a
teacher running the same slot week after week for a fixed group of people
(fix step plan §2-§3). These tests pin the shape and the constraints that
keep a past register honest: full names never silently rewrite themselves,
and a session's attendance rows are presence-only.
"""

from datetime import date

from django.db import IntegrityError
from django.test import TestCase

from step import constants
from step.models import (
    Activity,
    ActivityParticipant,
    ActivityPlan,
    Educator,
    Region,
    School,
    SchoolStaff,
    Session,
    SessionAttendance,
    Student,
    TeachingClass,
)


class ActivityTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.school = School.objects.create(name="School 12")

    def test_an_eca_activity_needs_no_school(self):
        activity = Activity.objects.create(
            educator=self.educator, kind=constants.ACTIVITY_KIND_ECA,
            title="Chess Club", started_on=date(2026, 9, 1),
            schedule_rule={"weekdays": [4]},
        )
        self.assertIsNone(activity.school)
        self.assertEqual(activity.kind, constants.ACTIVITY_KIND_ECA)
        self.assertIsNone(activity.archived_on)

    def test_a_cpd_offline_activity_carries_its_school(self):
        activity = Activity.objects.create(
            educator=self.educator, kind=constants.ACTIVITY_KIND_CPD_OFFLINE,
            title="Teacher Workshop", school=self.school, started_on=date(2026, 9, 1),
            schedule_rule={"weekdays": [1, 3]},
        )
        self.assertEqual(activity.school, self.school)
        self.assertEqual(activity.kind, constants.ACTIVITY_KIND_CPD_OFFLINE)


class ActivityParticipantTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.activity = Activity.objects.create(
            educator=self.educator, kind=constants.ACTIVITY_KIND_ECA,
            title="Chess Club", started_on=date(2026, 9, 1),
        )
        self.teaching_class = TeachingClass.objects.create(
            educator=self.educator, grade=9, slot=1, display_name="9A"
        )

    def test_full_name_survives_the_linked_student_being_deleted(self):
        """The register must never silently rewrite itself: full_name is
        stored independently, and SET_NULL only clears the link."""
        student = Student.objects.create(teaching_class=self.teaching_class, full_name="Aziz Karimov")
        participant = ActivityParticipant.objects.create(
            activity=self.activity, full_name="Aziz Karimov", student=student,
        )
        student.delete()
        participant.refresh_from_db()
        self.assertEqual(participant.full_name, "Aziz Karimov")
        self.assertIsNone(participant.student)

    def test_full_name_survives_the_linked_staff_being_deleted(self):
        school = School.objects.create(name="School 12")
        staff = SchoolStaff.objects.create(school=school, full_name="Dilnoza Yusupova")
        participant = ActivityParticipant.objects.create(
            activity=self.activity, full_name="Dilnoza Yusupova", staff=staff,
        )
        staff.delete()
        participant.refresh_from_db()
        self.assertEqual(participant.full_name, "Dilnoza Yusupova")
        self.assertIsNone(participant.staff)

    def test_a_participant_can_be_typed_in_with_no_link_at_all(self):
        participant = ActivityParticipant.objects.create(activity=self.activity, full_name="Guest")
        self.assertIsNone(participant.student)
        self.assertIsNone(participant.staff)

    def test_a_participant_cannot_be_linked_to_both_student_and_staff(self):
        """student and staff are mutually exclusive: a name is sourced from
        one or the other, or neither, never both."""
        student = Student.objects.create(teaching_class=self.teaching_class, full_name="Aziz Karimov")
        school = School.objects.create(name="School 12")
        staff = SchoolStaff.objects.create(school=school, full_name="Dilnoza Yusupova")
        with self.assertRaises(IntegrityError):
            ActivityParticipant.objects.create(
                activity=self.activity, full_name="Aziz Karimov", student=student, staff=staff,
            )

    def test_a_participant_can_be_linked_to_just_a_student(self):
        student = Student.objects.create(teaching_class=self.teaching_class, full_name="Aziz Karimov")
        participant = ActivityParticipant.objects.create(
            activity=self.activity, full_name="Aziz Karimov", student=student,
        )
        self.assertEqual(participant.student, student)
        self.assertIsNone(participant.staff)

    def test_a_participant_can_be_linked_to_just_staff(self):
        school = School.objects.create(name="School 12")
        staff = SchoolStaff.objects.create(school=school, full_name="Dilnoza Yusupova")
        participant = ActivityParticipant.objects.create(
            activity=self.activity, full_name="Dilnoza Yusupova", staff=staff,
        )
        self.assertIsNone(participant.student)
        self.assertEqual(participant.staff, staff)


class SessionAttendanceTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.activity = Activity.objects.create(
            educator=self.educator, kind=constants.ACTIVITY_KIND_ECA,
            title="Chess Club", started_on=date(2026, 9, 1),
        )
        self.session = Session.objects.create(activity=self.activity, scheduled_for=date(2026, 9, 4))
        self.participant = ActivityParticipant.objects.create(activity=self.activity, full_name="Aziz Karimov")

    def test_session_defaults_to_expected(self):
        self.assertEqual(self.session.status, constants.SESSION_STATUS_EXPECTED)
        self.assertIsNone(self.session.held_on)

    def test_a_participant_can_be_marked_present(self):
        SessionAttendance.objects.create(session=self.session, participant=self.participant)
        self.assertEqual(self.session.attendances.count(), 1)

    def test_a_participant_cannot_be_marked_present_twice_for_one_session(self):
        SessionAttendance.objects.create(session=self.session, participant=self.participant)
        with self.assertRaises(IntegrityError):
            SessionAttendance.objects.create(session=self.session, participant=self.participant)


class ActivityPlanTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.activity = Activity.objects.create(
            educator=self.educator, kind=constants.ACTIVITY_KIND_ECA,
            title="Chess Club", started_on=date(2026, 9, 1),
        )

    def test_plan_fields_are_blank_by_default(self):
        plan = ActivityPlan.objects.create(activity=self.activity, period=date(2026, 9, 1))
        self.assertEqual(plan.overview, "")
        self.assertEqual(plan.session_outline, "")
        self.assertEqual(plan.intended_outcomes, "")

    def test_one_plan_per_activity_and_period(self):
        ActivityPlan.objects.create(activity=self.activity, period=date(2026, 9, 1))
        with self.assertRaises(IntegrityError):
            ActivityPlan.objects.create(activity=self.activity, period=date(2026, 9, 1))

    def test_two_periods_can_coexist_for_the_same_activity(self):
        ActivityPlan.objects.create(activity=self.activity, period=date(2026, 9, 1))
        ActivityPlan.objects.create(activity=self.activity, period=date(2026, 10, 1))
        self.assertEqual(self.activity.plans.count(), 2)


class SchoolStaffTests(TestCase):
    def test_staff_is_scoped_to_a_school(self):
        school = School.objects.create(name="School 12")
        staff = SchoolStaff.objects.create(school=school, full_name="Dilnoza Yusupova")
        self.assertEqual(staff.school, school)
        self.assertEqual(str(staff), "Dilnoza Yusupova")
        self.assertEqual(school.staff.count(), 1)
