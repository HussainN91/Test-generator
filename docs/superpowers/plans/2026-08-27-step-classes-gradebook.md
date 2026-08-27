# STEP Classes & Gradebook — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Classes & Gradebook vertical — a teacher's own classes and student rosters, checkpoint scoring wired into the obligation engine as the `assessments` category, and a read-only rename in `diagnostics` so a class pack shows the teacher's own name for it.

**Architecture:** Three new models (`TeachingClass`, `Student`, `ProgressEntry`) in a new `step/models/classes.py`, following the pattern `ObligationType.form_slug` was built for: this is one more vertical, not a special case. `Obligation` gains a nullable `teaching_class` FK so the three checkpoint types can be generated per-class instead of per-educator. `diagnostics` gains a one-directional, read-only dependency on `step.TeachingClass` for display names only.

**Tech Stack:** Django 6.1, Python 3.14. Same conventions as the rest of `step` — `django.test.TestCase`, models in a `models/` package, wording kept out of `step/constants.py`.

**Spec:** `docs/superpowers/specs/2026-08-27-step-classes-gradebook-design.md` (supersedes §9 of the platform spine spec).

---

## Scope of this plan

This plan covers the full vertical: models, obligation-engine integration, the diagnostics rename, and the teacher-facing screens.

**Ownership note — read before executing.** The spec's own "Sequencing" section, and the live coordination this round, single out a short list of files as shared / owned by another session (`test-generator-b0`, holding the teacher-panel work formerly attributed to `test-generator-16` in the spec text — that name appears stale; treat `test-generator-b0` as current):

- `step/views.py`, `step/urls.py`, `templates/step/base.html`, `templates/step/obligation.html`
- the migration widening `Obligation`'s unique constraint (touches an already-migrated shared table)

Every task below that touches one of those is marked **STOP — coordinate before landing** and must not be executed unattended. Everything else — new files under `step/models/`, `step/generation.py`, `step/workflow.py`, `step/constants.py`, `step/admin.py`, a new `step/classes_urls.py` / `step/classes_views.py`, new templates, and all of `diagnostics/` — has no such conflict and can proceed independently. This mirrors how the spine plan separated backend work that is safe to run unattended from work needing a human or peer checkpoint.

**One documented deviation from the spec's literal model code:** none — the model definitions in Task 2 are transcribed verbatim from the spec, including its constraint names (`one_teaching_class_per_grade_slot`, `one_structured_entry_per_student_checkpoint`), because the spec is already approved and there is no reason to rename anything it settled. Where the spec leaves a detail open — due-date placement for the three checkpoints, the score's numeric range — this plan makes an explicit, flagged choice rather than leaving a gap.

---

## Environment

- Work from `D:\Test generator`, on branch `step-platform-spine`.
- Interpreter: `.venv\Scripts\python.exe` — always this one.
- Run the **whole** suite, not just `step`: `.venv\Scripts\python.exe manage.py test -v 2`. Baseline at the start of this plan: 537 tests, 0 failures (confirmed by `test-generator-17`'s audit). That number must only ever go up.
- Faster iteration on one app: `.venv\Scripts\python.exe manage.py test step -v 2`
- Faster iteration on one module: `.venv\Scripts\python.exe manage.py test step.tests.test_classes_models -v 2`
- Commit after every task. Never use `--no-verify`.

**Codebase conventions already established in `step` (follow them, don't reinvent):**

- Tests are `django.test.TestCase`, not pytest.
- Models live in a `models/` package re-exported from `models/__init__.py`.
- Module docstrings explain **why**, not what.
- Stored vocabulary lives in `step/constants.py`; user-facing wording never does (spec §7.0 of the spine spec).
- State transitions go through `step/workflow.py` only.
- Management commands live in `step/management/commands/`.

---

## File structure

Created by this plan:

| File | Responsibility |
|---|---|
| `step/models/classes.py` | `TeachingClass`, `Student`, `ProgressEntry` |
| `step/classes_urls.py` | URL map for the classes/gradebook screens |
| `step/classes_views.py` | Views for the classes/gradebook screens |
| `templates/step/classes/list.html` | My classes |
| `templates/step/classes/create.html` | Create a class |
| `templates/step/classes/detail.html` | One class: roster + checkpoint state |
| `templates/step/classes/student_create.html` | Add a student |
| `templates/step/classes/student_detail.html` | A student: history |
| `templates/step/classes/note_create.html` | Add a note |
| `step/tests/test_classes_models.py` | Model tests |
| `step/tests/test_classes_views.py` | Screen tests |
| `step/tests/test_navigation_display_name.py` | Diagnostics rename tests |

Modified — no conflict:

| File | Change |
|---|---|
| `step/constants.py` | Checkpoint/skill vocabulary, the bespoke form slug, the checkpoint→type-name lookup |
| `step/models/__init__.py` | Re-export the three new models |
| `step/admin.py` | Register the three new models |
| `step/generation.py` | `generate_checkpoint_obligations(year)` |
| `step/workflow.py` | `sync_checkpoint(teaching_class, checkpoint)` |
| `step/management/commands/generate_obligations.py` | `--checkpoints` flag |
| `step/management/commands/seed_demo.py` | Catalogue gets the three checkpoint types, loses the two superseded generic assessment types |
| `diagnostics/navigation.py` | `display_name_for(grade, number)` |
| `diagnostics/views.py` | Passes the display name into `grade_detail` and `class_pack` context |
| `templates/diagnostics/grade_detail.html`, `templates/diagnostics/class_pack.html` | Print the display name where they currently print "Class N" |
| `step/tests/test_generation.py`, `step/tests/test_workflow.py`, `step/tests/test_obligation_models.py` | New test classes for the additions above |

Modified — **STOP, coordinate with `test-generator-b0` first** (see "Sequencing" below):

| File | Change |
|---|---|
| `step/models/obligations.py` + its migration | `Obligation.teaching_class` FK; unique constraint widens to `(type, educator, teaching_class, period_start)` |
| `step/views.py` | One branch in the `obligation` view for `form_slug == "assessment_checkpoint"` |
| `templates/step/obligation.html` | One branch rendering the roster-scoring form instead of the evidence uploader |
| `step/urls.py` | One `include("step.classes_urls")` line |
| `templates/step/base.html` | One new "Classes" rail link |
| `step/tests/test_views.py` | New `CheckpointObligationTests` |

---

## Phase 1 — Data model

### Task 1: Constants

**Files:**
- Modify: `step/constants.py`
- Test: `step/tests/test_app.py`

- [ ] **Step 1: Write the failing test**

Append to `step/tests/test_app.py`:

```python
class ClassesGradebookConstantsTests(TestCase):
    def test_checkpoint_and_skill_values_are_distinct(self):
        checkpoints = [v for v, _ in constants.CHECKPOINT_CHOICES]
        self.assertEqual(len(checkpoints), len(set(checkpoints)))
        skills = [v for v, _ in constants.SKILL_CHOICES]
        self.assertEqual(len(skills), len(set(skills)))

    def test_every_checkpoint_maps_to_an_obligation_type_name(self):
        checkpoints = {v for v, _ in constants.CHECKPOINT_CHOICES}
        self.assertEqual(set(constants.CHECKPOINT_OBLIGATION_NAME_TEMPLATES), checkpoints)

    def test_the_reverse_lookup_is_the_exact_inverse(self):
        for checkpoint, template in constants.CHECKPOINT_OBLIGATION_NAME_TEMPLATES.items():
            self.assertEqual(constants.NAME_TEMPLATE_TO_CHECKPOINT[template], checkpoint)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_app -v 2`
Expected: FAIL — `AttributeError: module 'step.constants' has no attribute 'CHECKPOINT_CHOICES'`

- [ ] **Step 3: Add the vocabulary**

Append to `step/constants.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_app -v 2`
Expected: PASS

Then the whole suite: `.venv\Scripts\python.exe manage.py test -v 2`
Expected: 537 + 3, all OK

- [ ] **Step 5: Commit**

```bash
git add step/constants.py step/tests/test_app.py
git commit -m "Add classes/gradebook vocabulary to step.constants"
```

---

### Task 2: `TeachingClass`, `Student`, `ProgressEntry`

**Files:**
- Create: `step/models/classes.py`
- Modify: `step/models/__init__.py`
- Test: `step/tests/test_classes_models.py`

- [ ] **Step 1: Write the failing test**

```python
# step/tests/test_classes_models.py
"""TeachingClass, Student and ProgressEntry — the classes/gradebook data model.

(grade, slot) is globally unique, not scoped to the educator: diagnostics'
four class packs per grade are a fact about the paper bank, and one teacher
owns a given grade+slot in practice (classes/gradebook spec, "Why (grade,
slot) is globally unique"). Score and comment are one row per checkpoint,
not two, because the structured checkpoint record *is* the progress note.
"""

from django.db import IntegrityError
from django.test import TestCase

from step import constants
from step.models import Educator, ProgressEntry, Region, Student, TeachingClass


class TeachingClassTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)

    def test_a_class_needs_a_grade_a_slot_and_a_name(self):
        teaching_class = TeachingClass.objects.create(
            educator=self.educator, grade=9, slot=2, display_name="9B"
        )
        self.assertEqual(str(teaching_class), "9B")

    def test_grade_and_slot_are_globally_unique(self):
        TeachingClass.objects.create(educator=self.educator, grade=9, slot=2, display_name="9B")
        other = Educator.objects.create(full_name="John Cruz", region=self.region)
        with self.assertRaises(IntegrityError):
            TeachingClass.objects.create(educator=other, grade=9, slot=2, display_name="9B again")

    def test_the_same_slot_in_a_different_grade_is_fine(self):
        TeachingClass.objects.create(educator=self.educator, grade=9, slot=2, display_name="9B")
        TeachingClass.objects.create(educator=self.educator, grade=10, slot=2, display_name="10B")
        self.assertEqual(TeachingClass.objects.count(), 2)

    def test_deleting_the_educator_deletes_the_class(self):
        teaching_class = TeachingClass.objects.create(
            educator=self.educator, grade=9, slot=1, display_name="9A"
        )
        self.educator.delete()
        self.assertFalse(TeachingClass.objects.filter(pk=teaching_class.pk).exists())


class StudentTests(TestCase):
    def setUp(self):
        region = Region.objects.create(name="Samarkand", code="samarkand")
        educator = Educator.objects.create(full_name="Maria Santos", region=region)
        self.teaching_class = TeachingClass.objects.create(
            educator=educator, grade=9, slot=1, display_name="9A"
        )

    def test_a_student_belongs_to_one_class(self):
        student = Student.objects.create(teaching_class=self.teaching_class, full_name="Aziz Karimov")
        self.assertEqual(str(student), "Aziz Karimov")
        self.assertIn(student, self.teaching_class.students.all())

    def test_deleting_the_class_deletes_its_students(self):
        student = Student.objects.create(teaching_class=self.teaching_class, full_name="Aziz Karimov")
        self.teaching_class.delete()
        self.assertFalse(Student.objects.filter(pk=student.pk).exists())


class ProgressEntryTests(TestCase):
    def setUp(self):
        region = Region.objects.create(name="Samarkand", code="samarkand")
        educator = Educator.objects.create(full_name="Maria Santos", region=region)
        teaching_class = TeachingClass.objects.create(
            educator=educator, grade=9, slot=1, display_name="9A"
        )
        self.student = Student.objects.create(teaching_class=teaching_class, full_name="Aziz Karimov")

    def test_a_structured_checkpoint_entry_needs_no_grammar_point(self):
        entry = ProgressEntry.objects.create(
            student=self.student, checkpoint=constants.CHECKPOINT_BOY,
            score=78, skill=constants.SKILL_READING,
        )
        self.assertIsNone(entry.grammar_point)
        self.assertEqual(entry.comment, "")

    def test_only_one_structured_entry_per_student_and_checkpoint(self):
        ProgressEntry.objects.create(
            student=self.student, checkpoint=constants.CHECKPOINT_BOY, score=78
        )
        with self.assertRaises(IntegrityError):
            ProgressEntry.objects.create(
                student=self.student, checkpoint=constants.CHECKPOINT_BOY, score=81
            )

    def test_a_blank_checkpoint_freeform_note_may_repeat(self):
        ProgressEntry.objects.create(student=self.student, comment="Doing well with irregular verbs.")
        ProgressEntry.objects.create(student=self.student, comment="Struggling with articles.")
        self.assertEqual(self.student.progress_entries.count(), 2)

    def test_a_different_checkpoint_is_a_different_row(self):
        ProgressEntry.objects.create(
            student=self.student, checkpoint=constants.CHECKPOINT_BOY, score=78
        )
        ProgressEntry.objects.create(
            student=self.student, checkpoint=constants.CHECKPOINT_MOY, score=82
        )
        self.assertEqual(self.student.progress_entries.count(), 2)

    def test_deleting_the_student_deletes_their_entries(self):
        entry = ProgressEntry.objects.create(
            student=self.student, checkpoint=constants.CHECKPOINT_BOY, score=78
        )
        self.student.delete()
        self.assertFalse(ProgressEntry.objects.filter(pk=entry.pk).exists())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_classes_models -v 2`
Expected: FAIL — `ImportError: cannot import name 'TeachingClass' from 'step.models'`

- [ ] **Step 3: Write the models**

```python
# step/models/classes.py
"""A teacher's own classes, students, and checkpoint progress.

New per the classes/gradebook spec (2026-08-27), which brings the Assessments
vertical forward ahead of Monthly Reporting and replaces the two-obligation
shape sketched in the platform spine spec §9 (annotated there to point here).

Wired into the obligation engine the same way every other vertical is: three
ObligationType rows with form_slug="assessment_checkpoint" (step/constants.py),
generated per class rather than per educator (step/generation.py) and
auto-completed once every student has a structured entry for a checkpoint
(step/workflow.py) — no evidence to check, so nothing waits for a reviewer.
"""

from django.db import models

from step import constants
from step.models.roster import Educator


class TeachingClass(models.Model):
    educator = models.ForeignKey(Educator, on_delete=models.CASCADE, related_name="classes")
    grade = models.PositiveSmallIntegerField()
    slot = models.PositiveSmallIntegerField()
    display_name = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["grade", "slot"]
        constraints = [
            models.UniqueConstraint(fields=["grade", "slot"], name="one_teaching_class_per_grade_slot"),
        ]

    def __str__(self) -> str:
        return self.display_name


class Student(models.Model):
    teaching_class = models.ForeignKey(TeachingClass, on_delete=models.CASCADE, related_name="students")
    full_name = models.CharField(max_length=200)

    class Meta:
        ordering = ["full_name"]

    def __str__(self) -> str:
        return self.full_name


class ProgressEntry(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="progress_entries")
    checkpoint = models.CharField(max_length=8, choices=constants.CHECKPOINT_CHOICES, blank=True)
    score = models.PositiveSmallIntegerField(null=True, blank=True)
    skill = models.CharField(max_length=16, choices=constants.SKILL_CHOICES, blank=True)
    grammar_point = models.ForeignKey(
        "content.GrammarPoint", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="step_progress_entries",
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # A blank checkpoint means a freeform note and may repeat freely;
            # a non-blank checkpoint is the one structured record for that
            # checkpoint and may not.
            models.UniqueConstraint(
                fields=["student", "checkpoint"],
                condition=~models.Q(checkpoint=""),
                name="one_structured_entry_per_student_checkpoint",
            ),
        ]

    def __str__(self) -> str:
        label = self.get_checkpoint_display() if self.checkpoint else "Note"
        return f"{label} \u2014 {self.student.full_name}"
```

- [ ] **Step 4: Update the model re-exports**

```python
# step/models/__init__.py
"""Re-exports every STEP model so callers import from `step.models` directly."""

from step.models.classes import ProgressEntry, Student, TeachingClass
from step.models.geography import District, Region
from step.models.roster import (
    AliasMapping,
    Educator,
    PendingSignup,
    RosterImport,
    School,
    UnresolvedRow,
)
from step.models.obligations import AcademicYear, Obligation, ObligationType, Term
from step.models.submissions import Evidence, Submission

__all__ = [
    "AcademicYear",
    "AliasMapping",
    "District",
    "Educator",
    "Evidence",
    "Obligation",
    "ObligationType",
    "PendingSignup",
    "ProgressEntry",
    "Region",
    "RosterImport",
    "School",
    "Student",
    "Submission",
    "TeachingClass",
    "Term",
    "UnresolvedRow",
]
```

- [ ] **Step 5: Make and run migrations**

Run: `.venv\Scripts\python.exe manage.py makemigrations step`
Expected: `step/migrations/0006_teachingclass_student_progressentry_and_more.py` (exact name may differ) creating the three models

Run: `.venv\Scripts\python.exe manage.py migrate`

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_classes_models -v 2`
Expected: PASS — 9 tests OK

- [ ] **Step 7: Commit**

```bash
git add step/models/classes.py step/models/__init__.py step/migrations step/tests/test_classes_models.py
git commit -m "Add TeachingClass, Student and ProgressEntry models"
```

---

### Task 3: Admin registration

**Files:**
- Modify: `step/admin.py`
- Test: manual only (admin registration has no dedicated unit test elsewhere in this app; `test_admin.py` covers the site-wide smoke test and will catch a broken registration)

- [ ] **Step 1: Register the models**

Add to the imports in `step/admin.py`:

```python
from step.models import (
    AcademicYear, AliasMapping, District, Educator, Evidence, Obligation,
    ObligationType, PendingSignup, ProgressEntry, Region, RosterImport,
    School, Student, Submission, TeachingClass, Term, UnresolvedRow,
)
```

Append at the end of the file:

```python
class StudentInline(admin.TabularInline):
    model = Student
    extra = 0


@admin.register(TeachingClass)
class TeachingClassAdmin(admin.ModelAdmin):
    list_display = ("display_name", "grade", "slot", "educator")
    list_filter = ("grade", "slot")
    search_fields = ("display_name", "educator__full_name")
    inlines = [StudentInline]


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("full_name", "teaching_class")
    list_filter = ("teaching_class__grade",)
    search_fields = ("full_name",)


@admin.register(ProgressEntry)
class ProgressEntryAdmin(admin.ModelAdmin):
    list_display = ("student", "checkpoint", "score", "skill", "created_at")
    list_filter = ("checkpoint", "skill")
    search_fields = ("student__full_name", "comment")
    readonly_fields = ("created_at",)
```

- [ ] **Step 2: Run the existing admin smoke test**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_admin -v 2`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add step/admin.py
git commit -m "Register TeachingClass, Student and ProgressEntry in the admin"
```

---

## Phase 2 — Obligation engine integration

### Task 4: `Obligation.teaching_class` — STOP, coordinate before landing

**This task must not be executed unattended.** It is the one migration touching an already-migrated shared table (`step/models/obligations.py`), and the spec's own "Sequencing" section flags it for explicit review. Before running Step 5 below, get a stopping point agreed with `test-generator-b0` (or the user) — post the plan and this task's diff and wait for an explicit go-ahead.

**Resolved before landing, not just flagged:** the first draft of this task widened the single unique constraint to `(type, educator, teaching_class, period_start)`. `test-generator-b0` traced why that is a live bug, not just reduced defense-in-depth: `step/generation.py`'s own docstring promises idempotency "through the unique constraint on (type, educator, period_start), so a scheduled run that is retried after a partial failure cannot double up," and `_create_missing`'s `get_or_create` never puts `teaching_class` in its lookup — for every non-checkpoint type it is always `NULL`. SQLite (and Postgres) treat `NULL` as distinct from `NULL` in a unique index, so widening the single constraint would silently remove that guarantee for a retried/overlapping generation run on every non-checkpoint type: both inserts would succeed, producing a genuine duplicate obligation, exactly the failure mode the docstring says cannot happen.

The fix, as specified by `test-generator-b0` and a condition of their sign-off: two conditional/partial constraints instead of one, keyed on whether `teaching_class` is set. This leaves the existing guarantee completely untouched for every type that does not use `teaching_class`, and adds real per-class uniqueness for the three checkpoint types:

```python
constraints = [
    models.UniqueConstraint(
        fields=["type", "educator", "period_start"],
        condition=models.Q(teaching_class__isnull=True),
        name="step_obligation_unique_per_period_no_class",
    ),
    models.UniqueConstraint(
        fields=["type", "educator", "teaching_class", "period_start"],
        condition=models.Q(teaching_class__isnull=False),
        name="step_obligation_unique_per_period_per_class",
    ),
]
```

Confirmed workable on Django 6.1 + SQLite. `test-generator-b0` asked to see the actual migration file written this way before final sign-off — send it their way directly once Step 4 below produces it.

**Files:**
- Modify: `step/models/obligations.py`, its migration
- Test: `step/tests/test_obligation_models.py`

- [ ] **Step 1: Write the failing test**

Append to `step/tests/test_obligation_models.py`:

```python
class TeachingClassObligationTests(TestCase):
    """Needs `TeachingClass` from `step.models` — add it to this file's existing
    `from step.models import ...` line at the top (Task 2 already put it there
    for `step/tests/test_classes_models.py`; this file predates that model)."""

    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.type = ObligationType.objects.create(
            name_template="Beginning-of-year diagnostic", category=constants.CATEGORY_ASSESSMENTS,
            cadence=constants.CADENCE_ANNUAL, evidence_spec=constants.EVIDENCE_NONE,
            form_slug=constants.FORM_SLUG_ASSESSMENT_CHECKPOINT,
        )

    def test_a_checkpoint_obligation_carries_its_teaching_class(self):
        teaching_class = TeachingClass.objects.create(
            educator=self.educator, grade=9, slot=1, display_name="9A"
        )
        obligation = Obligation.objects.create(
            type=self.type, educator=self.educator, teaching_class=teaching_class,
            period_kind=constants.PERIOD_YEAR, period_start=date(2025, 9, 1), due_date=date(2025, 10, 1),
        )
        self.assertEqual(obligation.teaching_class, teaching_class)

    def test_an_ordinary_obligation_still_has_no_teaching_class(self):
        obligation = Obligation.objects.create(
            type=self.type, educator=self.educator,
            period_kind=constants.PERIOD_YEAR, period_start=date(2025, 9, 1), due_date=date(2025, 10, 1),
        )
        self.assertIsNone(obligation.teaching_class)

    def test_two_classes_can_share_a_period_start_for_the_same_type(self):
        a = TeachingClass.objects.create(educator=self.educator, grade=9, slot=1, display_name="9A")
        b = TeachingClass.objects.create(educator=self.educator, grade=9, slot=2, display_name="9B")
        Obligation.objects.create(
            type=self.type, educator=self.educator, teaching_class=a,
            period_kind=constants.PERIOD_YEAR, period_start=date(2025, 9, 1), due_date=date(2025, 10, 1),
        )
        Obligation.objects.create(
            type=self.type, educator=self.educator, teaching_class=b,
            period_kind=constants.PERIOD_YEAR, period_start=date(2025, 9, 1), due_date=date(2025, 10, 1),
        )
        self.assertEqual(Obligation.objects.filter(type=self.type).count(), 2)

    def test_the_same_class_and_period_cannot_repeat(self):
        teaching_class = TeachingClass.objects.create(
            educator=self.educator, grade=9, slot=1, display_name="9A"
        )
        Obligation.objects.create(
            type=self.type, educator=self.educator, teaching_class=teaching_class,
            period_kind=constants.PERIOD_YEAR, period_start=date(2025, 9, 1), due_date=date(2025, 10, 1),
        )
        with self.assertRaises(IntegrityError):
            Obligation.objects.create(
                type=self.type, educator=self.educator, teaching_class=teaching_class,
                period_kind=constants.PERIOD_YEAR, period_start=date(2025, 9, 1), due_date=date(2025, 10, 1),
            )

    def test_the_pre_existing_no_class_uniqueness_guarantee_still_holds(self):
        """Pins the exact regression test-generator-b0 identified: before this
        task, (type, educator, period_start) alone was unique. It must stay
        that way for every obligation with no teaching_class — otherwise a
        retried generation run can silently double up (step/generation.py's
        idempotency docstring)."""
        Obligation.objects.create(
            type=self.type, educator=self.educator,
            period_kind=constants.PERIOD_YEAR, period_start=date(2025, 9, 1), due_date=date(2025, 10, 1),
        )
        with self.assertRaises(IntegrityError):
            Obligation.objects.create(
                type=self.type, educator=self.educator,
                period_kind=constants.PERIOD_YEAR, period_start=date(2025, 9, 1), due_date=date(2025, 10, 1),
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_obligation_models -v 2`
Expected: FAIL — `TypeError: Obligation() got unexpected keyword arguments: 'teaching_class'`

- [ ] **Step 3: Add the field and split the constraint**

In `step/models/obligations.py`, add the import, the field, and the two conditional constraints in place of the single one:

```python
from step.models.classes import TeachingClass  # add to the existing import block
```

```python
class Obligation(models.Model):
    """One concrete thing one educator owes for one period."""

    type = models.ForeignKey(ObligationType, on_delete=models.PROTECT, related_name="obligations")
    educator = models.ForeignKey(Educator, on_delete=models.CASCADE, related_name="obligations")
    teaching_class = models.ForeignKey(
        TeachingClass, null=True, blank=True, on_delete=models.CASCADE, related_name="obligations"
    )

    period_kind = models.CharField(max_length=16, choices=constants.PERIOD_KIND_CHOICES)
    period_start = models.DateField()
    period_label = models.CharField(
        max_length=32, blank=True,
        help_text='For terms, the term name ("Term 1"). Months derive their own label.',
    )

    due_date = models.DateField()
    due_date_overridden = models.BooleanField(
        default=False, help_text="Set when an extension was granted. Visible, never silent."
    )
    status = models.CharField(
        max_length=16, choices=constants.OBLIGATION_STATUS_CHOICES, default=constants.STATUS_NOT_STARTED
    )
    opened_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "type__category"]
        constraints = [
            models.UniqueConstraint(
                fields=["type", "educator", "period_start"],
                condition=models.Q(teaching_class__isnull=True),
                name="step_obligation_unique_per_period_no_class",
            ),
            models.UniqueConstraint(
                fields=["type", "educator", "teaching_class", "period_start"],
                condition=models.Q(teaching_class__isnull=False),
                name="step_obligation_unique_per_period_per_class",
            ),
        ]
        indexes = [
            models.Index(fields=["educator", "status"]),
            models.Index(fields=["type", "period_start", "status"]),
            models.Index(fields=["due_date"]),
        ]

    @property
    def period_display(self) -> str:
        if self.period_label:
            return self.period_label
        if self.period_kind == constants.PERIOD_MONTH:
            return self.period_start.strftime("%B %Y")
        if self.period_kind == constants.PERIOD_YEAR:
            return str(self.period_start.year)
        return ""

    @property
    def display_name(self) -> str:
        """What the teacher actually reads. Never exposes model vocabulary."""
        template = self.type.name_template
        period = self.period_display
        if "{period}" in template:
            return template.replace("{period}", period)
        return f"{template} - {period}" if period else template

    @property
    def period_end(self):
        return _period_end(self.period_start, self.period_kind)

    @property
    def latest_submission(self):
        """The current revision, or None. Earlier revisions stay in `submissions`."""
        return self.submissions.order_by("-revision").first()

    def __str__(self) -> str:
        return f"{self.display_name} ({self.educator.full_name})"
```

Everything except the new `teaching_class` field and the `constraints` list is transcribed unchanged from the current file — the properties, `__str__`, and every other field are identical to what is already there. Note the old constraint's name, `step_obligation_unique_per_period`, is retired — both new constraints get new names — so the migration removes one constraint and adds two, rather than altering one in place.

- [ ] **Step 4: Make the migration**

Run: `.venv\Scripts\python.exe manage.py makemigrations step`
Expected: one migration adding `teaching_class` and replacing the one constraint on `Obligation` with the two conditional ones. Open it and confirm it contains exactly an `AddField`, one constraint removal, and two constraint additions — nothing else. This is the file to send `test-generator-b0` for their final sign-off (they asked to see it, not just the plan text, before confirming).

- [ ] **Step 5: STOP — get sign-off, then migrate**

Do not run `migrate` until `test-generator-b0` has looked at the actual migration file from Step 4 and confirmed.

Once confirmed: `.venv\Scripts\python.exe manage.py migrate`

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_obligation_models -v 2`
Expected: PASS — original tests plus 5 new ones

Then the whole suite.

- [ ] **Step 7: Commit**

```bash
git add step/models/obligations.py step/migrations step/tests/test_obligation_models.py
git commit -m "Add Obligation.teaching_class for per-class checkpoint obligations"
```

---

### Task 5: Seed the three checkpoint `ObligationType` rows

Replaces the two generic "assessments" types in the demo catalogue (`Assessment Administration - {period}`, `Assessment Scoring & Submission - {period}`) with the three the new spec defines — the whole reason this spec exists is to replace that shape (spec header: "supersedes §9").

**Files:**
- Modify: `step/management/commands/seed_demo.py`
- Test: `step/tests/test_admin.py` or a focused addition — this plan adds a focused test module instead, since seed_demo's existing tests may live elsewhere; check first.

- [ ] **Step 1: Locate the existing seed_demo tests**

Run: `.venv\Scripts\python.exe manage.py test step -v 2 --pattern="test_app.py"` — if this doesn't surface seed_demo coverage, search directly:

```bash
grep -rl "seed_demo" step/tests/
```

Add the new assertions to whichever file already calls `call_command("seed_demo", ...)`. If none exists, create `step/tests/test_seed_demo.py` following this shape:

```python
# step/tests/test_seed_demo.py (only if no existing coverage was found)
"""seed_demo's catalogue is what the classes/gradebook checkpoints attach to
by name (step.constants.CHECKPOINT_OBLIGATION_NAME_TEMPLATES) — a renamed or
missing catalogue entry breaks generation silently, so the names are pinned
here."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from step import constants
from step.models import ObligationType


class SeedDemoCheckpointTypesTests(TestCase):
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_seed_demo -v 2` (or the existing file's path)
Expected: FAIL — the three checkpoint types are not in the catalogue yet

- [ ] **Step 3: Update the catalogue**

In `step/management/commands/seed_demo.py`, the `catalogue` list currently unpacks 6-tuples `(template, category, cadence, spec, review, description)` with no `form_slug`. Extend to 7-tuples, defaulting existing rows to `""`:

```python
        catalogue = [
            ("Monthly Report", constants.CATEGORY_MONTHLY_REPORTING, constants.CADENCE_MONTHLY,
             constants.EVIDENCE_FILE, True,
             "Your monthly report, with the page your director signed and stamped.", ""),
            ("CPD Online - Classroom Management", constants.CATEGORY_CPD_ONLINE, constants.CADENCE_TERMLY,
             constants.EVIDENCE_EITHER, False,
             "Finish the online course and send the certificate.", ""),
            ("ECA Programme Plan - {period}", constants.CATEGORY_ECA, constants.CADENCE_TERMLY,
             constants.EVIDENCE_LINK, True,
             "Your plan for this term's extra-curricular activity.", ""),
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
```

Also remove the now-stale `ObligationType.objects.filter(name_template__startswith="Assessment ").delete()` — actually, since `update_or_create` keys on `name_template` and the two old names no longer appear in the catalogue, they are simply never touched again. Add an explicit cleanup line right after the loop so re-running `seed_demo` on a database seeded by an older version of this command actually removes them, rather than leaving orphaned rows:

```python
        ObligationType.objects.filter(
            name_template__in=[
                "Assessment Administration - {period}",
                "Assessment Scoring & Submission - {period}",
            ]
        ).delete()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_seed_demo -v 2`
Expected: PASS

Then the whole suite — `seed_demo` is exercised by other tests too, so check nothing else assumed the old catalogue shape:

Run: `.venv\Scripts\python.exe manage.py test -v 2`
Expected: all OK. If something else asserted on "Assessment Administration" or "Assessment Scoring", update that assertion to match the new catalogue — that is an intended consequence of the supersession, not a regression.

- [ ] **Step 5: Commit**

```bash
git add step/management/commands/seed_demo.py step/tests/test_seed_demo.py
git commit -m "Replace the generic assessment types with the three checkpoint types"
```

---

### Task 6: `generation.generate_checkpoint_obligations(year)`

**Files:**
- Modify: `step/generation.py`
- Test: `step/tests/test_generation.py`

- [ ] **Step 1: Write the failing test**

Append to `step/tests/test_generation.py`, after adding `TeachingClass` to its existing `from step.models import ...` line at the top of the file:

```python
class GenerateCheckpointObligationsTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.maria = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.john = Educator.objects.create(full_name="John Cruz", region=self.region)
        self.year = AcademicYear.objects.create(
            label="2025-26", start=date(2025, 9, 1), end=date(2026, 5, 31), is_current=True
        )
        self.boy = ObligationType.objects.create(
            name_template="Beginning-of-year diagnostic", category=constants.CATEGORY_ASSESSMENTS,
            cadence=constants.CADENCE_ANNUAL, evidence_spec=constants.EVIDENCE_NONE,
            form_slug=constants.FORM_SLUG_ASSESSMENT_CHECKPOINT,
            due_rule={"kind": "days_after_period_start", "days": 30},
        )

    def test_one_obligation_per_teaching_class_not_per_educator(self):
        TeachingClass.objects.create(educator=self.maria, grade=9, slot=1, display_name="9A")
        TeachingClass.objects.create(educator=self.maria, grade=9, slot=2, display_name="9B")
        created = generation.generate_checkpoint_obligations(self.year)
        self.assertEqual(created, 2)
        self.assertEqual(Obligation.objects.filter(type=self.boy).count(), 2)

    def test_an_educator_with_no_class_gets_nothing(self):
        created = generation.generate_checkpoint_obligations(self.year)
        self.assertEqual(created, 0)

    def test_the_obligation_carries_the_classs_own_educator(self):
        teaching_class = TeachingClass.objects.create(
            educator=self.john, grade=10, slot=1, display_name="10A"
        )
        generation.generate_checkpoint_obligations(self.year)
        obligation = Obligation.objects.get(teaching_class=teaching_class)
        self.assertEqual(obligation.educator, self.john)

    def test_the_due_date_comes_from_the_types_own_rule_against_year_bounds(self):
        TeachingClass.objects.create(educator=self.maria, grade=9, slot=1, display_name="9A")
        generation.generate_checkpoint_obligations(self.year)
        obligation = Obligation.objects.get(type=self.boy)
        self.assertEqual(obligation.due_date, date(2025, 10, 1))
        self.assertEqual(obligation.period_kind, constants.PERIOD_YEAR)
        self.assertEqual(obligation.period_start, self.year.start)

    def test_running_twice_creates_nothing_new(self):
        TeachingClass.objects.create(educator=self.maria, grade=9, slot=1, display_name="9A")
        generation.generate_checkpoint_obligations(self.year)
        created = generation.generate_checkpoint_obligations(self.year)
        self.assertEqual(created, 0)

    def test_non_checkpoint_types_are_not_touched(self):
        ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY,
        )
        TeachingClass.objects.create(educator=self.maria, grade=9, slot=1, display_name="9A")
        generation.generate_checkpoint_obligations(self.year)
        self.assertEqual(Obligation.objects.exclude(type=self.boy).count(), 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_generation -v 2`
Expected: FAIL — `AttributeError: module 'step.generation' has no attribute 'generate_checkpoint_obligations'`

(This test file also needs `Obligation.teaching_class` from Task 4 — run Task 4 first.)

- [ ] **Step 3: Write the function**

Add to `step/generation.py`:

```python
from step.models import Educator, Obligation, ObligationType, TeachingClass  # extend the existing import
```

```python
@transaction.atomic
def generate_checkpoint_obligations(year) -> int:
    """Create this year's beginning/mid/end-of-year diagnostic obligations.

    One per TeachingClass, not per educator: a teacher with two classes owes
    two checkpoints, because each class has its own roster and its own
    completion state (classes/gradebook spec, "Generation").
    """
    created = 0
    for obligation_type in ObligationType.objects.filter(
        is_active=True, form_slug=constants.FORM_SLUG_ASSESSMENT_CHECKPOINT
    ):
        due = scheduling.due_date_for(obligation_type.due_rule, year.start, year.end)
        for teaching_class in TeachingClass.objects.select_related("educator"):
            _, made = Obligation.objects.get_or_create(
                type=obligation_type,
                educator=teaching_class.educator,
                teaching_class=teaching_class,
                period_start=year.start,
                defaults={"period_kind": constants.PERIOD_YEAR, "due_date": due},
            )
            if made:
                created += 1
    return created
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_generation -v 2`
Expected: PASS — original tests plus 6 new ones

- [ ] **Step 5: Wire it into the management command**

In `step/management/commands/generate_obligations.py`:

```python
    def add_arguments(self, parser):
        parser.add_argument("--month", help='Month to generate, as YYYY-MM. Defaults to today.')
        parser.add_argument("--term", help="Term name within the current academic year.")
        parser.add_argument(
            "--checkpoints", action="store_true",
            help="Also generate this year's beginning/mid/end-of-year diagnostic obligations.",
        )

    def handle(self, *args, **options):
        total = 0
        current = None  # resolved lazily so --month-only runs don't need a current year

        raw_month = options.get("month")
        if raw_month:
            try:
                year, month = raw_month.split("-")
                month_start = date(int(year), int(month), 1)
            except (ValueError, TypeError) as exc:
                raise CommandError(f"--month must look like 2026-05, got {raw_month!r}") from exc
        else:
            month_start = date.today().replace(day=1)

        total += generation.generate_for_month(month_start)

        term_name = options.get("term")
        if term_name:
            current = AcademicYear.objects.filter(is_current=True).first()
            if current is None:
                raise CommandError("No academic year is marked current.")
            term = Term.objects.filter(year=current, name=term_name).first()
            if term is None:
                raise CommandError(f"No term named {term_name!r} in {current.label}.")
            total += generation.generate_for_term(term)

        if options.get("checkpoints"):
            current = current or AcademicYear.objects.filter(is_current=True).first()
            if current is None:
                raise CommandError("No academic year is marked current.")
            total += generation.generate_checkpoint_obligations(current)

        self.stdout.write(self.style.SUCCESS(f"Created {total} obligations."))
```

- [ ] **Step 6: Run the whole suite**

Run: `.venv\Scripts\python.exe manage.py test -v 2`
Expected: all OK

- [ ] **Step 7: Commit**

```bash
git add step/generation.py step/management/commands/generate_obligations.py step/tests/test_generation.py
git commit -m "Generate checkpoint obligations per teaching class"
```

---

### Task 7: `workflow.sync_checkpoint(teaching_class, checkpoint)`

**Files:**
- Modify: `step/workflow.py`
- Test: `step/tests/test_workflow.py`

- [ ] **Step 1: Write the failing test**

Append to `step/tests/test_workflow.py`, after adding `ProgressEntry, Student, TeachingClass` to its existing `from step.models import ...` line at the top of the file:

```python
class SyncCheckpointTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.teaching_class = TeachingClass.objects.create(
            educator=self.educator, grade=9, slot=1, display_name="9A"
        )
        self.a = Student.objects.create(teaching_class=self.teaching_class, full_name="Aziz Karimov")
        self.b = Student.objects.create(teaching_class=self.teaching_class, full_name="Dilnoza Yusupova")

        self.boy_type = ObligationType.objects.create(
            name_template="Beginning-of-year diagnostic", category=constants.CATEGORY_ASSESSMENTS,
            cadence=constants.CADENCE_ANNUAL, evidence_spec=constants.EVIDENCE_NONE,
            form_slug=constants.FORM_SLUG_ASSESSMENT_CHECKPOINT,
        )
        self.obligation = Obligation.objects.create(
            type=self.boy_type, educator=self.educator, teaching_class=self.teaching_class,
            period_kind=constants.PERIOD_YEAR, period_start=date(2025, 9, 1), due_date=date(2025, 10, 1),
        )

    def test_incomplete_class_does_not_settle_the_obligation(self):
        ProgressEntry.objects.create(student=self.a, checkpoint=constants.CHECKPOINT_BOY, score=80)
        workflow.sync_checkpoint(self.teaching_class, constants.CHECKPOINT_BOY)
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_NOT_STARTED)

    def test_every_student_scored_settles_the_obligation(self):
        ProgressEntry.objects.create(student=self.a, checkpoint=constants.CHECKPOINT_BOY, score=80)
        ProgressEntry.objects.create(student=self.b, checkpoint=constants.CHECKPOINT_BOY, score=74)
        workflow.sync_checkpoint(self.teaching_class, constants.CHECKPOINT_BOY)
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_ACCEPTED)

    def test_settling_creates_no_submission(self):
        ProgressEntry.objects.create(student=self.a, checkpoint=constants.CHECKPOINT_BOY, score=80)
        ProgressEntry.objects.create(student=self.b, checkpoint=constants.CHECKPOINT_BOY, score=74)
        workflow.sync_checkpoint(self.teaching_class, constants.CHECKPOINT_BOY)
        self.assertEqual(self.obligation.submissions.count(), 0)

    def test_a_different_checkpoint_does_not_settle_this_one(self):
        ProgressEntry.objects.create(student=self.a, checkpoint=constants.CHECKPOINT_MOY, score=80)
        ProgressEntry.objects.create(student=self.b, checkpoint=constants.CHECKPOINT_MOY, score=74)
        workflow.sync_checkpoint(self.teaching_class, constants.CHECKPOINT_MOY)
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_NOT_STARTED)

    def test_a_class_with_no_students_never_settles(self):
        empty = TeachingClass.objects.create(educator=self.educator, grade=9, slot=2, display_name="9B")
        Obligation.objects.create(
            type=self.boy_type, educator=self.educator, teaching_class=empty,
            period_kind=constants.PERIOD_YEAR, period_start=date(2025, 9, 1), due_date=date(2025, 10, 1),
        )
        result = workflow.sync_checkpoint(empty, constants.CHECKPOINT_BOY)
        self.assertIsNone(result)

    def test_freeform_notes_do_not_count_toward_completion(self):
        ProgressEntry.objects.create(student=self.a, checkpoint=constants.CHECKPOINT_BOY, score=80)
        ProgressEntry.objects.create(student=self.b, comment="A freeform note, no checkpoint.")
        workflow.sync_checkpoint(self.teaching_class, constants.CHECKPOINT_BOY)
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_NOT_STARTED)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_workflow -v 2`
Expected: FAIL — `AttributeError: module 'step.workflow' has no attribute 'sync_checkpoint'`

- [ ] **Step 3: Write the function**

Add to `step/workflow.py`:

```python
from step.models import Evidence, Obligation, ProgressEntry, Submission  # extend the existing import
```

```python
def sync_checkpoint(teaching_class, checkpoint: str) -> Obligation | None:
    """Settle a class's checkpoint obligation once every student has a
    structured entry for it.

    Bypasses `submit` deliberately: a checkpoint obligation has no evidence to
    check and nothing for a reviewer to decide (classes/gradebook spec,
    "Auto-completion"). No Submission row is created — callers must not assume
    one exists for these obligations.
    """
    total = teaching_class.students.count()
    if total == 0:
        return None

    scored = (
        ProgressEntry.objects.filter(student__teaching_class=teaching_class, checkpoint=checkpoint)
        .values("student").distinct().count()
    )
    if scored < total:
        return None

    name_template = constants.CHECKPOINT_OBLIGATION_NAME_TEMPLATES[checkpoint]
    obligation = Obligation.objects.filter(
        teaching_class=teaching_class, type__name_template=name_template
    ).first()
    if obligation is None or obligation.status == constants.STATUS_ACCEPTED:
        return obligation

    obligation.status = constants.STATUS_ACCEPTED
    obligation.save(update_fields=["status"])
    return obligation
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_workflow -v 2`
Expected: PASS — original tests plus 7 new ones

Then the whole suite.

- [ ] **Step 5: Commit**

```bash
git add step/workflow.py step/tests/test_workflow.py
git commit -m "Auto-complete checkpoint obligations once every student is scored"
```

---

## Phase 3 — Diagnostics rename (no conflict — proceed freely)

### Task 8: `diagnostics.navigation.display_name_for`

**Files:**
- Modify: `diagnostics/navigation.py`
- Test: `step/tests/test_navigation_display_name.py` (lives under `step/tests` because it exercises the `step` → `diagnostics` read; equally could live in `diagnostics/tests/`— either is fine, this plan picks `step/tests` since the behaviour under test is "does diagnostics correctly read a TeachingClass I created")

- [ ] **Step 1: Write the failing test**

```python
# step/tests/test_navigation_display_name.py
"""diagnostics prints "Class N" for every class pack today. This is the one
place STEP's TeachingClass.display_name is allowed to leak into diagnostics —
a one-directional, read-only dependency (classes/gradebook spec, "Diagnostics
rename"). diagnostics gains no login and no editing here.
"""

from django.test import TestCase

from diagnostics.navigation import display_name_for
from step.models import Educator, Region, TeachingClass


class DisplayNameForTests(TestCase):
    def test_falls_back_to_class_n_when_no_teaching_class_exists(self):
        self.assertEqual(display_name_for(grade=9, number=2), "Class 2")

    def test_uses_the_teachers_own_name_when_a_teaching_class_exists(self):
        region = Region.objects.create(name="Samarkand", code="samarkand")
        educator = Educator.objects.create(full_name="Maria Santos", region=region)
        TeachingClass.objects.create(educator=educator, grade=9, slot=2, display_name="9B")
        self.assertEqual(display_name_for(grade=9, number=2), "9B")

    def test_a_class_in_a_different_grade_does_not_match(self):
        region = Region.objects.create(name="Samarkand", code="samarkand")
        educator = Educator.objects.create(full_name="Maria Santos", region=region)
        TeachingClass.objects.create(educator=educator, grade=10, slot=2, display_name="10B")
        self.assertEqual(display_name_for(grade=9, number=2), "Class 2")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_navigation_display_name -v 2`
Expected: FAIL — `ImportError: cannot import name 'display_name_for' from 'diagnostics.navigation'`

- [ ] **Step 3: Write the function**

Add to `diagnostics/navigation.py`, after the existing imports:

```python
from step.models import TeachingClass
```

Append at the end of the file:

```python
def display_name_for(grade: int, number: int) -> str:
    """The teacher's own name for this class pack, if one has been set.

    STEP owns the name (TeachingClass.display_name); diagnostics only reads
    it, never writes it (classes/gradebook spec, "Diagnostics rename"). Falls
    back to the positional "Class N" this module always showed, so an
    unclaimed pack still prints something sensible.
    """
    teaching_class = TeachingClass.objects.filter(grade=grade, slot=number).first()
    if teaching_class:
        return teaching_class.display_name
    return f"Class {number}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_navigation_display_name -v 2`
Expected: PASS — 3 tests OK

Then the whole suite — this adds a real (one-directional) import from `diagnostics` to `step`, so confirm nothing in `diagnostics`' own test suite assumed no such dependency existed:

Run: `.venv\Scripts\python.exe manage.py test diagnostics -v 2`
Expected: all OK

- [ ] **Step 5: Commit**

```bash
git add diagnostics/navigation.py step/tests/test_navigation_display_name.py
git commit -m "Add a read-only TeachingClass name lookup to diagnostics.navigation"
```

---

### Task 9: Wire the display name into the grade and class-pack screens

**Files:**
- Modify: `diagnostics/views.py`, `templates/diagnostics/grade_detail.html`, `templates/diagnostics/class_pack.html`
- Test: `diagnostics/tests/test_views.py` (check for an existing views test file first; if absent, extend `diagnostics/tests/test_navigation.py` or create `diagnostics/tests/test_class_display_names.py`)

- [ ] **Step 1: Find or create the test location**

```bash
grep -rl "grade_detail\|class_pack" diagnostics/tests/
```

Add to whichever file already tests those two views. If none does, create `diagnostics/tests/test_class_display_names.py`:

```python
"""The grade and class-pack screens must show a teacher's own class name once
one exists — see diagnostics.navigation.display_name_for and the
classes/gradebook spec's "Diagnostics rename"."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from step.models import Educator, Region, TeachingClass


class GradeDetailDisplayNameTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("staff1", password="pw", is_staff=True)
        self.client.login(username="staff1", password="pw")

    def test_an_unclaimed_pack_still_shows_class_n(self):
        response = self.client.get(reverse("diagnostics:grade_detail", args=[9]))
        self.assertContains(response, "Class 2")

    def test_a_claimed_pack_shows_the_teachers_name(self):
        region = Region.objects.create(name="Samarkand", code="samarkand")
        educator = Educator.objects.create(full_name="Maria Santos", region=region)
        TeachingClass.objects.create(educator=educator, grade=9, slot=2, display_name="9B")
        response = self.client.get(reverse("diagnostics:grade_detail", args=[9]))
        self.assertContains(response, "9B")


class ClassPackDisplayNameTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("staff2", password="pw", is_staff=True)
        self.client.login(username="staff2", password="pw")

    def test_the_class_pack_page_shows_the_teachers_name(self):
        region = Region.objects.create(name="Samarkand", code="samarkand")
        educator = Educator.objects.create(full_name="Maria Santos", region=region)
        TeachingClass.objects.create(educator=educator, grade=9, slot=1, display_name="9A")
        response = self.client.get(reverse("diagnostics:class_pack", args=[9, 1]))
        self.assertContains(response, "9A")
```

Adapt the `setUp` login and URL names to whatever `diagnostics/tests/` already uses if an existing pattern differs (check `diagnostics/tests/test_navigation.py` and any `test_views.py` for the real login/permission fixture before assuming `is_staff=True` is sufficient — `diagnostics/views.py`'s `_visible_grades` may impose its own access rule).

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_class_display_names -v 2`
Expected: FAIL — response does not contain "9B" / "9A" (still shows "Class 2" / "Class 1")

- [ ] **Step 3: Pass the display name through the views**

In `diagnostics/views.py`, `display_name_for` joins the existing import from `diagnostics.navigation` (which currently reads `from diagnostics.navigation import (` followed by `CLASS_NUMBERS`, `CLASSES_PER_GRADE`, `variant_span`, `variants_for_class`, and whatever else that block already lists — check the real file, since this plan's earlier read of it only confirmed those four names exist, not the complete list). Add `display_name_for` alphabetically into that same `(...)` block; do not start a second `from diagnostics.navigation import` line.

In `grade_detail`, add `"display_name": display_name_for(grade, number)` to each pack dict:

```python
        packs.append(
            {
                "number": number,
                "display_name": display_name_for(grade, number),
                "span": variant_span(number),
                "paper_count": len(members),
                "issued_count": sum(1 for paper in members if paper.issue_count),
            }
        )
```

In `class_pack`, add `"class_display_name": display_name_for(grade, number)` to the context:

```python
    return render(
        request,
        "diagnostics/class_pack.html",
        {
            "grade": grade,
            "class_number": number,
            "class_display_name": display_name_for(grade, number),
            "span": variant_span(number),
            "papers": _pack_papers(request.user, grade, number),
            "prev_class": number - 1 if number > 1 else None,
            "next_class": number + 1 if number < CLASSES_PER_GRADE else None,
            "generation_open": GenerationWindow.load().is_open,
        },
    )
```

- [ ] **Step 4: Update the templates**

In `templates/diagnostics/grade_detail.html`, line 53, change the title span (leave the "idx" badge on line 52 alone — it is a positional code like "Class 01", not the class's name):

```diff
-      <span class="ttl">Class {{ pack.number }}</span>
+      <span class="ttl">{{ pack.display_name }}</span>
```

In `templates/diagnostics/class_pack.html`, both occurrences of `Class {{ class_number }}` are the page's actual title, not a positional code — replace both:

```diff
-  <b>Class {{ class_number }}</b>
+  <b>{{ class_display_name }}</b>
```
(line 18, the breadcrumb)

```diff
-    <h1 class="doc">Class {{ class_number }}</h1>
+    <h1 class="doc">{{ class_display_name }}</h1>
```
(line 24)

```diff
-    <b>Class {{ class_number }}</b>
+    <b>{{ class_display_name }}</b>
```
(line 30, the "ref" corner badge)

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_class_display_names -v 2`
Expected: PASS — 3 tests OK

Then the whole diagnostics suite, since the templates changed:

Run: `.venv\Scripts\python.exe manage.py test diagnostics -v 2`
Expected: all OK — check specifically for any existing test asserting the literal string `"Class {{ number }}"` output that this change would break; update it to expect `display_name_for`'s output instead if so.

Then the whole suite.

- [ ] **Step 6: Commit**

```bash
git add diagnostics/views.py templates/diagnostics/grade_detail.html templates/diagnostics/class_pack.html diagnostics/tests/test_class_display_names.py
git commit -m "Show the teacher's own class name on the grade and class-pack screens"
```

---

## Phase 4 — Screens

### Task 10: `step/classes_urls.py`, `step/classes_views.py` — My classes, Create a class

New module, not `step/views.py` — this keeps every classes/gradebook screen out of the file `test-generator-b0` owns, except the one obligation-page branch Task 13 cannot avoid. `_educator`/`_chrome` are small enough to duplicate here rather than importing private names out of `step/views.py`; reconciling that duplication later (a shared `step/context.py`, say) is a fair follow-up, not something worth blocking this plan on.

**Files:**
- Create: `step/classes_urls.py`, `step/classes_views.py`, `templates/step/classes/list.html`, `templates/step/classes/create.html`
- Test: `step/tests/test_classes_views.py`

- [ ] **Step 1: Write the failing test**

```python
# step/tests/test_classes_views.py
"""The classes/gradebook screens. GOV.UK one-thing-per-page, matching the
convention `step/tests/test_views.py` already pins for the obligation
screens: a teacher can never see or touch another teacher's classes.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from step.models import Educator, Region, TeachingClass


class ClassListTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region, user=self.user)
        self.client.login(username="maria", password="pw")

    def test_requires_signing_in(self):
        self.client.logout()
        response = self.client.get(reverse("step:class_list"))
        self.assertEqual(response.status_code, 302)

    def test_shows_only_my_own_classes(self):
        TeachingClass.objects.create(educator=self.educator, grade=9, slot=1, display_name="9A")
        other = Educator.objects.create(full_name="John Cruz", region=self.region)
        TeachingClass.objects.create(educator=other, grade=9, slot=2, display_name="9B")

        response = self.client.get(reverse("step:class_list"))
        names = [c.display_name for c in response.context["classes"]]
        self.assertEqual(names, ["9A"])


class ClassCreateTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region, user=self.user)
        self.client.login(username="maria", password="pw")

    def test_creates_a_class_owned_by_the_signed_in_teacher(self):
        response = self.client.post(
            reverse("step:class_create"), {"grade": "9", "slot": "1", "display_name": "9A"}
        )
        teaching_class = TeachingClass.objects.get(display_name="9A")
        self.assertEqual(teaching_class.educator, self.educator)
        self.assertRedirects(response, reverse("step:class_detail", args=[teaching_class.pk]))

    def test_a_grade_outside_9_to_11_is_rejected(self):
        response = self.client.post(
            reverse("step:class_create"), {"grade": "12", "slot": "1", "display_name": "9A"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TeachingClass.objects.exists())

    def test_a_slot_outside_1_to_4_is_rejected(self):
        response = self.client.post(
            reverse("step:class_create"), {"grade": "9", "slot": "5", "display_name": "9A"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TeachingClass.objects.exists())

    def test_a_grade_and_slot_already_taken_is_rejected_with_a_plain_message(self):
        TeachingClass.objects.create(educator=self.educator, grade=9, slot=1, display_name="9A")
        response = self.client.post(
            reverse("step:class_create"), {"grade": "9", "slot": "1", "display_name": "9A again"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(TeachingClass.objects.count(), 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_classes_views -v 2`
Expected: FAIL — `NoReverseMatch: 'class_list' is not a registered namespace`

- [ ] **Step 3: Write the views**

```python
# step/classes_views.py
"""Screens for a teacher's own classes, students and checkpoint scoring.

Kept out of step/views.py deliberately: that file, step/urls.py, and
templates/step/base.html are owned by another session's teacher-panel work
this round, and every route here is new — only the checkpoint branch inside
the existing obligation page (see step/views.py's obligation view once that
coordination lands) has to live in the shared file.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from step import constants, presentation
from step.models import Educator, TeachingClass


def _educator(request) -> Educator:
    educator = Educator.objects.filter(user=request.user).select_related("region", "school").first()
    if educator is None:
        raise Http404("This account is not linked to a teacher record yet.")
    return educator


def _chrome(educator) -> dict:
    return {
        "educator": educator,
        "file_ref": presentation.file_reference(educator),
        "categories": constants.CATEGORY_CHOICES,
        "returned_count": educator.obligations.filter(status=constants.STATUS_RETURNED).count(),
    }


@login_required
def class_list(request):
    educator = _educator(request)
    context = {"nav": "classes", "classes": educator.classes.all()}
    context.update(_chrome(educator))
    return render(request, "step/classes/list.html", context)


@login_required
def class_create(request):
    educator = _educator(request)

    if request.method == "POST":
        grade_raw = (request.POST.get("grade") or "").strip()
        slot_raw = (request.POST.get("slot") or "").strip()
        display_name = (request.POST.get("display_name") or "").strip()

        error = None
        grade = slot = None
        if not grade_raw.isdigit() or int(grade_raw) not in constants.TEACHING_GRADES:
            error = f"Choose a grade from {', '.join(str(g) for g in constants.TEACHING_GRADES)}."
        elif not slot_raw.isdigit() or not (1 <= int(slot_raw) <= constants.TEACHING_SLOTS_PER_GRADE):
            error = f"Choose a class number from 1 to {constants.TEACHING_SLOTS_PER_GRADE}."
        elif not display_name:
            error = "Give the class a name."
        else:
            grade, slot = int(grade_raw), int(slot_raw)

        if error is None:
            try:
                teaching_class = TeachingClass.objects.create(
                    educator=educator, grade=grade, slot=slot, display_name=display_name
                )
            except IntegrityError:
                error = f"Grade {grade}, class {slot} already belongs to another teacher."
            else:
                messages.success(request, f"{display_name} has been added.")
                return redirect("step:class_detail", pk=teaching_class.pk)

        messages.error(request, error)
        context = {
            "nav": "classes",
            "grades": constants.TEACHING_GRADES,
            "slots": range(1, constants.TEACHING_SLOTS_PER_GRADE + 1),
            "form": {"grade": grade_raw, "slot": slot_raw, "display_name": display_name},
        }
        context.update(_chrome(educator))
        return render(request, "step/classes/create.html", context)

    context = {
        "nav": "classes",
        "grades": constants.TEACHING_GRADES,
        "slots": range(1, constants.TEACHING_SLOTS_PER_GRADE + 1),
        "form": {},
    }
    context.update(_chrome(educator))
    return render(request, "step/classes/create.html", context)
```

```python
# step/classes_urls.py
from django.urls import path

from step import classes_views

urlpatterns = [
    path("", classes_views.class_list, name="class_list"),
    path("new/", classes_views.class_create, name="class_create"),
]
```

(`class_detail`, referenced above by `redirect`, is added in Task 11 — this task will not fully pass until that lands; the two tasks are written to be executed back-to-back, same as the spine plan's roster tasks depended on geography existing first.)

- [ ] **Step 4: Write the templates**

```html
{# templates/step/classes/list.html #}
{% extends "step/base.html" %}

{% block title %}My classes — STEP{% endblock %}

{% block content %}
<div class="head">
  <h1>My classes</h1>
</div>

<div class="columns">
  <div>
    <section class="block" aria-labelledby="classes-h">
      <h2 class="block__title" id="classes-h">Your classes</h2>
      <div class="block__body">
        {% if classes %}
        <ul class="filed">
          {% for teaching_class in classes %}
          <li>
            <div class="filed__what">
              <a href="{% url 'step:class_detail' teaching_class.pk %}">{{ teaching_class.display_name }}</a>
            </div>
            <div class="filed__when">Grade {{ teaching_class.grade }} &middot; {{ teaching_class.students.count }} student{{ teaching_class.students.count|pluralize }}</div>
          </li>
          {% endfor %}
        </ul>
        {% else %}
        <p>You have not added a class yet.</p>
        {% endif %}

        <div class="actions" style="border-top:2px solid var(--ink); padding-top:22px; margin-top:22px">
          <a class="btn btn--primary btn--lg" href="{% url 'step:class_create' %}">Add a class</a>
        </div>
      </div>
    </section>
  </div>
</div>
{% endblock %}
```

```html
{# templates/step/classes/create.html #}
{% extends "step/base.html" %}

{% block title %}Create a class — STEP{% endblock %}

{% block content %}
<nav class="crumbs" aria-label="Breadcrumb">
  <a href="{% url 'step:class_list' %}">My classes</a><span>/</span>Create a class
</nav>

<div class="head">
  <h1>Create a class</h1>
</div>

<div class="columns">
  <div>
    <section class="block" aria-labelledby="create-h">
      <h2 class="block__title" id="create-h">Which class is this</h2>
      <div class="block__body">
        <form method="post" novalidate>
          {% csrf_token %}

          <div class="field">
            <span class="field__label" id="grade-h">Grade</span>
            <div role="radiogroup" aria-labelledby="grade-h">
              {% for value in grades %}
              <label class="choice">
                <input type="radio" name="grade" value="{{ value }}" {% if form.grade == value|stringformat:"s" %}checked{% endif %}>
                <span class="choice__text">Grade <span class="num">{{ value }}</span></span>
              </label>
              {% endfor %}
            </div>
          </div>

          <div class="field">
            <span class="field__label" id="slot-h">Class number</span>
            <p class="field__hint">Matches the class pack number diagnostics already uses for this grade.</p>
            <div role="radiogroup" aria-labelledby="slot-h">
              {% for value in slots %}
              <label class="choice">
                <input type="radio" name="slot" value="{{ value }}" {% if form.slot == value|stringformat:"s" %}checked{% endif %}>
                <span class="choice__text">Class <span class="num">{{ value }}</span></span>
              </label>
              {% endfor %}
            </div>
          </div>

          <div class="field">
            <label class="field__label" for="display_name">What you call this class</label>
            <p class="field__hint">For example, 9B.</p>
            <input class="input" type="text" id="display_name" name="display_name" value="{{ form.display_name|default:'' }}">
          </div>

          <div class="actions" style="border-top:2px solid var(--ink); padding-top:22px">
            <button class="btn btn--primary btn--lg" type="submit">Create the class</button>
            <a class="btn btn--quiet" href="{% url 'step:class_list' %}">Back without creating</a>
          </div>
        </form>
      </div>
    </section>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Run tests**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_classes_views -v 2`
Expected: `ClassListTests` fails (`class_list` URL doesn't resolve yet — `step.urls` hasn't been wired, see Task 14) and `ClassCreateTests.test_creates_a_class...` fails the same way, but the validation-only tests pass once URLs resolve. This task cannot fully go green until Task 14's `include()` lands — that is expected and is why Task 14 exists as its own checkpoint rather than being folded in here.

Do not attempt to work around this by adding the include yourself — that edits the shared `step/urls.py` outside the coordinated checkpoint. Leave the red tests as the visible marker that Task 14 is still pending.

- [ ] **Step 6: Commit**

```bash
git add step/classes_urls.py step/classes_views.py templates/step/classes/list.html templates/step/classes/create.html step/tests/test_classes_views.py
git commit -m "Add My classes and Create a class screens (not yet routed)"
```

---

### Task 11: One class (roster + checkpoint state), Add a student

**Files:**
- Modify: `step/classes_urls.py`, `step/classes_views.py`
- Create: `templates/step/classes/detail.html`, `templates/step/classes/student_create.html`
- Test: `step/tests/test_classes_views.py`

- [ ] **Step 1: Write the failing test**

Append to `step/tests/test_classes_views.py`:

```python
from step.models import Obligation, ObligationType, ProgressEntry, Student
from step import constants


class ClassDetailTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region, user=self.user)
        self.teaching_class = TeachingClass.objects.create(
            educator=self.educator, grade=9, slot=1, display_name="9A"
        )
        self.client.login(username="maria", password="pw")

    def test_another_teachers_class_is_not_visible(self):
        other = Educator.objects.create(full_name="John Cruz", region=self.region)
        other_class = TeachingClass.objects.create(educator=other, grade=9, slot=2, display_name="9B")
        response = self.client.get(reverse("step:class_detail", args=[other_class.pk]))
        self.assertEqual(response.status_code, 404)

    def test_shows_the_roster(self):
        Student.objects.create(teaching_class=self.teaching_class, full_name="Aziz Karimov")
        response = self.client.get(reverse("step:class_detail", args=[self.teaching_class.pk]))
        self.assertContains(response, "Aziz Karimov")

    def test_shows_checkpoint_completion_state(self):
        student = Student.objects.create(teaching_class=self.teaching_class, full_name="Aziz Karimov")
        obligation_type = ObligationType.objects.create(
            name_template="Beginning-of-year diagnostic", category=constants.CATEGORY_ASSESSMENTS,
            cadence=constants.CADENCE_ANNUAL, evidence_spec=constants.EVIDENCE_NONE,
            form_slug=constants.FORM_SLUG_ASSESSMENT_CHECKPOINT,
        )
        Obligation.objects.create(
            type=obligation_type, educator=self.educator, teaching_class=self.teaching_class,
            period_kind=constants.PERIOD_YEAR, period_start=date(2025, 9, 1), due_date=date(2025, 10, 1),
        )
        response = self.client.get(reverse("step:class_detail", args=[self.teaching_class.pk]))
        checkpoints = {row["checkpoint"]: row for row in response.context["checkpoints"]}
        self.assertEqual(checkpoints[constants.CHECKPOINT_BOY]["done"], 0)
        self.assertEqual(checkpoints[constants.CHECKPOINT_BOY]["total"], 1)


class StudentCreateTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region, user=self.user)
        self.teaching_class = TeachingClass.objects.create(
            educator=self.educator, grade=9, slot=1, display_name="9A"
        )
        self.client.login(username="maria", password="pw")

    def test_adds_a_student_to_the_class(self):
        response = self.client.post(
            reverse("step:student_create", args=[self.teaching_class.pk]), {"full_name": "Aziz Karimov"}
        )
        self.assertTrue(Student.objects.filter(teaching_class=self.teaching_class, full_name="Aziz Karimov").exists())
        self.assertRedirects(response, reverse("step:class_detail", args=[self.teaching_class.pk]))

    def test_cannot_add_a_student_to_another_teachers_class(self):
        other = Educator.objects.create(full_name="John Cruz", region=self.region)
        other_class = TeachingClass.objects.create(educator=other, grade=9, slot=2, display_name="9B")
        response = self.client.post(
            reverse("step:student_create", args=[other_class.pk]), {"full_name": "Aziz Karimov"}
        )
        self.assertEqual(response.status_code, 404)
```

Add `from datetime import date` to the top of `step/tests/test_classes_views.py` if not already present from Task 10.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_classes_views -v 2`
Expected: FAIL — `NoReverseMatch: 'class_detail' is not a registered namespace`

- [ ] **Step 3: Write the views**

Add to `step/classes_views.py`:

```python
from step.models import Educator, Obligation, ProgressEntry, Student, TeachingClass  # extend the existing import


def _checkpoint_summary(teaching_class) -> list[dict]:
    total = teaching_class.students.count()
    summary = []
    for value, label in constants.CHECKPOINT_CHOICES:
        done = (
            ProgressEntry.objects.filter(student__teaching_class=teaching_class, checkpoint=value)
            .values("student").distinct().count()
        )
        name_template = constants.CHECKPOINT_OBLIGATION_NAME_TEMPLATES[value]
        obligation = Obligation.objects.filter(
            teaching_class=teaching_class, type__name_template=name_template
        ).first()
        summary.append({
            "checkpoint": value, "label": label, "done": done, "total": total,
            "obligation": obligation,
        })
    return summary


@login_required
def class_detail(request, pk: int):
    educator = _educator(request)
    teaching_class = get_object_or_404(TeachingClass, pk=pk, educator=educator)

    context = {
        "nav": "classes",
        "teaching_class": teaching_class,
        "students": teaching_class.students.all(),
        "checkpoints": _checkpoint_summary(teaching_class),
    }
    context.update(_chrome(educator))
    return render(request, "step/classes/detail.html", context)


@login_required
def student_create(request, pk: int):
    educator = _educator(request)
    teaching_class = get_object_or_404(TeachingClass, pk=pk, educator=educator)

    if request.method == "POST":
        full_name = (request.POST.get("full_name") or "").strip()
        if not full_name:
            messages.error(request, "Enter the student's name.")
        else:
            Student.objects.create(teaching_class=teaching_class, full_name=full_name)
            messages.success(request, f"{full_name} has been added to {teaching_class.display_name}.")
            return redirect("step:class_detail", pk=teaching_class.pk)

    context = {"nav": "classes", "teaching_class": teaching_class}
    context.update(_chrome(educator))
    return render(request, "step/classes/student_create.html", context)
```

Update `step/classes_urls.py`:

```python
from django.urls import path

from step import classes_views

urlpatterns = [
    path("", classes_views.class_list, name="class_list"),
    path("new/", classes_views.class_create, name="class_create"),
    path("<int:pk>/", classes_views.class_detail, name="class_detail"),
    path("<int:pk>/students/new/", classes_views.student_create, name="student_create"),
]
```

- [ ] **Step 4: Write the templates**

```html
{# templates/step/classes/detail.html #}
{% extends "step/base.html" %}

{% block title %}{{ teaching_class.display_name }} — STEP{% endblock %}

{% block content %}
<nav class="crumbs" aria-label="Breadcrumb">
  <a href="{% url 'step:class_list' %}">My classes</a><span>/</span>{{ teaching_class.display_name }}
</nav>

<div class="head">
  <h1>{{ teaching_class.display_name }}</h1>
  <p>Grade {{ teaching_class.grade }}</p>
</div>

<div class="columns">
  <div>
    <section class="block" aria-labelledby="roster-h">
      <h2 class="block__title" id="roster-h">Roster</h2>
      <div class="block__body">
        {% if students %}
        <ul class="filed">
          {% for student in students %}
          <li>
            <div class="filed__what"><a href="{% url 'step:student_detail' student.pk %}">{{ student.full_name }}</a></div>
          </li>
          {% endfor %}
        </ul>
        {% else %}
        <p>No students yet.</p>
        {% endif %}
        <div class="actions" style="border-top:2px solid var(--ink); padding-top:22px; margin-top:22px">
          <a class="btn btn--primary" href="{% url 'step:student_create' teaching_class.pk %}">Add a student</a>
        </div>
      </div>
    </section>
  </div>

  <div>
    <section class="block" aria-labelledby="checkpoints-h">
      <h2 class="block__title" id="checkpoints-h">Checkpoints</h2>
      <div class="block__body" style="font-size:14.5px">
        {% for row in checkpoints %}
        <p style="margin-bottom:11px">
          <strong>{{ row.label }}</strong><br>
          {% if row.obligation and row.obligation.status == 'accepted' %}
          <span class="impression impression--seal">Complete</span>
          {% else %}
          <span class="num">{{ row.done }}</span> of <span class="num">{{ row.total }}</span> scored
          {% if row.obligation %}
          &middot; <a href="{% url 'step:obligation' row.obligation.pk %}">Score it</a>
          {% endif %}
          {% endif %}
        </p>
        {% endfor %}
      </div>
    </section>
  </div>
</div>
{% endblock %}
```

```html
{# templates/step/classes/student_create.html #}
{% extends "step/base.html" %}

{% block title %}Add a student — {{ teaching_class.display_name }} — STEP{% endblock %}

{% block content %}
<nav class="crumbs" aria-label="Breadcrumb">
  <a href="{% url 'step:class_list' %}">My classes</a><span>/</span>
  <a href="{% url 'step:class_detail' teaching_class.pk %}">{{ teaching_class.display_name }}</a><span>/</span>Add a student
</nav>

<div class="head"><h1>Add a student</h1></div>

<div class="columns">
  <div>
    <section class="block" aria-labelledby="add-student-h">
      <h2 class="block__title" id="add-student-h">Student's name</h2>
      <div class="block__body">
        <form method="post" novalidate>
          {% csrf_token %}
          <div class="field">
            <label class="field__label" for="full_name">Full name</label>
            <input class="input" type="text" id="full_name" name="full_name" autofocus>
          </div>
          <div class="actions" style="border-top:2px solid var(--ink); padding-top:22px">
            <button class="btn btn--primary btn--lg" type="submit">Add the student</button>
            <a class="btn btn--quiet" href="{% url 'step:class_detail' teaching_class.pk %}">Back without adding</a>
          </div>
        </form>
      </div>
    </section>
  </div>
</div>
{% endblock %}
```

Note: `detail.html` links to `step:obligation` (the existing, shared obligation-page URL) and `step:student_detail` (added in Task 12). Both resolve once Task 14's `include()` and the existing `step:obligation` route are in place — same "expected red until the checkpoint lands" situation as Task 10.

- [ ] **Step 5: Run tests**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_classes_views -v 2`
Expected: the non-URL-resolution assertions (404 on another teacher's class, roster contents, checkpoint counts) pass; full-suite green still waits on Task 14.

- [ ] **Step 6: Commit**

```bash
git add step/classes_urls.py step/classes_views.py templates/step/classes/detail.html templates/step/classes/student_create.html step/tests/test_classes_views.py
git commit -m "Add the one-class and add-a-student screens"
```

---

### Task 12: A student (history), Add a note

**Files:**
- Modify: `step/classes_urls.py`, `step/classes_views.py`
- Create: `templates/step/classes/student_detail.html`, `templates/step/classes/note_create.html`
- Test: `step/tests/test_classes_views.py`

- [ ] **Step 1: Write the failing test**

Append to `step/tests/test_classes_views.py`:

```python
class StudentDetailTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region, user=self.user)
        self.teaching_class = TeachingClass.objects.create(
            educator=self.educator, grade=9, slot=1, display_name="9A"
        )
        self.student = Student.objects.create(teaching_class=self.teaching_class, full_name="Aziz Karimov")
        self.client.login(username="maria", password="pw")

    def test_shows_the_students_entries(self):
        ProgressEntry.objects.create(
            student=self.student, checkpoint=constants.CHECKPOINT_BOY, score=80,
            skill=constants.SKILL_READING, comment="Good pace.",
        )
        response = self.client.get(reverse("step:student_detail", args=[self.student.pk]))
        self.assertContains(response, "Good pace.")

    def test_another_teachers_student_is_not_visible(self):
        other = Educator.objects.create(full_name="John Cruz", region=self.region)
        other_class = TeachingClass.objects.create(educator=other, grade=9, slot=2, display_name="9B")
        other_student = Student.objects.create(teaching_class=other_class, full_name="Someone Else")
        response = self.client.get(reverse("step:student_detail", args=[other_student.pk]))
        self.assertEqual(response.status_code, 404)


class NoteCreateTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region, user=self.user)
        self.teaching_class = TeachingClass.objects.create(
            educator=self.educator, grade=9, slot=1, display_name="9A"
        )
        self.student = Student.objects.create(teaching_class=self.teaching_class, full_name="Aziz Karimov")
        self.client.login(username="maria", password="pw")

    def test_adds_a_freeform_note_with_no_checkpoint_and_no_score(self):
        self.client.post(
            reverse("step:note_create", args=[self.student.pk]),
            {"skill": constants.SKILL_WRITING, "comment": "Needs work on tenses."},
        )
        entry = ProgressEntry.objects.get(student=self.student)
        self.assertEqual(entry.checkpoint, "")
        self.assertIsNone(entry.score)
        self.assertEqual(entry.comment, "Needs work on tenses.")

    def test_a_note_may_repeat_freely(self):
        for _ in range(2):
            self.client.post(reverse("step:note_create", args=[self.student.pk]), {"comment": "A note."})
        self.assertEqual(ProgressEntry.objects.filter(student=self.student).count(), 2)

    def test_an_empty_note_is_rejected(self):
        self.client.post(reverse("step:note_create", args=[self.student.pk]), {"comment": "  "})
        self.assertEqual(ProgressEntry.objects.count(), 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_classes_views -v 2`
Expected: FAIL — `NoReverseMatch: 'student_detail' is not a registered namespace`

- [ ] **Step 3: Write the views**

Add to `step/classes_views.py`:

```python
@login_required
def student_detail(request, pk: int):
    educator = _educator(request)
    student = get_object_or_404(Student, pk=pk, teaching_class__educator=educator)

    context = {
        "nav": "classes",
        "student": student,
        "entries": student.progress_entries.select_related("grammar_point").all(),
    }
    context.update(_chrome(educator))
    return render(request, "step/classes/student_detail.html", context)


@login_required
def note_create(request, pk: int):
    educator = _educator(request)
    student = get_object_or_404(Student, pk=pk, teaching_class__educator=educator)

    if request.method == "POST":
        comment = (request.POST.get("comment") or "").strip()
        skill = request.POST.get("skill") or ""
        if not comment:
            messages.error(request, "Write what you want to note before saving.")
        else:
            ProgressEntry.objects.create(student=student, skill=skill, comment=comment)
            messages.success(request, "Note added.")
            return redirect("step:student_detail", pk=student.pk)

    context = {"nav": "classes", "student": student, "skills": constants.SKILL_CHOICES}
    context.update(_chrome(educator))
    return render(request, "step/classes/note_create.html", context)
```

Update `step/classes_urls.py`:

```python
from django.urls import path

from step import classes_views

urlpatterns = [
    path("", classes_views.class_list, name="class_list"),
    path("new/", classes_views.class_create, name="class_create"),
    path("<int:pk>/", classes_views.class_detail, name="class_detail"),
    path("<int:pk>/students/new/", classes_views.student_create, name="student_create"),
    path("students/<int:pk>/", classes_views.student_detail, name="student_detail"),
    path("students/<int:pk>/notes/new/", classes_views.note_create, name="note_create"),
]
```

- [ ] **Step 4: Write the templates**

```html
{# templates/step/classes/student_detail.html #}
{% extends "step/base.html" %}

{% block title %}{{ student.full_name }} — STEP{% endblock %}

{% block content %}
<nav class="crumbs" aria-label="Breadcrumb">
  <a href="{% url 'step:class_list' %}">My classes</a><span>/</span>
  <a href="{% url 'step:class_detail' student.teaching_class.pk %}">{{ student.teaching_class.display_name }}</a><span>/</span>{{ student.full_name }}
</nav>

<div class="head"><h1>{{ student.full_name }}</h1></div>

<div class="columns">
  <div>
    <section class="block" aria-labelledby="history-h">
      <h2 class="block__title" id="history-h">History</h2>
      <div class="block__body">
        {% if entries %}
        <ul class="filed">
          {% for entry in entries %}
          <li>
            <div class="filed__what">
              {% if entry.checkpoint %}{{ entry.get_checkpoint_display }}{% else %}Note{% endif %}
              {% if entry.skill %} &middot; {{ entry.get_skill_display }}{% endif %}
              {% if entry.score is not None %} &middot; <span class="num">{{ entry.score }}</span>{% endif %}
            </div>
            <div class="filed__when">{{ entry.created_at|date:"j F Y" }}</div>
            {% if entry.grammar_point %}<p style="margin:4px 0 0; font-size:13.5px">{{ entry.grammar_point.name }}</p>{% endif %}
            {% if entry.comment %}<p style="margin:4px 0 0; font-size:14px">{{ entry.comment }}</p>{% endif %}
          </li>
          {% endfor %}
        </ul>
        {% else %}
        <p>No entries yet.</p>
        {% endif %}
        <div class="actions" style="border-top:2px solid var(--ink); padding-top:22px; margin-top:22px">
          <a class="btn btn--primary" href="{% url 'step:note_create' student.pk %}">Add a note</a>
        </div>
      </div>
    </section>
  </div>
</div>
{% endblock %}
```

```html
{# templates/step/classes/note_create.html #}
{% extends "step/base.html" %}

{% block title %}Add a note — {{ student.full_name }} — STEP{% endblock %}

{% block content %}
<nav class="crumbs" aria-label="Breadcrumb">
  <a href="{% url 'step:class_list' %}">My classes</a><span>/</span>
  <a href="{% url 'step:student_detail' student.pk %}">{{ student.full_name }}</a><span>/</span>Add a note
</nav>

<div class="head"><h1>Add a note</h1></div>

<div class="columns">
  <div>
    <section class="block" aria-labelledby="note-h">
      <h2 class="block__title" id="note-h">What do you want to note</h2>
      <div class="block__body">
        <form method="post" novalidate>
          {% csrf_token %}
          <div class="field">
            <span class="field__label" id="skill-h">Skill (optional)</span>
            <div role="radiogroup" aria-labelledby="skill-h">
              {% for value, label in skills %}
              <label class="choice">
                <input type="radio" name="skill" value="{{ value }}">
                <span class="choice__text">{{ label }}</span>
              </label>
              {% endfor %}
            </div>
          </div>
          <div class="field">
            <label class="field__label" for="comment">Note</label>
            <textarea class="textarea" id="comment" name="comment"></textarea>
          </div>
          <div class="actions" style="border-top:2px solid var(--ink); padding-top:22px">
            <button class="btn btn--primary btn--lg" type="submit">Save the note</button>
            <a class="btn btn--quiet" href="{% url 'step:student_detail' student.pk %}">Back without saving</a>
          </div>
        </form>
      </div>
    </section>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Run tests**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_classes_views -v 2`
Expected: the validation and ownership assertions pass; full green still waits on Task 14.

- [ ] **Step 6: Commit**

```bash
git add step/classes_urls.py step/classes_views.py templates/step/classes/student_detail.html templates/step/classes/note_create.html step/tests/test_classes_views.py
git commit -m "Add the student-history and add-a-note screens"
```

---

### Task 13: The checkpoint bespoke obligation form — STOP, coordinate before landing

**This task edits `step/views.py` and `templates/step/obligation.html`, both owned by `test-generator-b0`.** Do not execute until a stopping point is agreed — post the diff below at the same checkpoint as Task 4 (they can be reviewed together, since both land in the same coordination window) and wait for confirmation.

**Files:**
- Modify: `step/views.py`, `templates/step/obligation.html`
- Test: `step/tests/test_views.py`

- [ ] **Step 1: Write the failing test**

Append to `step/tests/test_views.py`, after adding `ProgressEntry, Student, TeachingClass` to its existing `from step.models import ...` line at the top of the file:

```python
class CheckpointObligationTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.user = get_user_model().objects.create_user("maria", password="pw")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region, user=self.user)
        self.teaching_class = TeachingClass.objects.create(
            educator=self.educator, grade=9, slot=1, display_name="9A"
        )
        self.a = Student.objects.create(teaching_class=self.teaching_class, full_name="Aziz Karimov")
        self.b = Student.objects.create(teaching_class=self.teaching_class, full_name="Dilnoza Yusupova")

        self.boy_type = ObligationType.objects.create(
            name_template="Beginning-of-year diagnostic", category=constants.CATEGORY_ASSESSMENTS,
            cadence=constants.CADENCE_ANNUAL, evidence_spec=constants.EVIDENCE_NONE,
            form_slug=constants.FORM_SLUG_ASSESSMENT_CHECKPOINT,
        )
        self.obligation = Obligation.objects.create(
            type=self.boy_type, educator=self.educator, teaching_class=self.teaching_class,
            period_kind=constants.PERIOD_YEAR, period_start=date(2025, 9, 1), due_date=date(2025, 10, 1),
        )
        self.client.login(username="maria", password="pw")

    def test_the_page_lists_every_student_instead_of_an_uploader(self):
        response = self.client.get(reverse("step:obligation", args=[self.obligation.pk]))
        self.assertContains(response, "Aziz Karimov")
        self.assertContains(response, "Dilnoza Yusupova")
        self.assertNotContains(response, 'name="link"')

    def test_scoring_every_student_settles_the_obligation(self):
        self.client.post(
            reverse("step:obligation", args=[self.obligation.pk]),
            {
                f"score_{self.a.pk}": "80", f"skill_{self.a.pk}": constants.SKILL_READING,
                f"comment_{self.a.pk}": "",
                f"score_{self.b.pk}": "74", f"skill_{self.b.pk}": constants.SKILL_READING,
                f"comment_{self.b.pk}": "",
            },
        )
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_ACCEPTED)
        self.assertEqual(ProgressEntry.objects.filter(checkpoint=constants.CHECKPOINT_BOY).count(), 2)

    def test_scoring_only_some_students_leaves_it_not_started(self):
        self.client.post(
            reverse("step:obligation", args=[self.obligation.pk]),
            {f"score_{self.a.pk}": "80", f"skill_{self.a.pk}": constants.SKILL_READING, f"comment_{self.a.pk}": ""},
        )
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_NOT_STARTED)

    def test_a_blank_row_creates_no_entry(self):
        self.client.post(
            reverse("step:obligation", args=[self.obligation.pk]),
            {f"score_{self.a.pk}": "", f"skill_{self.a.pk}": "", f"comment_{self.a.pk}": ""},
        )
        self.assertEqual(ProgressEntry.objects.count(), 0)

    def test_resubmitting_updates_rather_than_duplicates(self):
        self.client.post(
            reverse("step:obligation", args=[self.obligation.pk]),
            {f"score_{self.a.pk}": "60", f"skill_{self.a.pk}": "", f"comment_{self.a.pk}": ""},
        )
        self.client.post(
            reverse("step:obligation", args=[self.obligation.pk]),
            {f"score_{self.a.pk}": "65", f"skill_{self.a.pk}": "", f"comment_{self.a.pk}": ""},
        )
        entry = ProgressEntry.objects.get(student=self.a, checkpoint=constants.CHECKPOINT_BOY)
        self.assertEqual(entry.score, 65)
        self.assertEqual(ProgressEntry.objects.filter(student=self.a).count(), 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_views.CheckpointObligationTests -v 2`
Expected: FAIL — the generic evidence uploader renders instead ("Aziz Karimov" is not on the page)

- [ ] **Step 3: Branch the view**

In `step/views.py`, extend the imports:

```python
from step import constants, presentation, urgency, workflow
from step.models import AcademicYear, Educator, Obligation, ProgressEntry, Submission
```

Replace the whole `obligation` function with this — the only changes from the current file are the `teaching_class` added to `select_related` and the four new lines branching to `_checkpoint_obligation`; everything from `latest = ...` onward is transcribed unchanged:

```python
@login_required
def obligation(request, pk: int):
    """One obligation, one screen, one job."""
    educator = _educator(request)
    today = date.today()

    obligation_obj = get_object_or_404(
        Obligation.objects.select_related("type", "educator", "teaching_class"),
        pk=pk,
        educator=educator,
    )

    if obligation_obj.type.form_slug == constants.FORM_SLUG_ASSESSMENT_CHECKPOINT:
        return _checkpoint_obligation(request, educator, obligation_obj, today)

    if request.method == "POST":
        return _handle_submit(request, educator, obligation_obj)

    latest = obligation_obj.latest_submission
    history = list(obligation_obj.submissions.select_related("reviewed_by").order_by("-revision"))

    context = {
        "nav": "work",
        "item": presentation.decorate(obligation_obj, today),
        "instruction": presentation.evidence_instruction(obligation_obj.type),
        "spec": obligation_obj.type.evidence_spec,
        "wants_link": obligation_obj.type.evidence_spec in {
            constants.EVIDENCE_LINK, constants.EVIDENCE_EITHER, constants.EVIDENCE_BOTH
        },
        "wants_file": obligation_obj.type.evidence_spec in {
            constants.EVIDENCE_FILE, constants.EVIDENCE_EITHER, constants.EVIDENCE_BOTH
        },
        "is_monthly_report": obligation_obj.type.category == constants.CATEGORY_MONTHLY_REPORTING,
        "rating_choices": constants.DIRECTOR_RATING_CHOICES,
        "outcome_choices": constants.OUTCOME_CHOICES,
        "latest": latest,
        "history": history,
        "can_submit": obligation_obj.status in {
            constants.STATUS_NOT_STARTED, constants.STATUS_RETURNED
        },
    }
    context.update(_chrome(educator))
    return render(request, "step/obligation.html", context)
```

Add two new functions (placed after `_handle_submit`):

```python
def _checkpoint_obligation(request, educator, obligation_obj, today):
    """The roster-scoring form for a checkpoint obligation.

    No evidence, no Submission row (classes/gradebook spec, "Auto-completion")
    — each POST here writes ProgressEntry rows directly and asks
    workflow.sync_checkpoint to settle the obligation once every student has
    one.
    """
    teaching_class = obligation_obj.teaching_class
    checkpoint = constants.NAME_TEMPLATE_TO_CHECKPOINT[obligation_obj.type.name_template]

    if request.method == "POST":
        for student in teaching_class.students.all():
            score_raw = (request.POST.get(f"score_{student.pk}") or "").strip()
            skill = request.POST.get(f"skill_{student.pk}") or ""
            comment = (request.POST.get(f"comment_{student.pk}") or "").strip()
            if not score_raw and not skill and not comment:
                continue
            ProgressEntry.objects.update_or_create(
                student=student, checkpoint=checkpoint,
                defaults={
                    "score": int(score_raw) if score_raw.isdigit() else None,
                    "skill": skill, "comment": comment,
                },
            )
        workflow.sync_checkpoint(teaching_class, checkpoint)
        obligation_obj.refresh_from_db()
        if obligation_obj.status == constants.STATUS_ACCEPTED:
            messages.success(request, "Thank you — every student is scored. Nothing further to do.")
        else:
            messages.success(request, "Saved. Come back to finish scoring the rest of the class.")
        return redirect("step:obligation", pk=obligation_obj.pk)

    existing = {
        entry.student_id: entry
        for entry in ProgressEntry.objects.filter(student__teaching_class=teaching_class, checkpoint=checkpoint)
    }
    rows = [
        {"student": student, "entry": existing.get(student.pk)}
        for student in teaching_class.students.all()
    ]

    context = {
        "nav": "work",
        "item": presentation.decorate(obligation_obj, today),
        "teaching_class": teaching_class,
        "rows": rows,
        "skill_choices": constants.SKILL_CHOICES,
        "can_submit": obligation_obj.status != constants.STATUS_ACCEPTED,
    }
    context.update(_chrome(educator))
    return render(request, "step/obligation.html", context)
```

- [ ] **Step 4: Branch the template**

In `templates/step/obligation.html`, the current file's "What to do" section runs from line 44 (`{% if can_submit %}`) to line 141 (its matching `{% endif %}`) — the whole generic link/file evidence form. Leave every line from 45 to 140 (the `<section class="block" aria-labelledby="do-h">...</section>` and its contents) completely untouched, character for character. Make exactly two insertions:

Immediately before line 44 (`{% if can_submit %}`), insert:

```
{% if teaching_class %}
{% if can_submit %}
<section class="block" aria-labelledby="do-h">
  <h2 class="block__title" id="do-h">Score {{ teaching_class.display_name }}</h2>
  <div class="block__body">
    <form method="post" novalidate>
      {% csrf_token %}
      {% for row in rows %}
      <div class="field" style="border-top:1px solid var(--rule-firm); padding-top:16px; margin-top:16px">
        <span class="field__label">{{ row.student.full_name }}</span>
        <div style="display:flex; gap:16px; flex-wrap:wrap; align-items:flex-start">
          <label>Score
            <input class="input" type="number" min="0" max="100" name="score_{{ row.student.pk }}"
                   value="{{ row.entry.score|default_if_none:'' }}" style="width:80px">
          </label>
          <label>Skill
            <select name="skill_{{ row.student.pk }}">
              <option value="">&mdash;</option>
              {% for value, label in skill_choices %}
              <option value="{{ value }}" {% if row.entry.skill == value %}selected{% endif %}>{{ label }}</option>
              {% endfor %}
            </select>
          </label>
        </div>
        <textarea class="textarea" name="comment_{{ row.student.pk }}" placeholder="Comment"
                  style="margin-top:8px; min-height:50px">{{ row.entry.comment|default:'' }}</textarea>
      </div>
      {% endfor %}
      <div class="actions" style="border-top:2px solid var(--ink); padding-top:22px; margin-top:22px">
        <button class="btn btn--primary btn--lg" type="submit">Save scores</button>
        <a class="btn btn--quiet" href="{% url 'step:dashboard' %}">Back without saving</a>
      </div>
    </form>
  </div>
</section>
{% endif %}
{% else %}
```

Immediately after line 141 (the `{% endif %}` that closes the original `{% if can_submit %}`), insert:

```
{% endif %}
```

The net effect: when `teaching_class` is in context (only true for checkpoint obligations, per the view in Step 3), the new roster-scoring form renders; otherwise the file behaves exactly as it does today, with the original generic form as the `{% else %}` branch.

The existing `{% if history %}` "What you have sent" section, further down the file, needs no change: no `Submission` row is ever created for a checkpoint obligation (Task 7's docstring), so `history` is always empty on this path and that block's own guard already hides it.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_views -v 2`
Expected: PASS — original tests plus 5 new ones

Then the whole suite: `.venv\Scripts\python.exe manage.py test -v 2`
Expected: all OK

- [ ] **Step 6: Commit**

```bash
git add step/views.py templates/step/obligation.html step/tests/test_views.py
git commit -m "Render the checkpoint roster-scoring form for assessment_checkpoint obligations"
```

---

### Task 14: Route the classes vertical and add the nav link — STOP, coordinate before landing

**This is the final shared-file touch: one `include()` line in `step/urls.py`, one rail link in `templates/step/base.html`.** Land it at the same checkpoint as Tasks 4 and 13 — once this is in, Tasks 10–12's screens go fully green.

**Files:**
- Modify: `step/urls.py`, `templates/step/base.html`
- Test: none new — this task turns the already-written, currently-red assertions in `step/tests/test_classes_views.py` green.

- [ ] **Step 1: Confirm the currently-red baseline**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_classes_views -v 2`
Expected: failures on every test that resolves a `step:class_*` / `step:student_*` / `step:note_create` URL (`NoReverseMatch`)

- [ ] **Step 2: Wire the include**

In `step/urls.py`:

```python
from django.urls import include, path

from step import views

app_name = "step"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("work/<int:pk>/", views.obligation, name="obligation"),
    path("submissions/", views.submissions, name="submissions"),
    path("feedback/", views.feedback, name="feedback"),
    path("classes/", include("step.classes_urls")),
]
```

- [ ] **Step 3: Add the nav link**

In `templates/step/base.html`, add a "Classes" link under the existing "Academic work" heading, after the category filter loop and before the "Evidence" heading:

```diff
     {% for key, label in categories %}
     <a class="rail__link" href="{% url 'step:dashboard' %}?category={{ key }}"
        {% if nav == 'work' and active_category == key %}aria-current="page"{% endif %}>{{ label }}</a>
     {% endfor %}

+    <a class="rail__link" href="{% url 'step:class_list' %}" {% if nav == 'classes' %}aria-current="page"{% endif %}>Classes</a>
+
     <div class="rail__heading">Evidence</div>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_classes_views -v 2`
Expected: PASS — every test from Tasks 10–12

Then the whole suite: `.venv\Scripts\python.exe manage.py test -v 2`
Expected: all OK, strictly greater than the 537 baseline.

- [ ] **Step 5: Commit**

```bash
git add step/urls.py templates/step/base.html
git commit -m "Route the classes/gradebook vertical and add its nav link"
```

---

## Sequencing summary

Run Phases 1–3 (Tasks 1–9) and the non-shared parts of Phase 4 (Tasks 10–12) unattended — nothing there touches a file another session owns, and Tasks 10–12's URL-resolution failures are the expected, self-documenting marker of what Task 14 still needs to unlock.

Before Tasks 4, 13, and 14: stop, and get an explicit go-ahead from `test-generator-b0` (relayed via `test-generator-17` if that is easier for the user). All three land in the same short window — Task 4's migration, Task 13's view/template branch, and Task 14's include/nav-link — since they are the complete set of edits to files `test-generator-b0` owns for this spec. Bundling the checkpoint into one review, rather than three separate interruptions, respects their time; splitting it into three would not make any one of them safer to skip review on.
