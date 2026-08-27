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
from django.core.management.base import BaseCommand
from django.db import transaction

from step import constants, roles, workflow
from step.models import (
    AcademicYear, District, Educator, Obligation, ObligationType, Region, School, Term,
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
        catalogue = [
            ("Monthly Report", constants.CATEGORY_MONTHLY_REPORTING, constants.CADENCE_MONTHLY,
             constants.EVIDENCE_FILE, True,
             "Your monthly report, with the page your director signed and stamped."),
            ("CPD Online - Classroom Management", constants.CATEGORY_CPD_ONLINE, constants.CADENCE_TERMLY,
             constants.EVIDENCE_EITHER, False,
             "Finish the online course and send the certificate."),
            ("ECA Programme Plan - {period}", constants.CATEGORY_ECA, constants.CADENCE_TERMLY,
             constants.EVIDENCE_LINK, True,
             "Your plan for this term's extra-curricular activity."),
            ("Assessment Administration - {period}", constants.CATEGORY_ASSESSMENTS, constants.CADENCE_TERMLY,
             constants.EVIDENCE_EITHER, False,
             "Run the diagnostic papers with your classes."),
            ("Assessment Scoring & Submission - {period}", constants.CATEGORY_ASSESSMENTS, constants.CADENCE_TERMLY,
             constants.EVIDENCE_EITHER, True,
             "Mark the papers and send the scores."),
            ("Update Class Data & Targets", constants.CATEGORY_OTHER, constants.CADENCE_TERMLY,
             constants.EVIDENCE_LINK, False,
             "Check your class list and targets are up to date."),
        ]

        types = []
        for template, category, cadence, spec, review, description in catalogue:
            obligation_type, _ = ObligationType.objects.update_or_create(
                name_template=template,
                defaults={
                    "category": category, "cadence": cadence, "evidence_spec": spec,
                    "requires_review": review, "description": description, "is_active": True,
                },
            )
            types.append(obligation_type)

        # --- The obligations, spread around today ------------------------
        if options["reset"]:
            Obligation.objects.filter(educator=educator).delete()

        # (type index, days from today, already accepted?)
        # A monthly report's period is the month it is due in, matching the
        # client mockup's "Monthly Report - May 2025, due 27 May 2025".
        spread = [
            (0, -4,  False),   # Monthly Report — late
            (1, +2,  False),   # CPD Online — due soon
            (2, +5,  False),   # ECA plan — due soon
            (3, +9,  False),   # Assessment admin — scheduled
            (4, +21, False),   # Assessment scoring — scheduled
            (5, +30, False),   # Class data — scheduled
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
                    evidence=[{"kind": constants.EVIDENCE_FILE_KIND, "url": "", "caption": "stamped-report.jpg"}],
                    evaluation={
                        "director_rating": 4,
                        "director_name": "John Dela Cruz",
                        "director_comments": "Good implementation of lesson planning and classroom management.",
                        "outcome": constants.OUTCOME_SATISFACTORY_OR_BETTER,
                    },
                )
                if obligation.type.requires_review:
                    workflow.accept(submission, reviewer=user)

        self.stdout.write(self.style.SUCCESS(
            f"Demo ready: {educator.full_name}, {len(types)} obligation types, {created} new obligations."
        ))
        self.stdout.write(f"  Sign in as  {DEMO_USERNAME}  /  {DEMO_PASSWORD}")
        self.stdout.write("  Then open   /step/")
