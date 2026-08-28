# STEP Platform — Spine Design (Slice 1)

Written 2026-08-26. This is the first document about STEP.

The `diagnostics` app's `HANDOFF.md` refers to a "much larger planned system ('Expert Council,'
a teacher hub) that doesn't exist yet." **That system is STEP.** This document is its first
design. Where `HANDOFF.md` speaks of an "Expert Council merge path," read STEP.

---

## 1. What STEP is

STEP is the obligations and evidence platform for **international educators placed in Uzbek
schools**. It tracks what each teacher owes, by when, whether it arrived, whether it was
acceptable, and rolls that up for programme administration and the Ministry of Preschool and
School Education (MoPSE).

Two client mockups define it and are the design reference:

- **Teacher view** — sidebar (`Monthly Reporting`, `CPD Online`, `CPD Offline`,
  `ECA Programme`, `Assessments`; `My Submissions`, `Feedback & Correction`; Drive library,
  calendar, notifications, help), an obligations queue with due dates and urgency badges,
  four stat tiles, a term schedule, and quick-access links.
- **Monthly Reports end-to-end flow** — a four-step process (teacher fills a 5-step form →
  director evaluates and **physically stamps** the paper → teacher photographs and uploads the
  stamped page → administration aggregates), plus a nine-widget analytics dashboard over
  ~2,012 teachers across 11 regions.

### 1.1 Two facts that shape everything

**STEP does not replace Google Forms, Drive and Sheets.** Those keep collecting. STEP is the
layer above them that knows who owes what, by when, and whether it landed. This is why STEP
does not need to build five form engines.

**STEP is the foreigners' platform.** Uzbek school staff — directors included — will not have
accounts and largely will not know it exists. The consequences are worked through in §5.10.

---

## 2. Decomposition

STEP is a platform, not a project. It breaks into these pieces:

### The spine

| | Piece | Description |
|---|---|---|
| **S0** | Identity and roster | Users, schools, regions, districts, roles; educator-to-school assignment |
| **S1** | Obligation engine | Types, term calendar, cadence, due rules, instance generation, status |
| **S2** | Evidence and submissions | Submission records; evidence as link or upload; swappable storage |
| **S3** | Review and feedback | Admin queue, accept/return, revisions, `Feedback & Correction` |
| **S4** | Admin analytics | Regional rollups, status, ratings, trend, timeliness, MoPSE export |

### The verticals

| | Piece | Description |
|---|---|---|
| **S5** | Assessments | Wires the existing `diagnostics` app in. Content already built. |
| **S6** | Monthly Reporting | The 5-step wizard, director evaluation capture, stamped-proof upload |
| **S7** | CPD Online / CPD Offline / ECA | **Configuration, not code**, if S1 is designed correctly |
| **S8** | Peripherals | Notifications, calendar view, resource index, global search, help |

S7 being pure configuration is the acceptance test for the S1 design. If adding CPD Offline
requires a code change, S1 is wrong.

**Superseded 2026-08-27** by `fix step plan.md` (repo root) — S7 failed its own acceptance test
above. CPD Offline needs a weekly cadence and a session/attendance concept the obligation engine
does not have, and cannot be configured into being; CPD Online needs an announcement concept that
does not exist either. `fix step plan.md` §2 replaces S7 with three peer concepts — Obligation
(owed), Activity → Session → Attendance (done, covering CPD Offline and ECA), and Announcement →
Response (broadcast, covering CPD Online) — rather than forcing all three verticals through the
shape below. Only Monthly Reporting and the mockup's `Update Class Data & Targets | Other` remain
pure `ObligationType` configuration; ECA keeps one monthly-plan `ObligationType` alongside its new
`Activity` shape. Kept here for history; `fix step plan.md` is authoritative for S7.

### Build order

1. **Slice 1 — the spine.** S0 + S1 + S2 + S3 + S4. This document.
2. **Slice 2 — Monthly Reporting.** S6. The client's headline vertical.
3. **Slice 3 — Assessments.** S5. Merging `diagnostics` in.
4. **Later.** S8, and any further verticals, which should be configuration.

**Revised 2026-08-27:** Assessments (slice 3) is brought forward ahead of Monthly
Reporting, at the user's explicit request — see §9, superseded by
`docs/superpowers/specs/2026-08-27-step-classes-gradebook-design.md`.

---

## 3. Slice 1 boundary

**In scope:**

- Geography fixture (regions and districts of Uzbekistan)
- Adaptive roster import from a client spreadsheet whose columns are not yet known
- Self-signup with configurable identity matching, and a pending queue for non-matches
- Roles: Educator, Admin, Programme Admin, System Admin
- Obligation types as data; term calendar; instance generation; due rules and overrides
- Generic obligations accepting link and/or file evidence
- Submissions with multiple evidence items and full revision history
- Review queue: accept, or return with a comment; `Feedback & Correction` for teachers
- The teacher dashboard as drawn in the mockup
- The administration analytics dashboard as drawn in the mockup
- Postgres, replacing SQLite

**Explicitly out of scope:**

- The 5-step Monthly Reporting wizard — slice 2
- Any wiring to `diagnostics` — slice 3
- Notifications and email of any kind
- Calendar view, resource library index, global search
- Any Google API integration (see §4.5)
- A generic drag-and-drop form builder (see §5.5)

---

## 4. S0 — Geography, roster and identity

### 4.1 Geography ships with the code

Uzbekistan's administrative divisions are seeded from a repository fixture, **not** read from
the client spreadsheet.

```
Region(name, name_uz, code, is_city)
District(region, name, name_uz, code)
```

All 14 top-level divisions are seeded (12 viloyats, the Republic of Karakalpakstan, and
Tashkent City), not only the 11 that appear in the mockup — the mockup shows 11 because that is
where teachers currently are, not because the others do not exist.

**Rationale.** Region is the axis every chart in the admin dashboard pivots on. If regions were
created from free text in a spreadsheet, "Tashkent", "Toshkent", "Tashkent city" and the
Cyrillic spelling would become four distinct regions and every rollup would be silently wrong.
Seeded geography makes that failure impossible.

### 4.2 The roster is imported adaptively

```
School(name, district, external_id)
Educator(user -> AUTH_USER_MODEL, school, email, passport_no, pinfl, source_fields: JSON)
RosterImport(file, imported_at, imported_by, row_count, header_row, mapping: JSON)
AliasMapping(kind, raw_value, resolved_to)
```

The client has a spreadsheet holding teachers, schools and registrations. **Its columns are
unknown at design time and may change between terms.** The importer is therefore built around
not knowing them. This follows the convention already established in `diagnostics`: the
workbook is a living source of truth, treated adaptively, enforcing minimum sufficiency rather
than an exact historical snapshot.

**Mapping is confirmed before anything is written.** The importer reads the header row,
proposes a mapping by fuzzy-matching column names (`Full Name` / `Teacher Name` / `Name` to
`full_name`; `Region` / `Viloyat` / `Province` to region), and presents that mapping for
confirmation. No row is committed until it is accepted. The accepted mapping is stored on the
`RosterImport` so a later import can reuse it.

**Two fields are required; everything else is optional.** One identity key (§4.3) and one
geographic anchor — region, district, or a school that resolves to one. Every unrecognised
column is preserved verbatim in `source_fields` rather than discarded.

**Geographic resolution learns.** Region and district strings are matched against the seeded
fixture. Anything that cannot be matched confidently lands in an unresolved queue for a human
to map once; the decision is written to `AliasMapping` and applied automatically thereafter.

**Re-import is idempotent.** Running an updated sheet matches existing records on the identity
key, updates in place, inserts new rows, and **flags** records that have disappeared from the
sheet rather than deleting them. People are never destroyed by an import.

**`source_fields` is staging, not a home.** Once the sheet's real contents are known, fields
that matter are promoted into real columns by migration. The JSON blob buys flexibility now
without permanently leaving the roster schemaless.

**School is optional.** An `Educator` may hang off a district alone if the sheet lacks usable
school names, and be attached to a school later.

### 4.3 Identity is configured, not hardcoded

Signup fields are **not yet decided**. Candidates are email plus passport number, or email plus
PINFL. The design must survive either answer.

`Educator` carries `email`, `passport_no` and `pinfl`, all nullable. An ordered setting —
`STEP_ROSTER_MATCH_KEYS`, for example `["pinfl", "passport_no", "email"]` — drives a **single
resolver used by both the importer and signup**. It tries each key in order; the first
confident match wins; conflicts and near-matches go to a manual review queue.

**Why an ordered fallback rather than one chosen key.** No single identifier is safe here.
PINFL is an Uzbek citizen identifier that foreign educators may not hold. Passport numbers
change on renewal. Email is stable but gets mistyped and shared. An ordered resolver with a
human queue for the residue degrades gracefully; a single hardcoded key does not.

The signup form renders whichever fields the configuration marks required, so when the client
decides, it is a settings change rather than a migration.

**Access flow.** A teacher signs up with the configured fields. If the resolver matches an
imported roster row, the account is linked to that `Educator` and admitted. If not, it lands in
a pending queue for an administrator. The spreadsheet remains the gatekeeper — no mass invite
email is sent, so there are no dead links and no 2,000-message spam problem.

### 4.4 Personal identifier handling

Passport numbers and PINFL are regulated personal identifiers. They must be:

- stored, but never rendered in list views, exports or search results;
- never placed in URLs or query strings;
- readable only by System Admins, with access logged.

This is cheap to build now and expensive to retrofit.

### 4.5 Evidence storage

Evidence files use a Django `FileField` against the configured default storage backend. Slice 1
uses local disk on the VPS. The client intends to move to their own server storage, and
possibly Drive, later — that is a storage-backend swap requiring **no model change**.

No Google API integration is built in slice 1. Teachers paste links or upload files directly.

---

## 5. S1 to S3 — The obligation engine

### 5.1 An obligation type is data, not code

```
AcademicYear(label, start, end)
Term(year, name, start, end)

ObligationType(category, name_template, cadence, due_rule, evidence_spec,
               scope_rule, requires_review, form_slug, is_active)

Obligation(type, educator, period_kind, period_start, due_date, status, opened_at)
Submission(obligation, submitted_by, submitted_at, note, status, revision)
Evidence(submission, kind: link|file, url, file, caption)
```

**On `period`.** An obligation's period is either a calendar month or a term, decided by the
type's `cadence`. It is stored as `period_kind` (`month` | `term` | `year` | `once`) plus
`period_start`, rather than a free-form label, so that "May 2026" and "Term 3" are both
sortable, groupable and unambiguous. The mockup's display strings ("Monthly Report - May 2025",
"ECA Programme Plan - Term 1") are rendered from `name_template` plus the period, not stored.

A Programme Admin creates an obligation type, chooses its cadence and what evidence it demands,
and a new vertical exists. This is what makes S7 — CPD Online, CPD Offline, ECA, and the
mockup's `Update Class Data & Targets | Other` — configuration rather than four separate
builds.

Only two things ever require code: a vertical with a bespoke multi-step form (Monthly
Reporting, slice 2) and one with bespoke content (Assessments, slice 3). Both attach by
`form_slug` referencing a coded form.

**Superseded 2026-08-27** by `fix step plan.md` §2-§5, for CPD Online, CPD Offline and ECA only —
those three turned out not to be `ObligationType` configuration after all. CPD Offline needs a
weekly cadence and a session log this shape has no room for; CPD Online is Ministry-run and merely
announced, with no obligation row at all; ECA is structurally a class with a roster, not a
per-term document. The obligation-type-is-data model above still stands for Monthly Reporting and
Assessments, and ECA keeps one monthly-plan `ObligationType` (`form_slug=eca_monthly_plan`)
alongside its new `Activity` → `Session` → `Attendance` shape. Kept here for history; `fix step
plan.md` is authoritative for the three verticals' shape.

### 5.2 Instances are materialised

A scheduled management command generates the next period's `Obligation` rows for every active
educator against every active type.

At roughly 2,012 educators and about 30 obligations a year, that is roughly 60,000 rows
annually, which is nothing. Materialising is preferred over computing on the fly because
submissions, timestamps, extensions and history all need something durable to attach to.
Computing saves storage that is not scarce and costs an audit trail that is.

### 5.3 Status is stored; urgency is derived

```
not_started --> submitted --> under_review --> accepted
                                  |
                                  +---------> returned --> (resubmit, revision + 1)
```

The mockup's `Overdue`, `Due Today` and `Due Soon` badges are **never stored**. They are a
function of `due_date`, `status` and the current time, computed at query time.

The same applies to the four stat tiles (`My Obligations`, `Due This Month`, `Completed`,
`Progress %`). No denormalised counters. Storing derived state means a nightly job must
maintain it, and the day that job fails the dashboard lies without anyone noticing.

### 5.4 Due dates come from a rule, with overrides

`due_rule` on the type expresses things like "day 27 of the month" or "five days before term
end". An individual `Obligation` may carry an explicit override for extensions. Overrides are
recorded and visible, never silent edits.

### 5.5 No generic form builder

Monthly Reporting's five-step wizard will be written as a real Django form in slice 2. A
configurable form designer is deliberately rejected: it is a substantial subsystem in its own
right, it reliably ends up meaningfully worse than a coded form, and Google Forms already
covers the long tail. Types needing structure reference a coded form by `form_slug`; every
other type takes a link, a file, or both.

### 5.6 Roles

| Role | Owes obligations | Capabilities |
|---|---|---|
| **Educator** | Yes | Own obligations, submissions, evidence, feedback |
| **Admin** | No | Review submissions, chase overdue, read all rollups |
| **Programme Admin** | No | Admin, plus define obligation types, set cadence and deadlines, grant extensions, run roster imports |
| **System Admin** | No | All of the above, plus user management, role assignment, personal identifier access, integrations |

Roles map onto Django Groups so permission checks stay conventional.

**Assignment scope is uniform.** Every active Educator owes every active obligation type.
Instance generation targets Educators only, so staff never accrue phantom obligations.
Per-educator exemption is the single escape hatch. `scope_rule` exists on `ObligationType` with
`all` as its only implementation, so a geographic or cohort filter can be added later in one
place.

**No administrative scoping.** All staff see all educators nationally. The dashboard is a single
national view.

### 5.7 Evidence is a list

One submission carries many evidence items, because the monthly report needs both form data and
the stamped photograph. `evidence_spec` on the type declares what is required and is validated
at submit time:

| `evidence_spec` | Meaning |
|---|---|
| `none` | Submitting requires no attachment |
| `link` | At least one link; files optional |
| `file` | At least one uploaded file; links optional |
| `either` | At least one evidence item, of any kind |
| `both` | At least one link **and** at least one file |

A `min_count` accompanies it, defaulting to 1.

### 5.8 Revisions, never overwrites

A returned submission that is resubmitted creates revision 2; revision 1 is retained in full.
This is the audit trail, and it is the data behind `Feedback & Correction`.

### 5.9 Review is optional per type

`requires_review` on the type. Monthly reports enter the queue. Something like `Update Class
Data & Targets` can auto-accept on submit. The states, queue and revision machinery exist
regardless, so switching review on for a type is a configuration change.

**Superseded 2026-08-27** by `fix step plan.md`, for CPD Online and CPD Offline only — neither
goes through `requires_review`/submission at all any more. CPD Online is an announcement RSVP
with no obligation row to review, and CPD Offline's session logs never enter the review queue
(`fix step plan.md` §2, "the review queue's load" — logging a session is a twenty-second act, not
a submission awaiting review). The pattern above still governs Monthly Reporting and the ECA
monthly plan, which auto-accepts exactly as `Update Class Data & Targets` does here, once all
three of its fields are filled. Kept here for history; `fix step plan.md` is authoritative for
CPD Online and CPD Offline.

### 5.10 The director is never a user, and the data says so

No Uzbek staff will hold accounts. The director evaluates on paper and applies a physical stamp.
Consequently the monthly report's director rating, director name, evaluation date and director
comments are **all teacher-transcribed**, and the photograph of the stamped page is the only
verification.

Slice 1 models this pattern generally: evaluation fields captured this way are marked
**self-reported** in the schema, and the analytics label them as such in the interface.

This is not pedantry. The mockup's "Performance Overview (By Director Rating)" donut is
self-reported data destined for a ministry. Presented unlabelled, it will be read as verified
assessment, and that is a credibility failure that is trivial to prevent now.

---

## 6. S4 — Analytics

The administration dashboard is nine derived widgets over `Obligation` and `Submission`. It
introduces **no new data model**.

1. Teachers by region — horizontal bar
2. Overall submission status — total, submitted, pending, not started, with percentages
3. Performance overview by director rating — donut, 5 / 4 / 3 / 1-2, **labelled self-reported**
4. Outcome overview — donut, "Satisfactory or Better" vs "Needs Improvement", **labelled self-reported**
5. Submission trend — cumulative percentage across the period
6. Submissions by status and region — stacked bar
7. On-time and late submission counts with percentages
8. Average submission time, and data completeness rate
9. Period selector driving all of the above

The two donuts chart two *different* self-reported signals: the five-star director rating
captured at wizard step 2, and the binary outcome radio at step 3. They are not derivable from
one another and both are stored.

**Computed live.** At this scale these are trivial aggregates given indexes on
`(educator, period)`, `(type, period, status)` and `submitted_at`. Precomputed snapshots are
added only if a query is measured to be slow. Caching before that point buys nothing and
introduces an invalidation bug.

### 6.1 Metric definitions

These are normative. Without them, two people compute different numbers.

Note that the dashboard's *Pending* and *Not started* buckets are **reporting categories derived
at query time**, and are not the same thing as the `not_started` value in the status enum of
§5.3. An obligation whose stored status is `not_started` reports as *Pending* before its due
date and as *Not started* after it. Keeping these names distinct in code is required.

- **On-time** — `submitted_at <= due_date`.
- **Late** — submitted, with `submitted_at > due_date`.
- **Pending** (reporting) — stored status `not_started`, `due_date` not yet passed.
- **Not started** (reporting) — stored status `not_started`, `due_date` passed.
- **Average submission time** — mean of `submitted_at - opened_at`, in days, over submitted
  obligations in the period.
- **Data completeness rate** — proportion of required evidence slots actually filled across
  submissions in the period. **This definition is provisional and requires client
  confirmation**, since the mockup does not define it.

### 6.2 MoPSE export

A CSV/XLSX export of the same aggregates. Not a live ministry integration; nothing in the
mockups implies one.

---

## 7. Design system and interaction model

### 7.0 The governing constraint: neither audience is comfortable with software

This is a hard requirement, not a preference. Teachers must be able to complete obligations with
zero complications, and administrators are people who are easily overwhelmed by dense screens.
Every layout decision in slice 1 is subordinate to that.

**The model followed is the GOV.UK Service Manual, principally "one thing per page."** It is
chosen deliberately over generic SaaS dashboard convention because it was researched against
precisely this population: people completing *compulsory administrative tasks* that they did not
choose, under deadline, with mixed digital confidence, often on a phone. That is exactly what a
monthly report is. Three of its rules bind here:

1. **One decision per screen.** Never present two unrelated questions at once. A long flow of
   simple screens consistently outperforms one dense screen, even though it looks slower.
2. **Progressive disclosure.** Show what is needed now. Everything else lives behind a link,
   never behind a modal stack.
3. **Plain language, no internal vocabulary.** The interface says "Your monthly report is due in
   3 days," not "Obligation instance status: pending." The domain model's vocabulary
   (`ObligationType`, `evidence_spec`, `revision`) is **never** shown to a user.

Supporting principles: progressive disclosure (Nielsen), and Hick's Law — every additional
choice on a screen costs decision time, so the default screen offers the fewest choices that
still allow the task.

### 7.1 For teachers: answer one question

The teacher's home must answer **"what do I need to do right now?"** before it shows anything
else. The mockup is already close — the obligations queue is central — and slice 1 adds one
thing above it: a single **next action** panel naming the one most urgent obligation, its
deadline in human terms ("due in 3 days", not a date to subtract), and one button.

Rules:

- Every obligation opens onto **one screen with one job**. Attach evidence, or answer, or
  confirm. Not all three at once.
- Status is written in words, never only in colour. `Overdue` reads as "Late — please submit
  as soon as you can", not a red pill alone. Colour is reinforcement, never the sole carrier
  of meaning; this is also the accessibility requirement.
- **Nothing is ever lost.** Partial work saves as a draft automatically. A teacher who closes
  the tab mid-task loses nothing.
- Errors say what to do next. "The file is too large — please upload something under 10 MB"
  rather than "Validation error."
- **Mobile is a first-class case.** The stamped report is photographed on a phone, so the
  upload path must work on a phone, not merely resize down to one.

### 7.2 For administrators: lead with the work, not the charts

This is the most substantive departure from the mockup, and it is deliberate.

The administration screen as drawn opens with nine analytics widgets. Nine widgets is what
overwhelms people. Analytics answer *what happened*; an administrator arriving at work needs
*what do I do*. So slice 1 inverts the page:

1. **An action queue first.** "136 teachers have not submitted. 12 submissions are waiting for
   your review." Each is a link into a filtered, workable list — not a number to admire.
2. **One headline figure second.** The single compliance number for the period.
3. **The analytics below that**, unchanged from the mockup, as the answer to "how are we doing"
   rather than the first thing in the eye.
4. **Detail on demand.** Regional breakdowns expand; they do not all render at once.

The nine widgets are still built and still present. They are ordered beneath the work.

### 7.3 Visual language

**The STEP mockups win.** Slice 1 is built to their visual language: light blue-and-white,
card-based layout, rounded corners, soft elevation, coloured icon chips.

This directly conflicts with the existing **"Examinations Office"** system in
`static/css/paper.css`, whose founding rules are "no cards, no corner radii, no shadows, no
gradients". That conflict is accepted and deferred:

- Slice 1 introduces a separate STEP stylesheet. `paper.css` is not modified.
- The `diagnostics`, `bank` and `assembly` screens keep `paper.css` until slice 3.
- **The print stylesheet (`paper-print.css`) is never restyled.** Printed exams should look
  like stationery; that is correct and unaffected.

**Implementation requirement:** the `frontend-design` skill must be used when the STEP interface
is built, to avoid generic AI-generated design patterns. Building to a card-based SaaS mockup is
exactly the situation that produces indistinguishable output if left unguided. This is recorded
here because brainstorming hands off only to planning, so the requirement must survive in
writing.

---

## 8. Infrastructure

The project currently runs Docker, gunicorn, WhiteNoise and Caddy against SQLite. That suits 48
papers and a handful of users. It does not suit about 2,012 educators submitting with file
uploads, concentrated into the final 48 hours of each month.

**Slice 1 moves to Postgres.** Media storage stays on local disk behind the configured storage
backend, ready to be swapped.

---

## 9. Merge path for `diagnostics` (slice 3, recorded now)

**Superseded 2026-08-27** by
`docs/superpowers/specs/2026-08-27-step-classes-gradebook-design.md`, at the user's request —
the two-per-term-obligation shape below turned out not to match what the user actually needed
(a per-class BOY/MOY/EOY gradebook with student-level grades, comments and progress notes, not
just scores-as-evidence). Kept here for history; the new spec is authoritative for the
Assessments vertical's shape and for the cross-import rule.

`diagnostics` was deliberately built decoupled for this moment: it uses
`settings.AUTH_USER_MODEL` rather than a concrete user, imports nothing from `content`, `bank`
or `assembly`, and puts teacher-to-grade resolution behind a swappable resolver.

At slice 3 (original plan, superseded):

- `TeacherGradeAssignment` is replaced by a resolver reading STEP's Educator-to-school-to-class
  assignment.
- Two obligation types are created — "Assessment Administration" and "Assessment Scoring and
  Submission", both per-term, matching the mockup.
- The administration obligation's detail view surfaces the teacher's class pack, using the
  existing `diagnostics/navigation.py` grade to class-pack to variants structure.
- The scoring obligation takes scores as evidence.
- `diagnostics` screens are rethemed to the STEP system.

Nothing in slice 1 may import from `diagnostics`, and nothing in `diagnostics` may import from
STEP's spine, until that slice. **This still holds direction-for-direction** — the new spec's
one permitted exception is `diagnostics` reading STEP's `TeachingClass` table read-only, recorded
explicitly there rather than as a silent violation of this rule.

---

## 10. Open questions for the client

These are genuinely unresolved and each blocks part of the build:

1. **What columns does the roster spreadsheet actually contain?** The importer is designed to
   tolerate any answer, but promoting `source_fields` into real columns waits on it.
2. **What does signup ask for** — email plus passport number, or email plus PINFL? A settings
   change, but the resolver order depends on it.
3. **How is "data completeness rate" defined?** §6.1 carries a provisional definition.
4. **Is there an existing account or registration source** beyond the sheet — a Google Form
   whose responses should seed the roster?
5. **Who staffs the review queue,** and what turnaround is expected? This determines whether
   `requires_review` is switched on at launch or shortly after.
6. **Academic year dates.** The mockup shows Term 1 September to November, Term 2 December to
   February, Term 3 March to May, but labels the schedule inconsistently. Confirm the real
   calendar before seeding.

---

## 11. Rejected alternatives

- **Building the Assessments vertical as slice 1.** Rejected: the content already exists and
  the spine is the actual blocker.
- **Analytics-first with thin capture.** Rejected: it reports over data STEP does not own, and
  gives teachers nothing.
- **Deep Google API integration.** Rejected for slice 1: OAuth, service accounts, quotas and
  sync failure become a support surface before there is anything to support. Links and uploads
  cover the requirement, and the client's stated direction is toward their own storage anyway.
- **A configurable form builder.** Rejected — see §5.5.
- **Region-scoped administrators.** Rejected per client: all staff see all educators.
- **Rendering STEP in the Examinations Office system.** Rejected per client: the mockups win.
- **Submit-and-track without a review loop.** Rejected per client: without accept/return,
  `Feedback & Correction` has nothing to show and "submitted" cannot mean "acceptable".
