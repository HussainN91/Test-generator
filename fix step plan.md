# Fix STEP Plan — Re-aligning the verticals with what actually happens

Written 2026-08-27, after the client walkthrough of Monthly Reporting, CPD Online,
CPD Offline and the ECA Programme.

This document **supersedes** the treatment of S7 in
`docs/superpowers/specs/2026-08-26-step-platform-spine-design.md` §2, §5.1 and §5.9.
Everything else in that spec stands. It follows the convention already used there in §9:
the superseded section is annotated in place and this document becomes authoritative for
the verticals, rather than the history being rewritten.

---

## 1. What was got wrong

The spine spec assumed **every vertical is paperwork**: a teacher owes a document, per month
or per term, an administrator reviews it. That produced `ObligationType` → `Obligation` →
`Submission` → `Evidence`, with `cadence ∈ {monthly, termly, annual, once}`.

Three of the four verticals do not work that way.

| Vertical | What actually happens | What was built | Why it fails |
|---|---|---|---|
| **Monthly Reporting** | Teacher fills the form, director stamps the paper, teacher photographs and uploads it | The five-step wizard, slice 2 | **Correct. Unchanged by this document.** |
| **CPD Online** | The **Ministry** runs it. A Programme Admin announces each session. The teacher answers *attending* or *not attending*. | `ObligationType("CPD Online - Classroom Management", cadence=termly, evidence=either)` in `seed_demo.py` | There is no announcement concept anywhere in STEP — notifications were cut from slice 1. And no fixed cadence can express "whenever the Ministry schedules one". |
| **CPD Offline** | The foreign teacher **delivers** training **to Uzbek teachers**, **every Friday**. | Nothing seeded. Would have been an obligation type. | No weekly cadence exists in `constants.py`; `scheduling.py` has no weekly arithmetic; and there is no way to record *a session delivered to an audience holding no accounts*. |
| **ECA Programme** | 1–6 groups per teacher (usually 1–2), same students each week, content freely agreed — drama, debate, IELTS. Monthly plan per group. Sessions logged with attendance. | `ObligationType("ECA Programme Plan - {period}", cadence=termly, evidence=link)` | ECA is structurally *a class with a roster*, closer to the existing `TeachingClass`/`Student` models than to a per-term document. Modelling it as one link discards the group, the schedule, the students and every session. |

The spine spec set its own acceptance test in §2:

> S7 being pure configuration is the acceptance test for the S1 design. If adding CPD
> Offline requires a code change, S1 is wrong.

**By that test, S1 was wrong.** CPD Offline needs a weekly cadence that does not exist and a
session/attendance concept that does not exist. It cannot be configured into being.

**The root cause, stated once:** the obligation engine models things that are *owed*. Two of
these verticals are things that are *done* — recurring delivery with participants — and one is
a thing that is *announced*. Forcing all three through one abstraction is what broke.

---

## 2. The corrected model — three peer concepts

| Concept | Meaning | Covers |
|---|---|---|
| **Obligation** | Something **owed**, by a date, with evidence, reviewable | Monthly Report, ECA monthly plan, assessment checkpoints |
| **Activity → Session → Attendance** | Something **done**, recurring, with a roster | ECA groups, Friday CPD Offline |
| **Announcement → Response** | Something **broadcast**, with an RSVP | CPD Online |

Each concept means exactly one thing.

Critically, **a session is not an obligation.** Logging a session is a twenty-second act, not a
submission awaiting review. At full scale — ~2,012 educators × ~7 sessions a week — treating
sessions as obligations would push roughly **500,000 rows a year through a review queue built
for about nine per teacher per year**. Under this model the review queue is untouched.

The **monthly plan obligation remains the reviewable artefact**, and it reads the session log:
*"You logged 4 of 4 Friday sessions this month."*

Rejected alternatives are recorded in §9.

---

## 3. Activities, Sessions and Attendance

### 3.1 Models

New file `step/models/activities.py`:

```python
Activity(educator, kind, title, school, schedule_rule, started_on, archived_on, created_at)
ActivityParticipant(activity, full_name, student→Student?, staff→SchoolStaff?)
Session(activity, scheduled_for, held_on, status, topic, notes, evidence_url, recorded_at)
SessionAttendance(session, participant)
```

`SchoolStaff(school, full_name, created_at)` goes in `step/models/roster.py`, beside `School`
and `Educator`, because it is roster data.

`kind` is `eca` or `cpd_offline`. **One model, not two**, because both are *a recurring thing
with a roster that meets and gets logged*. The differences — where the roster comes from, and
whether a monthly plan hangs off it — are fields, not separate shapes.

### 3.2 Participants carry their own name

`ActivityParticipant.full_name` is stored even when the participant came from a `Student` or a
`SchoolStaff` row. Two reasons:

1. The tick list renders from one field, so it is fast on a phone.
2. **Last March's register still reads correctly** after a student leaves the class or a name
   is corrected. A register that silently rewrites itself is not a register.

The two nullable links record *where the name came from* — pulled from an existing class, or
typed. That is exactly the ECA requirement: pull names from classes the teacher already has,
or leave the roster empty and type them.

### 3.3 `SchoolStaff` is scoped to the school, not the educator

The Friday CPD audience is the Uzbek teachers at the placement school. They hold no accounts
(spine spec §5.10) and appear nowhere in the roster import. The teacher types them once; STEP
remembers them.

Scoping to **school** rather than to educator means two foreign teachers placed in one school
tick the same list instead of each maintaining a private duplicate of the same twelve names.

### 3.4 Sessions are generated ahead, then filled in

`schedule_rule` is JSON, following the convention `due_rule` already uses in
`step/scheduling.py`:

```json
{"weekdays": [4]}
{"weekdays": [1, 3]}
```

The first is every Friday — the CPD Offline slot. The second is Tuesdays and Thursdays — an ECA
group meeting twice a week.

STEP materialises each upcoming session as `status=expected`. The teacher turns it into `held`
or `cancelled`, and may add an off-schedule session at any time.

This is what makes the rest work:

- The teacher's home can say **"2 sessions to log"** — a countable action, not a nag.
- The monthly plan obligation can state **"4 of 4 Friday sessions logged"** without inference.
- **Gaps are visible.** A session neither logged nor cancelled shows as a gap instead of
  vanishing.

Session status values: `expected`, `held`, `cancelled`.

### 3.5 Logging a session is one screen

Per spine spec §7.0 — one thing per page, and neither audience is comfortable with software.

- Date and topic prefilled from the schedule.
- The roster as a tick list, **everyone pre-ticked**.
- Notes optional. Drive link optional.

The common case — everyone showed up — is **confirm**, not data entry. That is the difference
between twenty seconds and three minutes, seven times a week, indefinitely. It is the single
decision that determines whether this feature is used or resented.

### 3.6 Attendance stores presence only

A `SessionAttendance` row exists only for a participant who **was present**. No absentee rows.

Volume at full scale: ~500,000 sessions and ~7.6M attendance rows a year. That is a narrow
two-column table and entirely comfortable on Postgres with indexes on `session` and
`participant`. It is stated here so nobody discovers it in production.

### 3.7 Evidence photos live in the teacher's own Drive

Session evidence is a **link** (`Session.evidence_url`), never a file in STEP storage. It is
**optional**.

The reason is deliberate and must not be optimised away: the teacher keeps their own proof of
work done, so it cannot be lost or controlled by the programme. This protects the teacher's
rights in any dispute about whether a session happened.

Two consequences that must be built, not assumed:

1. **A private Drive link is unreadable to a reviewer unless shared.** At the moment the
   teacher pastes it, STEP says so plainly: *"Make sure this link can be opened by anyone with
   the link, or your reviewer will see nothing."*
2. **Show a *link not reachable* state** rather than silently accepting a dead link. Optional
   evidence that is silently broken is worse than no evidence at all.

### 3.8 Creating a group is always open; archiving never deletes

- A teacher may create an ECA group at **any time**. It is never gated to a term boundary or a
  setup window.
- Therefore **obligations generate on create**, not only on the nightly batch. A teacher who
  starts a debate club on the 12th gets that month's plan obligation immediately.
- **Late-month grace:** a group created within the last 7 days of a month **skips** that
  month's plan and starts the following month, rather than being born already overdue.
- `archived_on` stops future sessions and future plan obligations. Past plans, sessions and
  attendance survive untouched — the same principle as the roster importer flagging rather
  than deleting people.

---

## 4. The ECA monthly plan

One plan **per group, per month**. Mandatory. Three typed fields — **no file upload, no
optional attachment**:

| Field | Shown to the teacher as | Holds |
|---|---|---|
| `overview` | **Overview** | What this group is doing this month |
| `session_outline` | **Session outline** | The week-by-week breakdown |
| `intended_outcomes` | **Intended outcomes** | What students should be able to do by month's end |

Field names avoid internal vocabulary per spine spec §7.0. "Scheme of work" was rejected as
educational jargon; "Session outline" says the same thing in plain words.

### 4.1 How it attaches to the obligation engine

Exactly as the assessment checkpoints already do — this is the established pattern in the
codebase, not a new one:

- `ObligationType(category=eca, cadence=monthly, evidence_spec=none, form_slug="eca_monthly_plan")`
- The plan is stored in its own model, not on `Submission`:

```python
ActivityPlan(activity, period, overview, session_outline, intended_outcomes,
             created_at, updated_at)
```

- `step/workflow.py` auto-completes the obligation once all three fields are filled, mirroring
  how checkpoint obligations complete when every student has a structured entry. Nothing waits
  for a reviewer.

`ActivityPlan` is a separate model rather than columns on `Submission` because the plan belongs
to *the group and the month*. `Submission` already carries five monthly-report-specific columns;
adding three ECA-specific ones would make it the union of every vertical.

### 4.2 `Obligation` needs an `activity` link

`Obligation` already carries a nullable `teaching_class` for per-class checkpoints, with split
unique constraints — and a comment explaining exactly why they are split: SQL treats NULL as
distinct from NULL, so one combined constraint would silently drop the guarantee for ordinary
obligations.

An ECA plan obligation is **per activity**, so add a nullable `activity` FK and a **third**
unique constraint on `(type, educator, activity, period_start)` where `activity` is not null.
The existing two constraints gain `activity__isnull=True` in their conditions.

Three constraint pairs is slightly more than ideal. It is chosen over a generic content-type
subject because it stays explicit, matches the style already in the file, and keeps every
guarantee readable in the model.

---

## 5. CPD Online — Announcements and RSVP

### 5.1 Models

New file `step/models/announcements.py`:

```python
Announcement(created_by, title, body, published_at, respond_by,
             requires_response, is_active)
AnnouncementResponse(announcement, educator, attending, responded_at)
```

A unique constraint on `(announcement, educator)` — one answer per teacher, changeable until
`respond_by`.

### 5.2 Access is the point

**Only the Programme Admin role may publish an announcement.** This is an access rule, not a
routing convention: it exists to stop several administrators broadcasting contradictory
messages to roughly 2,000 teachers.

The role already exists in the spine spec §5.6 and maps to a Django Group, so this is a
permission on a new capability rather than a new role.

**Up to five people hold Programme Admin.** This is recorded as operational policy and is
**not** enforced as a hard cap in code — an arbitrary limit that blocks a legitimate sixth
appointment at the wrong moment is worse than the problem it prevents. The role-management
screen displays the current holder count so the policy is visible where it is administered.

### 5.3 The teacher's side

A published announcement appears on the teacher's home. If `requires_response` is set, the
teacher answers **I will attend** / **I will not attend**, then submits. That is the whole
interaction. No certificate, no file, no obligation row.

An announcement with `requires_response=False` is pure news.

### 5.4 The administrator's side

Per the client: *"x teachers coming, x teachers not coming."* Two figures, plus the count who
have **not answered** — which is the number an administrator actually needs to chase, and is
not derivable from the other two without knowing the eligible population.

---

## 6. Cross-cutting regional activity

The client asked for a per-region activity graph **for all activities, not just CPD Online**.

`step/analytics.py` currently has `status_by_region()`, which covers obligations only. Add:

```python
def activity_by_region(period_start: date) -> list[dict]
```

One row per region that has educators, with counts spanning **all four verticals**:

| Column | Source |
|---|---|
| Monthly reports submitted | `Obligation` + `Submission` |
| CPD Online responses | `AnnouncementResponse` |
| CPD Offline sessions held | `Session` where `activity.kind = cpd_offline`, `status = held` |
| ECA sessions held | `Session` where `activity.kind = eca`, `status = held` |

Rendered as one grouped bar chart, region on one axis. Region is reached through
`Educator.region`, which is a real FK to seeded geography — the reason spine spec §4.1 refused
to create regions from spreadsheet free text.

Indexes required: `Session(activity, status, held_on)` and
`AnnouncementResponse(announcement, educator)`.

Computed live, consistent with spine spec §6 — these are trivial aggregates at this scale, and
a precomputed snapshot buys nothing until a query is measured to be slow.

---

## 7. Implementation phases

### Phase 1 — Models and migrations

1. `step/constants.py` — add `ACTIVITY_KIND_CHOICES` (`eca`, `cpd_offline`),
   `SESSION_STATUS_CHOICES` (`expected`, `held`, `cancelled`), `FORM_SLUG_ECA_MONTHLY_PLAN`.
   **Do not add a weekly cadence** — sessions are not obligations, so `ObligationType` needs no
   new cadence.
2. New `step/models/activities.py` — `Activity`, `ActivityParticipant`, `Session`,
   `SessionAttendance`, `ActivityPlan`.
3. `step/models/roster.py` — add `SchoolStaff`.
4. `step/models/obligations.py` — add nullable `activity` FK; add the third unique constraint;
   add `activity__isnull=True` to the two existing constraint conditions.
5. `step/models/__init__.py` — export the new models.
6. Migration. **Verify the constraint change migrates cleanly against existing data** — the
   two existing constraints are being narrowed, not replaced.

### Phase 2 — Scheduling and generation

7. `step/scheduling.py` — add `session_dates(schedule_rule, start, finish)` returning the dates
   a weekly rule produces in a window. Pure function, no models, consistent with the rest of
   the module. Tests for month boundaries and multi-weekday rules.
8. `step/generation.py` — add:
   - `generate_sessions(activity, through)` — materialise `expected` sessions, idempotent on
     `(activity, scheduled_for)`.
   - `generate_activity_plan_obligations(month_start)` — one per active, unarchived ECA
     `Activity`, mirroring `generate_checkpoint_obligations`'s per-class shape.
   - the late-month grace rule from §3.8.
9. Activity creation immediately generates its sessions and the current month's plan
   obligation. Not deferred to the nightly batch.
10. `step/management/commands/generate_obligations.py` — add a `--sessions` flag alongside the
    existing `--checkpoints`.

### Phase 3 — Teacher screens

Built with the `frontend-design` skill, per spine spec §7.3. GOV.UK one-thing-per-page
throughout.

11. **Set up an activity** — name it, choose what it is, set the weekly schedule, build the
    roster. For ECA: *pull from one of my classes* or *type names*. For CPD Offline: type
    names, saved to `SchoolStaff` and offered next time.
12. **Log a session** — §3.5. One screen. Everyone pre-ticked. Drive link optional, with the
    §3.7 sharing warning inline at the point of pasting.
13. **The ECA monthly plan** — three fields, one screen, mandatory, autosaved as a draft per
    spine spec §7.1 ("nothing is ever lost").
14. **Announcements on the teacher's home** — read, and RSVP where required.
15. `step/urls.py` — add `activities/` following the existing `classes/` include pattern; new
    `step/activities_urls.py` and `step/activities_views.py`, matching the
    `classes_urls.py` / `classes_views.py` convention already in the app.

### Phase 4 — Administration

16. **Announcement composer** — gated to the Programme Admin group. Title, body, optional
    `respond_by`, `requires_response` toggle.
17. **RSVP view** — coming / not coming / not yet answered, per announcement.
18. `step/analytics.py` — `activity_by_region()` per §6, plus a sessions-held figure for the
    period.
19. Add the regional activity chart to the admin dashboard, **below the action queue**, per
    spine spec §7.2 — lead with the work, not the charts.

### Phase 5 — Seed data and documentation

20. `step/management/commands/seed_demo.py` — **remove** `"CPD Online - Classroom Management"`
    and `"ECA Programme Plan - {period}"` from the catalogue, and delete them on re-run, using
    the same explicit-deletion pattern the command already uses for the two superseded
    assessment types. Add the `eca_monthly_plan` type. Seed one demo ECA group with students, a
    CPD Offline activity with `SchoolStaff`, a few held sessions, and one announcement with
    responses.
21. Annotate `docs/superpowers/specs/2026-08-26-step-platform-spine-design.md` §2, §5.1 and §5.9
    as superseded by this document — in place, following the §9 convention.

---

## 8. What is explicitly not changing

- **Monthly Reporting.** The five-step wizard, the physical director stamp, the photographed
  page, and the self-reported labelling of §5.10 are all correct. Untouched.
- **Assessments / classes / gradebook.** `TeachingClass`, `Student`, `ProgressEntry` and the
  BOY/MOY/EOY checkpoints stand. ECA *reads* class rosters to copy names; it does not alter
  them.
- **The obligation engine's core.** `Obligation`, `Submission`, `Evidence`, `workflow.py`,
  revisions, the review queue and `Feedback & Correction` are unchanged in shape. One nullable
  FK is added.
- **Roster import, identity resolution, geography.** Untouched.
- **`paper.css`, `paper-print.css` and the `diagnostics` screens.** Untouched, per spine spec
  §7.3.
- **The review queue's load.** Sessions never enter it. This is the point of §2.

---

## 9. Rejected alternatives

- **Extend the obligation engine — add a weekly cadence and make each session an obligation
  with attendance as evidence.** Rejected: ~500,000 obligation rows a year through a review
  queue built for ~9 per teacher, and it stretches "obligation" until the word means nothing.
  A Friday session is not *owed by a deadline*; it either happened or it did not.
- **Activity-first — everything is an activity with a schedule, obligations become derived
  views over gaps.** Rejected: the Monthly Report — a form, a physical stamp, a photographed
  page — is not an activity in any useful sense, and this would discard a working obligation
  engine, generation, workflow and analytics to find that out.
- **A `Session` model per vertical (`ECASession`, `CPDSession`).** Rejected: identical shape,
  duplicated logging screen, duplicated analytics. `kind` on one model costs one column.
- **Storing absentees as attendance rows with a false flag.** Rejected: doubles a 7.6M-row
  table annually to record the absence of information already implied.
- **Uploading session photos into STEP storage.** Rejected per client: the teacher keeps their
  own evidence in their own Drive, which is a rights question, not a storage question.
- **Hard-capping Programme Admin at five holders.** Rejected: policy, not a constraint.
  See §5.2.
- **A file upload or optional attachment on the ECA monthly plan.** Rejected per client: three
  typed fields, nothing else.

---

## 10. Assumptions to confirm

1. **CPD Offline is one activity per teacher** — the standing Friday slot — rather than several.
2. **ECA groups are not capped.** 1–6 is the expectation, usually 1–2; no number is enforced.
3. **The ECA monthly plan requires no review** — it auto-accepts once the three fields are
   filled, like the assessment checkpoints. If the programme wants plans read and returned,
   `requires_review=True` is a one-field change, but the review queue's load should be
   reconsidered first.
4. **Announcements are national.** Every active educator sees every published announcement.
   Consistent with spine spec §5.6, "no administrative scoping".
5. **Announcements are in-app only.** No email or Telegram delivery, matching slice 1's
   exclusion of notifications. If the Ministry expects teachers to be *reached* rather than to
   *find* the announcement on login, that is a separate piece of work.
