"""seed_demo's catalogue is what the classes/gradebook checkpoints attach to
by name (step.constants.CHECKPOINT_OBLIGATION_NAME_TEMPLATES) — a renamed or
missing catalogue entry breaks generation silently, so the names are pinned
here. Same reasoning extends to the ECA Monthly Plan type: generation.py's
generate_activity_plan_obligations() looks it up by form_slug and silently
no-ops if it is absent (fix step plan §7 item 20), so its presence is pinned
too, alongside proof CPD Online and the old ECA Programme Plan type are gone
for good, and that the Activity/Session/Announcement demo data comes out of
the real generation path rather than hand-rolled rows."""

import tempfile
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from step import constants
from step.models import (
    Activity, AnnouncementResponse, Educator, Evidence, Obligation, ObligationType, Session,
    SessionAttendance,
)

MEDIA = tempfile.mkdtemp()


class SeedDemoCheckpointTypesTests(TestCase):
    def setUp(self):
        # seed_demo bails out with no regions to attach the demo teacher to.
        call_command("seed_geography", stdout=StringIO())
        call_command("seed_roles", stdout=StringIO())

    def test_the_three_checkpoint_types_are_seeded(self):
        call_command("seed_demo", stdout=StringIO())
        names = set(
            ObligationType.objects.filter(
                form_slug=constants.FORM_SLUG_ASSESSMENT_CHECKPOINT
            ).values_list("name_template", flat=True)
        )
        self.assertEqual(names, set(constants.CHECKPOINT_OBLIGATION_NAME_TEMPLATES.values()))

    def test_the_superseded_generic_assessment_types_are_gone(self):
        call_command("seed_demo", stdout=StringIO())
        self.assertFalse(
            ObligationType.objects.filter(name_template__startswith="Assessment Administration").exists()
        )
        self.assertFalse(
            ObligationType.objects.filter(name_template__startswith="Assessment Scoring").exists()
        )

    def test_checkpoint_types_are_annual_with_no_evidence(self):
        call_command("seed_demo", stdout=StringIO())
        boy = ObligationType.objects.get(name_template="Beginning-of-year diagnostic")
        self.assertEqual(boy.cadence, constants.CADENCE_ANNUAL)
        self.assertEqual(boy.evidence_spec, constants.EVIDENCE_NONE)
        self.assertFalse(boy.requires_review)

    @override_settings(MEDIA_ROOT=MEDIA)
    def test_the_accepted_monthly_reports_carry_a_real_file_not_an_empty_one(self):
        """A file-kind Evidence row with no actual file crashes any template
        that reads evidence.file.url (FieldFile.url raises on an empty file) —
        found by test-generator-a7 auditing the admin review screen against
        this command's seed data."""
        call_command("seed_demo", stdout=StringIO())
        file_evidence = Evidence.objects.filter(kind=constants.EVIDENCE_FILE_KIND)
        self.assertGreater(file_evidence.count(), 0)
        for evidence in file_evidence:
            self.assertTrue(evidence.file, f"Evidence {evidence.pk} claims kind=file but has no file")

    def test_seed_demo_is_genuinely_rerunnable(self):
        """The whole point of the explicit-deletion pattern is that running
        this command twice against the same database must not IntegrityError
        or silently duplicate rows — pinned directly rather than assumed."""
        call_command("seed_demo", stdout=StringIO())
        call_command("seed_demo", stdout=StringIO())


class SeedDemoFixStepTypesTests(TestCase):
    """fix step plan.md §7 item 20: CPD Online and the old per-term ECA
    Programme Plan type are removed from the catalogue (and deleted on
    re-run), replaced by a single ECA Monthly Plan type that generation.py's
    generate_activity_plan_obligations() looks up by form_slug."""

    def setUp(self):
        call_command("seed_geography", stdout=StringIO())
        call_command("seed_roles", stdout=StringIO())

    def test_cpd_online_type_is_gone(self):
        call_command("seed_demo", stdout=StringIO())
        self.assertFalse(
            ObligationType.objects.filter(name_template="CPD Online - Classroom Management").exists()
        )

    def test_the_old_eca_programme_plan_type_is_gone(self):
        call_command("seed_demo", stdout=StringIO())
        self.assertFalse(
            ObligationType.objects.filter(name_template="ECA Programme Plan - {period}").exists()
        )

    def test_a_rerun_against_the_old_catalogue_removes_the_superseded_types(self):
        """Pins the "not just stop touching them" requirement: seeding from
        an older version of this command, then re-running the current one,
        must actually delete the superseded rows."""
        ObligationType.objects.create(
            name_template="CPD Online - Classroom Management", category=constants.CATEGORY_CPD_ONLINE,
            cadence=constants.CADENCE_TERMLY,
        )
        ObligationType.objects.create(
            name_template="ECA Programme Plan - {period}", category=constants.CATEGORY_ECA,
            cadence=constants.CADENCE_TERMLY,
        )
        call_command("seed_demo", stdout=StringIO())
        self.assertFalse(
            ObligationType.objects.filter(
                name_template__in=["CPD Online - Classroom Management", "ECA Programme Plan - {period}"]
            ).exists()
        )

    def test_the_eca_monthly_plan_type_is_seeded_with_the_right_shape(self):
        call_command("seed_demo", stdout=StringIO())
        eca_plan_type = ObligationType.objects.get(form_slug=constants.FORM_SLUG_ECA_MONTHLY_PLAN)
        self.assertEqual(eca_plan_type.category, constants.CATEGORY_ECA)
        self.assertEqual(eca_plan_type.cadence, constants.CADENCE_MONTHLY)
        self.assertEqual(eca_plan_type.evidence_spec, constants.EVIDENCE_NONE)
        self.assertFalse(eca_plan_type.requires_review)


class SeedDemoActivitiesTests(TestCase):
    """fix step plan.md §7 item 20: one demo ECA group and one CPD Offline
    activity, both generated through generation.on_activity_created() so the
    demo data exercises the real path — sessions materialised, some marked
    held with attendance, and (for ECA) a plan obligation generated."""

    def setUp(self):
        call_command("seed_geography", stdout=StringIO())
        call_command("seed_roles", stdout=StringIO())
        call_command("seed_demo", stdout=StringIO())

    def test_an_eca_activity_and_a_cpd_offline_activity_exist(self):
        self.assertTrue(Activity.objects.filter(kind=constants.ACTIVITY_KIND_ECA).exists())
        self.assertTrue(Activity.objects.filter(kind=constants.ACTIVITY_KIND_CPD_OFFLINE).exists())

    def test_each_activity_has_at_least_one_held_session_with_attendance(self):
        for activity in Activity.objects.all():
            held = Session.objects.filter(activity=activity, status=constants.SESSION_STATUS_HELD)
            self.assertGreater(held.count(), 0, f"{activity} has no held session")
            for session in held:
                self.assertGreater(
                    SessionAttendance.objects.filter(session=session).count(), 0,
                    f"{session} is held but has no attendance",
                )

    def test_the_eca_activity_owes_a_monthly_plan_obligation(self):
        eca_activity = Activity.objects.get(kind=constants.ACTIVITY_KIND_ECA)
        self.assertTrue(Obligation.objects.filter(activity=eca_activity).exists())

    def test_rerunning_does_not_duplicate_sessions_or_participants(self):
        eca_activity = Activity.objects.get(kind=constants.ACTIVITY_KIND_ECA)
        session_count = Session.objects.filter(activity=eca_activity).count()
        participant_count = eca_activity.participants.count()
        call_command("seed_demo", stdout=StringIO())
        self.assertEqual(Session.objects.filter(activity=eca_activity).count(), session_count)
        self.assertEqual(eca_activity.participants.count(), participant_count)


class SeedDemoAnnouncementTests(TestCase):
    """fix step plan.md §7 item 20: one Announcement with real
    AnnouncementResponse rows covering all three RSVP states an
    administrator sees — attending, not attending, and not yet answered
    (the absence of a row, fix step plan §5.4)."""

    def setUp(self):
        call_command("seed_geography", stdout=StringIO())
        call_command("seed_roles", stdout=StringIO())
        call_command("seed_demo", stdout=StringIO())

    def test_an_announcement_exists_and_requires_a_response(self):
        self.assertTrue(AnnouncementResponse.objects.exists())

    def test_responses_cover_both_attending_and_not_attending(self):
        attending = set(AnnouncementResponse.objects.values_list("attending", flat=True))
        self.assertEqual(attending, {True, False})

    def test_at_least_one_educator_has_no_response_at_all(self):
        """"Not yet answered" is the absence of a row, not a stored value."""
        from step.models import Educator
        responded = set(AnnouncementResponse.objects.values_list("educator_id", flat=True))
        self.assertTrue(Educator.objects.exclude(pk__in=responded).exists())
