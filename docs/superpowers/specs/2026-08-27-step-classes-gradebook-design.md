# STEP Classes & Gradebook — design

Status: approved by user, not yet planned or implemented.
Owner: this session. Coordinate with `test-generator-16` (owns
`step/views.py`, `step/urls.py`, `step/presentation.py`, `step/urgency.py`,
`templates/step/base.html`, `templates/step/{dashboard,obligation,submissions,feedback}.html`,
`static/css/step.css`) before editing any file on that list — see
"Sequencing" at the end.

## Problem

Nothing in the codebase lets a teacher record their own classes, students,
grades, comments, or progress notes. The "Assessments" entry in the sidebar
nav is a bare filter over an obligation category with no content behind it.
Separately, the `diagnostics` app already produces three annual English
assessments (beginning/mid/end of year), split into four "class packs" per
grade (Design Revision 2 §2.1), but has no concept of a teacher, a class
roster, or a student.

This spec adds the missing piece: a teacher-facing Classes and Gradebook
vertical, wired into the existing obligation engine as an
`assessments`-category vertical, per the pattern `ObligationType.form_slug`
was built for ("Only a vertical needing a bespoke form or bespoke content
requires programming, and it attaches through `form_slug`" —
`step/models/obligations.py`).

**Out of scope:** any admin/director view of this data. That belongs to the
admin/reporting dashboard `test-generator-2a` is building separately, and
will be a follow-up spec once this data model exists.

## Data model

New file `step/models/classes.py`.

```python
class TeachingClass(models.Model):
    educator = models.ForeignKey(Educator, on_delete=models.CASCADE, related_name="classes")
    grade = models.PositiveSmallIntegerField()       # 9, 10, or 11
    slot = models.PositiveSmallIntegerField()        # 1-4, matches diagnostics' class pack number
    display_name = models.CharField(max_length=64)   # what the teacher calls it, e.g. "9B"
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["grade", "slot"], name="one_teaching_class_per_grade_slot"),
        ]


class Student(models.Model):
    teaching_class = models.ForeignKey(TeachingClass, on_delete=models.CASCADE, related_name="students")
    full_name = models.CharField(max_length=200)


class ProgressEntry(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="progress_entries")
    checkpoint = models.CharField(max_length=8, choices=CHECKPOINT_CHOICES, blank=True)
    score = models.PositiveSmallIntegerField(null=True, blank=True)
    skill = models.CharField(max_length=16, choices=SKILL_CHOICES, blank=True)
    grammar_point = models.ForeignKey(
        "content.GrammarPoint", null=True, blank=True, on_delete=models.SET_NULL
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
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
```

`CHECKPOINT_CHOICES` (BOY / MOY / EOY) and `SKILL_CHOICES` (Reading /
Writing / Listening / Speaking) join the vocabulary in `step/constants.py`,
alongside the existing category/status/evidence enums — same rule as
everything else there: stored values only, no user-facing wording.

**Why `(grade, slot)` is globally unique, not scoped to the educator:**
diagnostics' four class packs per grade are a fact about the paper bank, not
about any one teacher's account (diagnostics has no login). In this
programme one international English teacher owns a given grade+slot in
practice, so a global unique constraint matches reality and gives
diagnostics a single, unambiguous name to display. If that assumption turns
out to be wrong (two teachers legitimately sharing a slot), the constraint
is the first thing to revisit — flagging it here rather than discovering it
silently.

**Why score+comment are one row, not two:** the structured checkpoint record
*is* the progress note for that checkpoint — a skill, an optional grammar
point pulled from that student's grade syllabus, and free text — with the
score alongside it, per the user's description of the feature. There is
exactly one such row per student per checkpoint.

## Obligation engine integration

`step/models/obligations.py`'s `Obligation` gets one new nullable field:

```python
teaching_class = models.ForeignKey(
    "step.TeachingClass", null=True, blank=True, on_delete=models.CASCADE, related_name="obligations"
)
```

and the existing unique constraint changes from
`(type, educator, period_start)` to `(type, educator, teaching_class, period_start)`.
Every other obligation type keeps `teaching_class=None`; only the three
checkpoint types use it. This is the one migration touching an
already-migrated shared table — flagged for explicit review before it lands
(see Sequencing).

Three `ObligationType` rows carry the vertical:

| name_template | category | cadence | evidence_spec | requires_review | form_slug |
|---|---|---|---|---|---|
| Beginning-of-year diagnostic | assessments | annual | none | False | `assessment_checkpoint` |
| Mid-year diagnostic | assessments | annual | none | False | `assessment_checkpoint` |
| End-of-year diagnostic | assessments | annual | none | False | `assessment_checkpoint` |

**Generation** (`step/generation.py`, new `generate_checkpoint_obligations(year)`):
for every `ObligationType` with `form_slug="assessment_checkpoint"`, create
one `Obligation` per `TeachingClass` (not per educator) for that academic
year, using the class's `educator` and the type's own due-date rule against
the year's bounds (exact BOY/MOY/EOY due-date placement is a planning-time
detail — `scheduling.due_date_for` already generalises this).

**Auto-completion** (`step/workflow.py`, new `sync_checkpoint(teaching_class, checkpoint)`):
called after a `ProgressEntry` with a non-blank `checkpoint` is saved. If
every student in the class now has a structured entry for that checkpoint,
the matching `Obligation` (looked up by `teaching_class` + the checkpoint's
type) is set to `accepted` directly — bypassing `workflow.submit()`, since
there is no evidence to check and nothing to review. No `Submission` row is
created for these obligations; the obligation page must not assume one
exists (see Screens).

## Diagnostics rename

`diagnostics` gains a read-only lookup: wherever it currently prints
"Class N" (derived positionally in `diagnostics/navigation.py`), it looks up
`TeachingClass.objects.filter(grade=N_grade, slot=N).first()` and shows
`display_name` if a row exists, else falls back to "Class N" unchanged.
Diagnostics does not gain login or editing — the name is set only from the
STEP side. This is a one-directional dependency (`diagnostics` reads
`step.TeachingClass`); acceptable since the platform vision already has
diagnostics merging into STEP as its Assessments vertical.

## Screens (GOV.UK one-thing-per-page, per existing STEP convention)

- **My classes** — list of the teacher's `TeachingClass` rows, with a
  "create a class" action.
- **Create a class** — one form: grade, slot, name.
- **One class** — its student roster, an "add a student" action, and the
  three checkpoints with their completion state.
- **Add a student** — one form: name.
- **A checkpoint** (the `assessment_checkpoint` bespoke obligation form) —
  every student in the class, each with score / skill / grammar point /
  comment. This is what `templates/step/obligation.html` must branch to
  render when `obligation.type.form_slug == "assessment_checkpoint"`,
  instead of the generic evidence uploader.
- **A student** — history of checkpoint entries plus freeform notes, with an
  "add a note" action (skill / grammar point / comment, no score, no
  checkpoint).

Nav: a new "Classes" item in `templates/step/base.html`'s rail, under
"Academic work" alongside the existing category filters.

## Sequencing

This spec is approved but unplanned. Before any implementation touches
files `test-generator-16` owns — `step/views.py`, `step/urls.py`,
`templates/step/base.html`, `templates/step/obligation.html`, and the
migration on `step/models/obligations.py` — check with that session or the
user for a stopping point. The new-file work (`step/models/classes.py`,
`step/generation.py` additions, `step/workflow.py` additions,
`step/constants.py` additions) has no such conflict and can proceed
independently.
