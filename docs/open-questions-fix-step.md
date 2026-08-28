# Open questions — fix step plan

Decisions for the user, compiled by the orchestrator (test-generator-2a) across the three
sessions building `fix step plan.md`. Each item: the question, what the code currently does,
what changes if the answer differs, and how expensive that change is.

---

## From the plan's own §10 ("Assumptions to confirm")

### 1. Is CPD Offline really one activity per teacher?

Plan assumed: the standing Friday slot, not several.

**Code today:** does not enforce this either way. `Activity` has no constraint limiting how many
CPD Offline activities one educator can hold, and the create screen has no cap check. Nothing is
hard-committed — if the real answer turns out to be "several", the code already supports it with
zero changes.

### 2. Are ECA groups really uncapped (1–6, usually 1–2)?

**Code today:** no cap exists anywhere. Same as above — nothing to change if the answer is
different; a cap would need to be *added*, not removed.

### 3. Does the ECA monthly plan really need no review?

Plan claimed this is reversible with a one-field change (`ObligationType.requires_review = True`).

**That claim does not hold as built.** `workflow.sync_activity_plan()` force-accepts the
obligation once all three fields are filled — it never reads `type.requires_review` at all (it
bypasses `submit()` entirely, the same way checkpoint auto-completion does). Flipping the flag on
the `ObligationType` row would currently do **nothing**. Turning review on for real means editing
`sync_activity_plan()` to check the flag and route to `submitted` instead of `accepted` — a small
but real code change, not a data change. Worth having the user confirm review is genuinely not
wanted, since the plan's own escape hatch doesn't work.

### 4. Are announcements really national (no regional/school scoping)?

**Code today:** `Announcement` has no scope field of any kind — every active educator sees every
published announcement, no exceptions possible. Matches the assumption. Adding scoping later
means a new field, a migration, and a filter change everywhere announcements are queried — not
cheap.

### 5. Are announcements really in-app only (no email/Telegram)?

**Code today:** no delivery mechanism exists — no email call, no Telegram integration, nothing
that pushes an announcement to anyone. Matches the assumption; the plan itself already flags this
as a separate piece of work if it turns out to be wrong, and the code confirms there is no partial
scaffolding to build on — it would start from zero.

---

## 2. New: what does the regional chart's "CPD Online responses" column count?

Surfaced while building Phase 4 (item 18, `analytics.activity_by_region()`). The column is named
"CPD Online responses" and reads from `AnnouncementResponse`.

- **Reading A (as currently, provisionally, built):** counts every response, attending or not —
  *engagement* with the announcement.
- **Reading B:** counts attendees only — *turnout*.

The orchestrator has provisionally ruled Reading A, since that's what the column's plain name
("responses") says. This is a one-line queryset change either way (add `.filter(attending=True)`
for Reading B), and 84 is marking the exact call site so it's easy to flip once the user decides.

---

## 3. Risk, not a decision: `fix step plan.md` is untracked in git

The document all three sessions are building against — which explicitly supersedes parts of an
already-committed spec (`docs/superpowers/specs/2026-08-26-step-platform-spine-design.md` §2,
§5.1, §5.9) — exists only as a loose file in the working tree (`git status` shows it as `??`).
One `git clean`, one careless `git checkout .`, and the contract all three sessions are working
from is gone with no history to recover it from.

The orchestrator is raising this with the user directly and will not commit it without being
asked — that decision (and where it should live, and under what name) is the user's, not any
session's to make unilaterally.
