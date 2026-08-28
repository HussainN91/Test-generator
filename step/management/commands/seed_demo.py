"""Creates a demonstration teacher with a realistic spread of obligations.

FOR DEVELOPMENT AND CLIENT DEMONSTRATIONS ONLY. It invents a person and their
work so the screens can be looked at before the real roster spreadsheet
arrives. It never touches imported roster rows: everything it creates is
matched on a reserved demo email, and re-running it resets that one teacher's
obligations rather than accumulating duplicates.

Deadlines are positioned relative to *today* rather than at fixed dates, so the
dashboard always shows one late item, some due soon and some already accepted —
which is what makes the urgency design legible in a screenshot.
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from step import constants, generation, roles, workflow
from step.models import (
    AcademicYear, Activity, ActivityParticipant, Announcement, AnnouncementResponse,
    District, Educator, Obligation, ObligationType, Region, School, SchoolStaff,
    Session, SessionAttendance, Student, TeachingClass, Term,
)

DEMO_EMAIL = "maria.santos@step.demo"
DEMO_USERNAME = "maria"
DEMO_PASSWORD = "demo-teacher-2026"


class Command(BaseCommand):
    help = "Create a demo teacher and obligations so the screens can be viewed. Dev only."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true",
            help="Delete the demo teacher's obligations before recreating them.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        today = date.today()

        region = Region.objects.filter(code="tashkent-city").first()
        if region is None:
            self.stderr.write(self.style.ERROR(
                "No regions found. Run `manage.py seed_geography` first."
            ))
            return

        district = District.objects.filter(region=region).first()
        school, _ = School.objects.get_or_create(
            name="International School 4", district=district
        )

        # --- The person -------------------------------------------------
        User = get_user_model()
        user, created_user = User.objects.get_or_create(
            username=DEMO_USERNAME, defaults={"email": DEMO_EMAIL, "first_name": "Maria", "last_name": "Santos"},
        )
        if created_user:
            user.set_password(DEMO_PASSWORD)
            user.save()

        educator, _ = Educator.objects.update_or_create(
            email=DEMO_EMAIL,
            defaults={
                "full_name": "Maria Santos",
                "region": region,
                "district": district,
                "school": school,
                "user": user,
                "is_active": True,
                "missing_from_last_import": False,
            },
        )

        try:
            roles.assign(user, constants.ROLE_EDUCATOR)
        except Exception:
            self.stderr.write(self.style.WARNING(
                "Could not assign the Educator role — run `manage.py seed_roles` first."
            ))

        # --- The academic year ------------------------------------------
        start_year = today.year if today.month >= 9 else today.year - 1
        year, _ = AcademicYear.objects.update_or_create(
            label=f"{start_year}-{str(start_year + 1)[2:]}",
            defaults={
                "start": date(start_year, 9, 1),
                "end": date(start_year + 1, 5, 31),
                "is_current": True,
            },
        )
        for sequence, (name, first, last) in enumerate([
            ("Term 1", date(start_year, 9, 1), date(start_year, 11, 30)),
            ("Term 2", date(start_year, 12, 1), date(start_year + 1, 2, 28)),
            ("Term 3", date(start_year + 1, 3, 1), date(start_year + 1, 5, 31)),
        ], start=1):
            Term.objects.update_or_create(
                year=year, sequence=sequence,
                defaults={"name": name, "start": first, "end": last},
            )

        # --- The obligation catalogue, as drawn in the client mockup -----
        # The three checkpoint types supersede the two generic "assessments"
        # entries below them from an earlier draft (classes/gradebook spec,
        # "supersedes §9") — see the cleanup right after this loop.
        catalogue = [
            ("Monthly Report", constants.CATEGORY_MONTHLY_REPORTING, constants.CADENCE_MONTHLY,
             constants.EVIDENCE_FILE, True,
             "Your monthly report, with the page your director signed and stamped.", ""),
            ("Beginning-of-year diagnostic", constants.CATEGORY_ASSESSMENTS, constants.CADENCE_ANNUAL,
             constants.EVIDENCE_NONE, False,
             "Score every student in the class on the beginning-of-year diagnostic.",
             constants.FORM_SLUG_ASSESSMENT_CHECKPOINT),
            ("Mid-year diagnostic", constants.CATEGORY_ASSESSMENTS, constants.CADENCE_ANNUAL,
             constants.EVIDENCE_NONE, False,
             "Score every student in the class on the mid-year diagnostic.",
             constants.FORM_SLUG_ASSESSMENT_CHECKPOINT),
            ("End-of-year diagnostic", constants.CATEGORY_ASSESSMENTS, constants.CADENCE_ANNUAL,
             constants.EVIDENCE_NONE, False,
             "Score every student in the class on the end-of-year diagnostic.",
             constants.FORM_SLUG_ASSESSMENT_CHECKPOINT),
            ("Update Class Data & Targets", constants.CATEGORY_OTHER, constants.CADENCE_TERMLY,
             constants.EVIDENCE_LINK, False,
             "Check your class list and targets are up to date.", ""),
            # CPD Online and CPD Offline are no longer paperwork owed by a date
            # (fix step plan §2): CPD Online is Ministry-run and merely
            # announced, with the teacher's whole interaction being an RSVP
            # (Announcement/AnnouncementResponse, seeded below); CPD Offline is
            # Activity/Session/Attendance, also seeded below. Only the ECA
            # monthly plan stays as an ObligationType, because it is still the
            # one reviewable, owed artefact in that vertical — it is generated
            # per-activity by generation.on_activity_created(), never spread
            # per-educator the way the rows above are.
            ("ECA Monthly Plan - {period}", constants.CATEGORY_ECA, constants.CADENCE_MONTHLY,
             constants.EVIDENCE_NONE, False,
             "Your plan for this month's extra-curricular group: overview, session outline "
             "and intended outcomes.",
             constants.FORM_SLUG_ECA_MONTHLY_PLAN),
        ]

        types = []
        for template, category, cadence, spec, review, description, form_slug in catalogue:
            obligation_type, _ = ObligationType.objects.update_or_create(
                name_template=template,
                defaults={
                    "category": category, "cadence": cadence, "evidence_spec": spec,
                    "requires_review": review, "description": description, "is_active": True,
                    "form_slug": form_slug,
                },
            )
            types.append(obligation_type)

        # A re-run against a database seeded by an older version of this
        # command must actually remove the types this catalogue replaced,
        # not just stop touching them.
        ObligationType.objects.filter(
            name_template__in=[
                "Assessment Administration - {period}",
                "Assessment Scoring & Submission - {period}",
                "CPD Online - Classroom Management",
                "ECA Programme Plan - {period}",
            ]
        ).delete()

        # --- The obligations, spread around today ------------------------
        if options["reset"]:
            Obligation.objects.filter(educator=educator).delete()

        # (type index, days from today, already accepted?)
        # A monthly report's period is the month it is due in, matching the
        # client mockup's "Monthly Report - May 2025, due 27 May 2025".
        #
        # The three checkpoint types (catalogue indices 1-3) are deliberately
        # not spread here: they are per-class, not per-educator (classes/
        # gradebook spec, "Generation"). A TeachingClass exists further down
        # (so the ECA activity has a roster to pull participants from), but
        # demonstrating checkpoints still means running
        # `generate_obligations --checkpoints` against it, not this
        # per-educator spread.
        #
        # CPD Online and ECA Monthly Plan (fix step plan §2, §4) are also
        # absent here on purpose: CPD Online no longer has a per-educator
        # ObligationType at all, and the ECA plan is generated per-*activity*
        # by generation.on_activity_created(), further down — neither is
        # spreadable by this (type index, offset) mechanism.
        spread = [
            (0, -4,  False),   # Monthly Report — late
            (4, +30, False),   # Class data — scheduled
            (0, -32, True),    # last month's report — accepted
            (0, -63, True),    # and the one before
        ]

        created = 0
        for index, offset, done in spread:
            obligation_type = types[index]
            due = today + timedelta(days=offset)
            period = due.replace(day=1)

            obligation, made = Obligation.objects.get_or_create(
                type=obligation_type, educator=educator, period_start=period,
                defaults={
                    "period_kind": obligation_type.period_kind,
                    "period_label": "Term 1" if obligation_type.period_kind == constants.PERIOD_TERM else "",
                    "due_date": due,
                },
            )
            if made:
                created += 1
            if done and obligation.status == constants.STATUS_NOT_STARTED:
                submission = workflow.submit(
                    obligation, user=user,
                    evidence=[{
                        "kind": constants.EVIDENCE_FILE_KIND,
                        "file": SimpleUploadedFile("stamped-report.jpg", b"demo", content_type="image/jpeg"),
                        "caption": "stamped-report.jpg",
                    }],
                    evaluation={
                        "director_rating": 4,
                        "director_name": "John Dela Cruz",
                        "director_comments": "Good implementation of lesson planning and classroom management.",
                        "outcome": constants.OUTCOME_SATISFACTORY_OR_BETTER,
                    },
                )
                if obligation.type.requires_review:
                    workflow.accept(submission, reviewer=user)

        # --- ECA and CPD Offline: Activity -> Session -> Attendance ------
        # (fix step plan §3-4). A TeachingClass exists solely so the ECA
        # group has a roster to pull participants from — see the comment
        # above the "spread" list for why this doesn't touch checkpoints.
        teaching_class, _ = TeachingClass.objects.get_or_create(
            grade=9, slot=1, defaults={"educator": educator, "display_name": "9A"}
        )
        students = [
            Student.objects.get_or_create(teaching_class=teaching_class, full_name=name)[0]
            for name in ["Aziz Karimov", "Malika Yusupova"]
        ]

        eca_activity, _ = Activity.objects.get_or_create(
            educator=educator, kind=constants.ACTIVITY_KIND_ECA, title="Debate Club",
            defaults={"started_on": today - timedelta(days=21), "schedule_rule": {"weekdays": [1, 3]}},
        )
        for student in students:
            ActivityParticipant.objects.get_or_create(
                activity=eca_activity, full_name=student.full_name, defaults={"student": student}
            )
        # Materialises this activity's sessions and its current-month plan
        # obligation exactly as the real "set up an activity" screen does
        # (generation.on_activity_created — fix step plan §3.8), so the demo
        # data exercises the real path rather than hand-rolled rows.
        generation.on_activity_created(eca_activity, today=today)
        self._log_past_sessions(eca_activity, today, topic="Argument structure")

        staff_rows = [
            SchoolStaff.objects.get_or_create(school=school, full_name=name)[0]
            for name in ["Dilnoza Yusupova", "Rustam Aliev"]
        ]

        cpd_activity, _ = Activity.objects.get_or_create(
            educator=educator, kind=constants.ACTIVITY_KIND_CPD_OFFLINE, title="Friday Workshop",
            defaults={
                "school": school, "started_on": today - timedelta(days=21),
                "schedule_rule": {"weekdays": [4]},
            },
        )
        for staff in staff_rows:
            ActivityParticipant.objects.get_or_create(
                activity=cpd_activity, full_name=staff.full_name, defaults={"staff": staff}
            )
        generation.on_activity_created(cpd_activity, today=today)
        self._log_past_sessions(cpd_activity, today, topic="Classroom management")

        # --- CPD Online: one announcement, real RSVP responses -----------
        # (fix step plan §5). No obligation row for this vertical any more —
        # the whole interaction is the RSVP below.
        announcement, _ = Announcement.objects.get_or_create(
            title="New CPD Online course: Assessment for Learning",
            defaults={
                "body": "The Ministry has published a new course. Let us know if you'll attend.",
                "requires_response": True,
                "respond_by": today + timedelta(days=14),
            },
        )
        colleague, _ = Educator.objects.get_or_create(
            full_name="Aibek Toshev", region=region, defaults={"district": district, "school": school}
        )
        # Left deliberately unanswered, so the RSVP view's "not yet
        # answered" figure — the one an administrator actually needs to
        # chase (fix step plan §5.4) — has something real to count.
        Educator.objects.get_or_create(
            full_name="Jasur Yusupov", region=region, defaults={"district": district, "school": school}
        )
        AnnouncementResponse.objects.update_or_create(
            announcement=announcement, educator=educator, defaults={"attending": True}
        )
        AnnouncementResponse.objects.update_or_create(
            announcement=announcement, educator=colleague, defaults={"attending": False}
        )

        self.stdout.write(self.style.SUCCESS(
            f"Demo ready: {educator.full_name}, {len(types)} obligation types, {created} new obligations, "
            "2 activities and 1 announcement seeded."
        ))
        self.stdout.write(f"  Sign in as  {DEMO_USERNAME}  /  {DEMO_PASSWORD}")
        self.stdout.write("  Then open   /step/")

    def _log_past_sessions(self, activity, today, *, topic):
        """Mark the two earliest already-scheduled sessions as held, with
        every participant present — the common case the real log-session
        screen defaults to (fix step plan §3.5) — so the demo shows a
        register with real attendance rather than only "expected" rows."""
        participants = list(activity.participants.all())
        sessions = activity.sessions.filter(
            scheduled_for__lte=today, status=constants.SESSION_STATUS_EXPECTED
        ).order_by("scheduled_for")[:2]
        for session in sessions:
            session.status = constants.SESSION_STATUS_HELD
            session.held_on = session.scheduled_for
            session.topic = topic
            session.recorded_at = timezone.now()
            session.save(update_fields=["status", "held_on", "topic", "recorded_at"])
            for participant in participants:
                SessionAttendance.objects.get_or_create(session=session, participant=participant)
