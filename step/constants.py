"""Vocabulary for the obligation engine.

These values are stored in the database and must not be renamed casually.
User-facing wording is deliberately NOT defined here — the spec (§7.0) forbids
showing this vocabulary to users, so display strings live in templates.
"""

# --- Obligation status (stored) -------------------------------------------
STATUS_NOT_STARTED = "not_started"
STATUS_SUBMITTED = "submitted"
STATUS_UNDER_REVIEW = "under_review"
STATUS_ACCEPTED = "accepted"
STATUS_RETURNED = "returned"

OBLIGATION_STATUS_CHOICES = [
    (STATUS_NOT_STARTED, "Not started"),
    (STATUS_SUBMITTED, "Submitted"),
    (STATUS_UNDER_REVIEW, "Under review"),
    (STATUS_ACCEPTED, "Accepted"),
    (STATUS_RETURNED, "Returned"),
]

#: Statuses that mean the teacher has nothing left to do.
SETTLED_STATUSES = {STATUS_ACCEPTED}

#: Statuses that mean the ball is in an administrator's court.
AWAITING_REVIEW_STATUSES = {STATUS_SUBMITTED, STATUS_UNDER_REVIEW}

# --- Categories (the sidebar groupings in the client mockup) --------------
CATEGORY_MONTHLY_REPORTING = "monthly_reporting"
CATEGORY_CPD_ONLINE = "cpd_online"
CATEGORY_CPD_OFFLINE = "cpd_offline"
CATEGORY_ECA = "eca"
CATEGORY_ASSESSMENTS = "assessments"
CATEGORY_OTHER = "other"

CATEGORY_CHOICES = [
    (CATEGORY_MONTHLY_REPORTING, "Monthly Reporting"),
    (CATEGORY_CPD_ONLINE, "CPD Online"),
    (CATEGORY_CPD_OFFLINE, "CPD Offline"),
    (CATEGORY_ECA, "ECA Programme"),
    (CATEGORY_ASSESSMENTS, "Assessments"),
    (CATEGORY_OTHER, "Other"),
]

# --- Cadence and period ---------------------------------------------------
CADENCE_MONTHLY = "monthly"
CADENCE_TERMLY = "termly"
CADENCE_ANNUAL = "annual"
CADENCE_ONCE = "once"

CADENCE_CHOICES = [
    (CADENCE_MONTHLY, "Every month"),
    (CADENCE_TERMLY, "Every term"),
    (CADENCE_ANNUAL, "Once a year"),
    (CADENCE_ONCE, "One off"),
]

PERIOD_MONTH = "month"
PERIOD_TERM = "term"
PERIOD_YEAR = "year"
PERIOD_ONCE = "once"

PERIOD_KIND_CHOICES = [
    (PERIOD_MONTH, "Month"),
    (PERIOD_TERM, "Term"),
    (PERIOD_YEAR, "Year"),
    (PERIOD_ONCE, "One off"),
]

CADENCE_TO_PERIOD_KIND = {
    CADENCE_MONTHLY: PERIOD_MONTH,
    CADENCE_TERMLY: PERIOD_TERM,
    CADENCE_ANNUAL: PERIOD_YEAR,
    CADENCE_ONCE: PERIOD_ONCE,
}

# --- Evidence requirements (spec §5.7) ------------------------------------
EVIDENCE_NONE = "none"
EVIDENCE_LINK = "link"
EVIDENCE_FILE = "file"
EVIDENCE_EITHER = "either"
EVIDENCE_BOTH = "both"

EVIDENCE_SPEC_CHOICES = [
    (EVIDENCE_NONE, "No attachment required"),
    (EVIDENCE_LINK, "At least one link"),
    (EVIDENCE_FILE, "At least one uploaded file"),
    (EVIDENCE_EITHER, "At least one link or file"),
    (EVIDENCE_BOTH, "At least one link and one file"),
]

EVIDENCE_LINK_KIND = "link"
EVIDENCE_FILE_KIND = "file"
EVIDENCE_KIND_CHOICES = [
    (EVIDENCE_LINK_KIND, "Link"),
    (EVIDENCE_FILE_KIND, "File"),
]

# --- Scope (spec §5.6: `all` is the only implementation in slice 1) -------
SCOPE_ALL = "all"
SCOPE_CHOICES = [(SCOPE_ALL, "Every active educator")]

# --- Roles ----------------------------------------------------------------
ROLE_EDUCATOR = "Educator"
ROLE_ADMIN = "Admin"
ROLE_PROGRAMME_ADMIN = "Programme Admin"
ROLE_SYSTEM_ADMIN = "System Admin"

ROLE_NAMES = [ROLE_EDUCATOR, ROLE_ADMIN, ROLE_PROGRAMME_ADMIN, ROLE_SYSTEM_ADMIN]

#: Roles that never accrue obligations (spec §5.6).
STAFF_ROLES = {ROLE_ADMIN, ROLE_PROGRAMME_ADMIN, ROLE_SYSTEM_ADMIN}

# --- Urgency (derived, never stored — spec §5.3) --------------------------
URGENCY_DONE = "done"
URGENCY_OVERDUE = "overdue"
URGENCY_DUE_TODAY = "due_today"
URGENCY_DUE_SOON = "due_soon"
URGENCY_SCHEDULED = "scheduled"

#: How many days ahead counts as "due soon" in the teacher's queue.
DUE_SOON_DAYS = 7

# --- Self-reported evaluation (spec §5.10) --------------------------------
# The director never logs in, so these are transcribed by the teacher and
# verified only by the photographed stamp. Anything rendering them MUST label
# them as self-reported.
OUTCOME_SATISFACTORY_OR_BETTER = "satisfactory_or_better"
OUTCOME_NEEDS_IMPROVEMENT = "needs_improvement"

OUTCOME_CHOICES = [
    (OUTCOME_SATISFACTORY_OR_BETTER, "Received Satisfactory or Better"),
    (OUTCOME_NEEDS_IMPROVEMENT, "Received Needs Improvement"),
]

#: Director star rating, 1-5, as drawn in the client mockup.
DIRECTOR_RATING_CHOICES = [(n, str(n)) for n in range(1, 6)]

# --- Classes & Gradebook (2026-08-27 classes/gradebook spec) --------------
# Supersedes the two generic "assessments" types from the platform spine
# spec §9 — see the classes/gradebook spec's header note.
CHECKPOINT_BOY = "boy"
CHECKPOINT_MOY = "moy"
CHECKPOINT_EOY = "eoy"

CHECKPOINT_CHOICES = [
    (CHECKPOINT_BOY, "Beginning of year"),
    (CHECKPOINT_MOY, "Mid year"),
    (CHECKPOINT_EOY, "End of year"),
]

SKILL_READING = "reading"
SKILL_WRITING = "writing"
SKILL_LISTENING = "listening"
SKILL_SPEAKING = "speaking"

SKILL_CHOICES = [
    (SKILL_READING, "Reading"),
    (SKILL_WRITING, "Writing"),
    (SKILL_LISTENING, "Listening"),
    (SKILL_SPEAKING, "Speaking"),
]

#: The bespoke obligation form this vertical uses (ObligationType.form_slug).
FORM_SLUG_ASSESSMENT_CHECKPOINT = "assessment_checkpoint"

#: Grades and class-pack slots this programme serves. Slot count matches
#: diagnostics' CLASSES_PER_GRADE (diagnostics/navigation.py) but is not
#: imported from there — step stays decoupled from diagnostics; the
#: dependency runs the other way (diagnostics reads step.TeachingClass).
TEACHING_GRADES = (9, 10, 11)
TEACHING_SLOTS_PER_GRADE = 4

#: A ProgressEntry.checkpoint has no obligation-type FK of its own (the model
#: only needs a short code), so this is the one place that ties a checkpoint
#: to the ObligationType.name_template generated for it (see step/generation.py
#: and seed_demo.py's catalogue).
CHECKPOINT_OBLIGATION_NAME_TEMPLATES = {
    CHECKPOINT_BOY: "Beginning-of-year diagnostic",
    CHECKPOINT_MOY: "Mid-year diagnostic",
    CHECKPOINT_EOY: "End-of-year diagnostic",
}
NAME_TEMPLATE_TO_CHECKPOINT = {v: k for k, v in CHECKPOINT_OBLIGATION_NAME_TEMPLATES.items()}

# --- Activities: ECA Programme & CPD Offline (platform spine spec §3, fix
# step plan §3-4) ------------------------------------------------------------
# These are recurring delivery with a roster, not paperwork, so they are
# modeled as Activity -> Session -> Attendance rather than as obligations.
# Deliberately no weekly CADENCE_* value: sessions are not obligations.
ACTIVITY_KIND_ECA = "eca"
ACTIVITY_KIND_CPD_OFFLINE = "cpd_offline"

ACTIVITY_KIND_CHOICES = [
    (ACTIVITY_KIND_ECA, "ECA Programme"),
    (ACTIVITY_KIND_CPD_OFFLINE, "CPD Offline"),
]

SESSION_STATUS_EXPECTED = "expected"
SESSION_STATUS_HELD = "held"
SESSION_STATUS_CANCELLED = "cancelled"

SESSION_STATUS_CHOICES = [
    (SESSION_STATUS_EXPECTED, "Expected"),
    (SESSION_STATUS_HELD, "Held"),
    (SESSION_STATUS_CANCELLED, "Cancelled"),
]

#: The bespoke obligation form the ECA monthly plan uses (ObligationType.form_slug).
FORM_SLUG_ECA_MONTHLY_PLAN = "eca_monthly_plan"
