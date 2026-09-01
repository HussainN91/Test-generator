# English Test Generator

Generates English tests for grades 9–11 from the Cambridge "Prepare" syllabus,
as tagged non-overlapping variants (Test A, Test B, …) with matching answer keys.

Built to the design in [test-generator-spec.md](test-generator-spec.md). The two
priorities from that spec drive everything: **varied question types** that
genuinely test knowledge, and **tick-based marking** — every item resolves to one
fixed answer.

---

## Current state

Everything below is working and covered by tests (`python manage.py test` → 64 tests).

| Layer | Status |
|---|---|
| Content layer (§3.1) | ✅ 60 units, 1,110 vocabulary entries, 60 grammar points, 283 sample sentences imported from the three guides |
| Item bank (§3.4–3.5) | ✅ 736 approved items, all passing validation |
| Validation layer (§3.3) | ✅ structural checks + spaCy; gap-uniqueness implemented |
| Assembly & tracking (§3.4) | ✅ instant sampling, non-overlap within a batch, traceable variants |
| Output (§3.6) | ✅ printable HTML + .docx, answer keys alongside |
| Multi-user (§6) | ✅ Django auth, admin review queue, no LLM at runtime |
| Claude pipeline (§3.2) | ✅ written and wired; **not yet run** — needs an API key |

**The one gap:** the bank currently holds matching, multiple-choice and
word-formation items only. Gap-fill, key word transformation and error
correction need the Claude pipeline, which needs an API key. See
[Filling the bank properly](#filling-the-bank-properly).

---

## Run it

```bash
.venv/Scripts/python.exe manage.py runserver
```

Then open http://localhost:8000 and sign in.

Two accounts exist. **Change both passwords before this goes anywhere near a VPS.**

| User | Password | Role |
|---|---|---|
| `admin` | `changeme-admin-2026` | Superuser — review queue, all admin |
| `teacher` | `changeme-teacher-2026` | Teacher — build and export tests |

```bash
.venv/Scripts/python.exe manage.py changepassword admin
```

### What you can do right now

1. **Test builder** (`/`) — pick a grade, tick units, set question count and how
   many variants. Units with an empty bank are greyed out with their item count
   shown, so you never select one that cannot fill a test.
2. **Preview** — every variant with its answer key, before you print anything.
   Shortfalls are reported explicitly ("asked for 2, bank has 0") rather than
   silently producing a shorter test.
3. **Export** — printable HTML (tests, and answer keys separately) or a `.docx`
   with all variants followed by all keys.
4. **Bank coverage** (`/coverage/`) — the grade × unit grid from §7.1.
5. **Admin** (`/admin/`) — the item review queue. It opens filtered to items
   needing a decision, with approve / reject / flag as bulk actions.

---

## How the pieces fit

```
guides (.txt)  ──import_guide──▶  content layer      (Grade → Unit → Vocabulary + GrammarPoint)
                                        │
                    ┌───────────────────┴───────────────────┐
                    ▼                                       ▼
              seed_bank                            generate_items      ← needs API key
        (deterministic, no LLM)                 (Claude, 2 passes)
                    │                                       │
                    └───────────────┬───────────────────────┘
                                    ▼
                            validate_items          (structural + spaCy)
                                    ▼
                          admin review queue        (human approval)
                                    ▼
                             ITEM BANK  ──export_bank──▶ JSON ──import_bank──▶ VPS
                                    │
                                    ▼
                          assembly (pure SQL sampling)  →  Test A / B / C…
```

Everything left of the item bank is **offline**. The deployed app only reads the
bank — it holds no API key and has no runtime LLM dependency (§6).

---

## Commands

### Content

```bash
python manage.py import_guide                      # all three guides
python manage.py import_guide --grade 9 --dry-run  # parse and report, write nothing
```

Idempotent — fix a `.txt` and re-import. The parser handles all three guide
formats (they differ substantially); see `content/parsing/guide_parser.py`.

### Filling the bank — without an API key

```bash
python manage.py seed_bank                # every unit
python manage.py seed_bank --grade 10 --reset
```

Derives items from data already in the database, deterministically. It covers
three types:

- **matching** — vocabulary ↔ the guide's own definitions
- **multiple choice** — a definition cue, four same-part-of-speech options, and
  an *odd-one-out* variant built from the units' semantic categories
- **word formation** — taught prefixes and word families

It refuses to write an item it cannot prove has a single answer. Concretely: a
distractor whose definition names the target word (or overlaps it heavily) is
dropped, so *attractive* and *pretty* never appear in the same option set; a
word family yielding two nouns from one root is dropped entirely; and a
coincidental prefix match like *take* → *mistake* is rejected because the part
of speech changes and the definition describes no negation.

### Filling the bank properly — with an API key

```bash
export ANTHROPIC_API_KEY=...     # or: ant auth login
python manage.py generate_items --grade 10 --unit 3 --type gap_fill --count 8
python manage.py generate_items --grade 10 --unit 3 --type gap_fill --dry-run
```

Two passes (§3.2–3.3): generation under a JSON schema via Structured Outputs, then
a separate review pass judging naturalness and answer uniqueness. Items land as
`draft` (or `flagged` with the reason, if review objected) — invisible to
teachers until approved.

Start with one unit and `--dry-run` to see what the prompts produce before
spending on a full grade.

### Validation

```bash
python manage.py validate_items --status draft          # report only
python manage.py validate_items --status draft --apply  # write results back
python manage.py validate_items --status approved       # audit the live bank
```

Never writes without `--apply`. Checks: exactly one blank, the answer not
visible in its own prompt, the target word actually in the unit's vocabulary,
part of speech (via spaCy), duplicate options/definitions, and the gap-fill
uniqueness check — every other word in the unit is substituted into the blank
and the item is rejected if one fits the slot as well as the target.

Without spaCy installed the structural checks still run and the parser-based
ones report as *skipped* rather than silently passing.

### Moving a bank to the VPS

```bash
# on the machine with the API key
python manage.py export_bank --out bank-export.json

# on the VPS
python manage.py import_guide
python manage.py import_bank --in bank-export.json
```

Items are keyed by (grade, unit number) and deduplicated by content hash, so
re-importing is a no-op and a rebuilt production database still matches.

---

## Install

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py import_guide
.venv/Scripts/python.exe manage.py seed_bank
.venv/Scripts/python.exe manage.py createsuperuser
```

`requirements.txt` is the **production** set: Django plus python-docx. That is
what belongs on the VPS.

`requirements-pipeline.txt` adds `anthropic` and `spacy` for offline generation
and validation. Install it only where you generate.

### A note on the disk-space constraint

The spec set a budget of "well under ~200MB". The production set meets that
easily (~70MB with Django and python-docx). **spaCy does not** — with its
dependencies (numpy, thinc, blis) and the small English model it takes this
project's venv to ~314MB. Options, if that matters:

- keep it, since it only needs to exist where you generate, not on the VPS
  (this is what the split requirements files are for); or
- drop spaCy: the validation layer degrades cleanly and the Claude review pass
  still covers naturalness and uniqueness semantically.

No local LLM is used anywhere, which was the constraint's actual purpose.

---

## Deployment notes

Set these before running with `TESTGEN_DEBUG=0`:

| Variable | Purpose |
|---|---|
| `TESTGEN_DOMAIN` | the public hostname; Caddy uses it as the site address, so TLS is issued for it |
| `TESTGEN_SECRET_KEY` | required — startup fails without it when DEBUG is off |
| `TESTGEN_DEBUG` | `0` in production |
| `TESTGEN_ALLOWED_HOSTS` | comma-separated hostnames |
| `TESTGEN_CSRF_TRUSTED_ORIGINS` | comma-separated origins, if behind a proxy |
| `TESTGEN_DB_PATH` | SQLite location; swap `DATABASES` for Postgres when concurrency demands it |
| `TESTGEN_SSL` | `1` once HTTPS is actually serving — enables SSL redirect, HSTS, and proxy scheme detection. Leave off until TLS works, or you will lock yourself out. |

Secure cookies, `X-Frame-Options: DENY` and nosniff switch on automatically when
`TESTGEN_DEBUG=0`. With `TESTGEN_SSL=1` as well, `manage.py check --deploy`
reports zero issues.

The server runs this as a Docker stack — app plus its own Caddy, no shared
proxy. See [deploy/README.md](deploy/README.md) for the update procedure.

---

## Exam groups and listening question sets

Each grade runs 4 classes; each class splits into 2 **groups**; each group sits
the diagnostic in one room at one time. That is 8 groups per grade, 24 in all.

One room plays **one recording**, so both papers in a group share the same two
audio clips and differ in which of the recording's two **question sets** they
answer. Groups are derived from `VARIANTS` in `diagnostics/navigation.py`, not
stored — variant A and B are group 1, C and D are group 2, and so on.

`check_papers` proves four things about every sitting: same recordings,
different question sets, no shared speaking prompt, no shared reading passage.

**Known limitation — picture clips.** Each of the five picture recordings
contains seven items, so its two question sets of five overlap by three
(`5 + 5 − 7 = 3`). The two students in a room therefore share 3 of their 5
picture questions; their rotating clip's five questions are fully distinct, so
the two papers always differ on at least 5 of their 10 listening questions.
Additionally, 3 of the 5 picture clips serve two groups each per grade, which
sit at different times — the same exposure the bank already tolerates across
classes. Fixing either would require commissioning new picture audio; both are
accepted by design.

**Rebuild still pending as of 2026-09-01.** The code and the second question
sets are deployed, but the 48 stored papers were built by the old allocator and
still carry the defect — `check_papers` reports 24 recording mismatches against
live data until `build_papers --resample` is run. Rebuilding rewrites every
paper's listening section and redraws its speaking prompts, so **any paper
printed or downloaded before that rebuild is superseded** and must be
re-downloaded before it is administered.

## Known limits

- **Grade 9 has only 46 items**, against ~420 for grade 10 and ~270 for grade 11.
  This is a source-data limit, not a bug: the grade 9 guide lists vocabulary with
  parts of speech but **no definitions**, so definition-based items cannot be
  built for it. Its items are all odd-one-out, derived from the unit categories.
  Either add definitions to the grade 9 guide and re-import, or run the Claude
  pipeline for grade 9 — the pipeline does not need definitions.
- **The mix is recognition-heavy** until the Claude pipeline runs. The sampler
  already weights production types 10:2 over recognition types; it just has
  nothing to draw from yet for four of the six types.
- **Grade 10 Unit 17** has no vocabulary — the source guide says so explicitly
  ("no specific vocabulary list designated for Unit 17"). It is grammar-only.
- **17 of 1,110 vocabulary entries** have no part of speech, because the source
  lists them without one (mostly untagged collocations).
- **Open cloze and sentence reordering** are v2 per the spec (§3.5) and not built.

## Layout

```
config/           settings, urls
content/          syllabus: models, guide parser, import_guide
  parsing/guide_parser.py     handles all three guide formats
bank/             item bank: models, admin review queue, presentation
  generation/bootstrap.py     deterministic item generation (no LLM)
  generation/claude_pipeline.py   offline Claude generation + review
  generation/validation.py    structural + spaCy checks
  generation/schemas.py       Structured Outputs JSON schemas
assembly/         sampling, forms, views, docx export
templates/        server-rendered HTML (no JS framework)
```


WE STOPPED AT THE AGENT SAYING: Extract real listening stems and options