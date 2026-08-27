# STEP Platform — Administration Dashboard Design

Written 2026-08-27. Owner: this session (`test-generator-2a`). Implements the S3 review UI and
the S4 analytics UI described in `2026-08-26-step-platform-spine-design.md` §6–§7.2, in the
visual language of `2026-08-27-step-ui-spec.md` ("Dossier & Stamp").

**File ownership** (agreed with `test-generator-16`, who owns the teacher-facing screens):

| Mine | Theirs — do not edit |
|---|---|
| `templates/step/admin/*.html` | `static/css/step.css` |
| `step/admin_views.py` (new) | `templates/step/base.html`, `_letterhead.html`, `_messages.html` |
| `step/tests/test_admin_views.py` | `templates/step/{dashboard,obligation,submissions,feedback}.html` |
| `templates/step/base_admin.html` (new, once they land the shared includes) | `step/views.py`, `step/presentation.py` |
| this spec file | `step/urls.py` (shared — I hand them my patterns) |

Read-only, do not rewrite: `step/analytics.py`, `step/workflow.py`, `step/roles.py` — all already
built and tested; this build is a presentation layer over them, no new business logic.

---

## 1. Scope

**In:**
- Admin dashboard home: action queue, headline compliance figure, the nine analytics widgets
  (collapsed detail), period selector.
- Review queue and a one-submission review screen: Accept, or Return for correction.
- Teacher directory: searchable/filterable list of all active educators, and a per-teacher file
  screen (their obligations and submission history).
- Access control: gate the whole admin area to the three staff roles (Admin, Programme Admin,
  System Admin) — confirmed with the user 2026-08-27, no per-screen role narrowing for this build.

**Out (deferred, confirmed with the user 2026-08-27):**
- MoPSE CSV/XLSX export (spec §6.2).
- Obligation type / roster import / role management screens (Programme Admin / System Admin
  administrative tools beyond viewing) — these stay in the raw Django admin for now.
- Region-scoped access (spec explicitly rejects this — all staff see all educators nationally).

---

## 2. Screens and URLs

All under `app_name = "step"`, new `step-admin`-prefixed names, added to `step/urls.py` by
`test-generator-16` from patterns I hand them:

| URL | View | Template | Job |
|---|---|---|---|
| `/step/admin/` | `dashboard` | `admin/dashboard.html` | Action queue → headline → 9 widgets |
| `/step/admin/review/` | `review_queue` | `admin/review_queue.html` | List submissions awaiting a decision |
| `/step/admin/review/<int:pk>/` | `review_detail` | `admin/review_detail.html` | One submission: Accept or Return |
| `/step/admin/teachers/` | `teacher_directory` | `admin/teacher_directory.html` | Search/filter all teachers |
| `/step/admin/teachers/<int:pk>/` | `teacher_detail` | `admin/teacher_detail.html` | One teacher's obligations/submissions |

The action queue's "N teachers have not submitted" link routes into `teacher_directory` with
`?status=outstanding&period=...` rather than a separate obligations list — one roster screen, not
two. The review queue stays separate: its rows are submissions, not teachers.

---

## 3. Access control

A `staff_required` decorator in `admin_views.py` (new, not shared with `step/views.py`):
requires login (reuses the project's existing `LOGIN_URL`), then `roles.is_staff_role(user)`,
else `HttpResponseForbidden` with plain-language copy — not a stack trace, not a silent redirect
loop. No new login flow is built; the project's existing login page is reused.

---

## 4. Dashboard home (`/step/admin/`)

Implements spec §7.2's inversion, unchanged in principle from the spine spec:

1. **Action queue.** Plain sentences, each a link into a real filtered list:
   *"X teachers have not submitted for [period]."* → teacher directory, filtered.
   *"Y submissions are waiting for your review."* → review queue.
   Counts come from `analytics.submission_status()` (`not_started` + `pending` reporting
   categories, §6.1) and `len(workflow.review_queue())`.
2. **Headline figure.** `analytics.submission_status()` rendered as a record-strip (reusing
   `.record`/`.record__cell` from `step.css`): Submitted / Pending / Not started / compliance %.
   This is also widget 2 of the nine — no duplicate figure.
3. **The remaining eight widgets, collapsed behind a "See the full breakdown" toggle**
   (progressive disclosure — spec §7.0.2):
   - Teachers by region — horizontal bar (`analytics.teachers_by_region`)
   - Performance by director rating — donut, **labelled "Self-reported"** (`rating_distribution`)
   - Outcome overview — donut, **labelled "Self-reported"** (`outcome_distribution`)
   - Submission trend — cumulative line across the period (`submission_trend`)
   - Submissions by status and region — stacked bar (`status_by_region`)
   - On-time / late — figures with percentages (`timeliness`)
   - Average submission time, and completeness rate — labelled **provisional** per spec §6.1
     open question 3 (`timeliness`, `completeness_rate`)
   - Period selector (month picker, defaults to the current month) — drives every widget above
     via a `period` query parameter.
4. Region-based charts cap at the top handful of rows with a "show all 14" expansion, rather than
   rendering all regions at once — "detail on demand" (spec §7.2.4).

**Colour rule (from `test-generator-16`, binding on this screen more than any other since it is
almost entirely charts):** colour sits on the *category*, never the *status*. `--stamp` and
`--seal` mean late/returned and accepted, exclusively — never used as a chart series colour. The
five category inks (`--ink-violet`, `--ink-teal`, `--ink-ochre`, `--ink-umber`, `--ink-plum`) are
the chart series palette.

**Chart primitives needed from `test-generator-16`** (none exist in `step.css` yet — to be
requested once this spec is approved): horizontal bar row, stacked bar, donut, trend line. The
horizontal bar row (teachers-by-region) is the widest widget and should be built first since it
sets proportions for the others.

---

## 5. Review queue and review screen

`GET /step/admin/review/` lists `workflow.review_queue()` (oldest first) using the `.register`/
`.entry` ruled-list classes already in `step.css` — reused as-is per `test-generator-16`.

`GET /step/admin/review/<pk>/` shows the submission: obligation, evidence items, and — for
Monthly Reporting types — the self-reported director rating/outcome, **labelled self-reported**
(spec §5.10, non-negotiable). One screen, one job, mirroring `step/views.py`'s `obligation` view.

`POST` with `action=accept` calls `workflow.accept(submission, reviewer=request.user)`.
`POST` with `action=return` calls `workflow.return_for_correction(submission, reviewer=...,
comment=...)` — the view surfaces `ValueError` (missing comment) as a plain-language form error,
not a 500. Both are existing, tested functions; this view adds no new transition logic.

Per the lesson `test-generator-16` already hit on the teacher side: if the queue is filtered
(by region or status, if that's added later), the heading and any headline counts on that screen
move with the filter. Not building filtering into the review queue for this pass, but noting the
constraint so it isn't retrofitted wrong later.

---

## 6. Teacher directory and teacher file

`GET /step/admin/teachers/` — search by name; filter by region, school, and status
(`?status=outstanding` for the action-queue link, meaning "has at least one obligation reporting
as pending or not-started this period"). Paginated (2,012 rows). No passport/PINFL in the list,
ever (spec §4.4) — mirrors the constraint already enforced and tested in `step/admin.py`'s
`EducatorAdmin`.

`GET /step/admin/teachers/<pk>/` — that teacher's obligations and submission history, built on
`presentation.decorate_all` so wording matches the teacher-facing screens exactly (no separate
vocabulary for the same status). This is the "file" the letterhead's `file_ref` already points at
(`presentation.file_reference`) — the screen title uses that reference.

---

## 7. Testing

`step/tests/test_admin_views.py`, following the pattern in `step/tests/test_views.py` and
`step/tests/test_workflow.py`:
- Access control: staff roles admitted, educator role and anonymous users rejected.
- Dashboard: correct figures for a seeded set of obligations/submissions across statuses and
  regions; self-reported widgets carry the label; period parameter changes every widget's figures
  together (not just one).
- Review: accept and return-for-correction both transition state via the existing `workflow`
  functions and reject an empty return comment with a plain-language error, not a 500.
- Directory: search and each filter narrow results correctly; passport/PINFL never appear in
  response content.
- No personal identifier reaches a URL or query string anywhere in this app (grep-style assertion,
  mirroring the existing admin test's intent).

Baseline to preserve: full suite green (528 passing per `test-generator-16`, plus whatever grows
it in the meantime) before and after this work.

---

## 8. Open items carried forward (not blocking this build)

- Data completeness rate definition is provisional pending client confirmation (spine spec §10.3).
- MoPSE export, obligation-type management, and roster-import UI are explicitly deferred per §1.
