# Handoff — Diagnostic Test Generator (`diagnostics` app)

Written 2026-08-24, last updated 2026-08-26 after Task 12 (full verification pass) of the
16-variants revision, for a fresh Claude Code session with zero prior context. Read this
whole file before touching code. **This supersedes every earlier version of this file.**
If you find an older cached copy — the 2026-08-24 or 2026-08-25 versions, or the original
17-task plan alone — it's stale, follow this one.

## What this is

A Django app that produces **48 fixed diagnostic test papers** — Grades 9, 10, 11 × 16
variants (A–P), 40 marks each (Listening/Reading/Writing/Speaking, 10 marks each), all CEFR
B1. It is **not** a generative engine: content is imported once from real client sources,
then assembled by a deterministic allocator; the Django app is a catalogue, exporter, and
generation tracker over that content.

It lives as a new `diagnostics` app inside an **existing** Django project at
`D:\Test generator`, which already has three other apps (`content`, `bank`, `assembly`)
implementing a *different* system — a syllabus-unit item bank for a separate test generator.
`diagnostics` imports nothing from those apps. Its infrastructure (Django auth, `python-docx`
export helpers, settings, deployment, `static/css/paper.css`) is reused; its content is not.

This diagnostic app is one piece of a much larger planned system ("Expert Council," a teacher
hub) that doesn't exist yet. The app is deliberately built decoupled — `settings.AUTH_USER_MODEL`
not a concrete `User`, no cross-app imports — so it can be merged into that system later
without rework.

## Read these first, in order

1. **`docs/superpowers/specs/2026-08-24-diagnostic-test-generator-design.md`** — the original
   design spec. Client requirements, the listening-clip allocation table, why the existing
   `bank`/`assembly` bank isn't reused, merge-path constraints.
2. **`docs/superpowers/specs/2026-08-24-diagnostic-test-generator-design-revision-1.md`** —
   documents the real, richer content bank discovered after the original spec
   (`D:\Diagnostics Gate\Question Bank -Diagnostic Test.xlsx`) and how it changed Reading/
   Writing/Speaking from "fixed authored sets" to "shared item bank + per-paper sampling."
3. **`docs/superpowers/specs/2026-08-25-diagnostics-16-variants-and-layout-design.md`
   ("Design Revision 2") — the current one.** Written after client management reviewed the
   completed 12-paper build and asked for five changes: 16 variants per grade, embedded
   audio, better listening/photo distribution, and simpler downloads. **Where this document
   and either earlier one disagree, this one wins; where it is silent, the earlier ones still
   stand.** This is the spec actually implemented in the codebase as it exists today.
4. **`docs/superpowers/plans/2026-08-24-diagnostics-content-foundation.md`** — original
   17-task plan. Tasks 1–12 (schema, listening pipeline) are done. Tasks 13–17 are superseded.
5. **`docs/superpowers/plans/2026-08-24-diagnostics-real-content-revision.md`** — superseded
   old Tasks 13–17. All 10 tasks are done, including Task 10 (`diagnostics/sampling.py`),
   which an earlier version of this file incorrectly claimed was unbuilt — it exists and is
   exercised by every paper build.
6. **`docs/superpowers/plans/2026-08-25-diagnostics-16-variants-and-layout.md`** — the plan
   that implemented Design Revision 2 above. All tasks done, including this file's own
   Task 12 (this verification pass).

A separate, concurrent session also built a **navigation restructure** on top of this
revision (grade picker → 4 class packs per grade → that class's 4 variants). It isn't
covered by a dedicated spec/plan doc under `docs/superpowers/` — read `diagnostics/navigation.py`
directly, it's short and explains itself.

## Absolute constraints — do not violate these

- **No git.** This project has no `.git` and the user has explicitly declined version
  control ("relatively small project"). Do not run `git init` or any git command. No commit
  steps anywhere — intentional.
- **`D:\Diagnostics Gate` is read-only client source material.** Never write, move, or
  delete anything there. All extraction code opens files read-only. A live-Excel risk was
  observed during the original build (the source workbook found open in Excel mid-session
  via its `~$...xlsx` lock file) — no data loss resulted, but if you see that lock file
  present, mention it to the user and ask them to close Excel without saving before relying
  on a fresh read.
- **The old "zero sharing within a grade" rule is gone — deliberately, by explicit client
  instruction, and this was a documented reversal, not a bug.** The original spec called
  "the variants within one grade share zero content" *inviolable*. At 16 variants per grade
  that rule became arithmetically unsatisfiable against the real bank size (e.g. 20 listening
  clips can supply at most 20 zero-share paper-slots per grade if each paper used only one,
  and each paper needs two; 15 reading passages can't supply 16 zero-share slots either — see
  Design Revision 2 §1 for the full table). Management chose to relax the rule rather than
  grow the content bank threefold. It is now a **capped reuse** rule: how many times one
  component may repeat *within a single grade* is set per component type in
  `diagnostics/constants.py`'s `REUSE_CAPS` (picture clip 4×, rotating clip 2×, reading
  passage 2×, speaking prompt 2×, writing question 1× — writing keeps genuine zero-reuse
  because its pool comfortably supports it). Cross-grade reuse remains unrestricted, as
  before. Enforced by `diagnostics/allocation.py` (the deterministic allocator) at build
  time and independently re-verified by `check_papers` (see below) — `Paper.clean()` alone
  is still not sufficient in production code paths (Django's `.create()`/`update_or_create()`
  skip it), so `check_papers` remains the real safety net, not optional polish.
- **Do not add a `test_type` field to `Paper`.** Mid-term/placement tests are handled by the
  *other* existing generator (`bank`/`assembly`), by explicit user decision. Keep
  `diagnostics` scoped to the beginning-of-year diagnostic only.
- **Flat B1 difficulty across all three grades** — grade determines *which* paper, not how
  hard it is.
- **The workbook is the living source of truth, treated adaptively.** Import commands
  enforce *minimum sufficiency* (enough content for the grade's variants), never an exact
  historical snapshot count. If the client's bank grows or changes next term, the pipeline
  should adapt, not break.
- **No ZIP export.** Client management asked for simpler downloads — five independent files
  per paper (student test, answer key, examiner/speaking pack, two audio clips) instead of
  one bundled ZIP. The ZIP pack code was removed entirely; do not re-add it. Photos are not
  independently downloadable — they exist only embedded inside the rendered `.docx` files.

## Environment

- Windows. Python 3.14.4, Django 6.1 (pinned in `requirements-lock.txt`; `requirements.txt`
  says `>=5.2`). `requirements-lock.txt` is not kept in lockstep with every dependency
  addition (Pillow and openpyxl are both missing from it) — pre-existing project convention,
  not a bug to fix.
- Interpreter: `.venv\Scripts\python.exe` — always use this.
- Run the **whole project's** tests (diagnostics shares `static/css/paper.css` with
  `assembly`/`bank`, so a diagnostics-only run doesn't prove nothing else broke):
  `.venv\Scripts\python.exe manage.py test -v 2`. Run just `diagnostics` with
  `.venv\Scripts\python.exe manage.py test diagnostics -v 2` for faster iteration, but treat
  the project-wide run as the one that actually gates completion.
- Work from `D:\Test generator`.
- **`Start Test Generator.bat`** (project root) is a double-click launcher for non-technical
  users: checks the venv, applies pending migrations, starts `runserver` on 127.0.0.1:8000,
  opens Chrome once the server answers. Detects an already-running instance instead of
  crashing. Closing its window stops the server.
- `settings.DIAGNOSTICS_SOURCE_DIR` points at `D:\Diagnostics Gate` by default, overridable
  via env var.
- `MEDIA_URL` reads back as `/media/` (Django 6.1 auto-prefixes) even though `settings.py`
  sets `"media/"` — correct framework behavior, not a bug.
- **If you write any future test that exercises a command/view writing to an
  `ImageField`/`FileField`/audio `FileField`, override `MEDIA_ROOT` to a temp directory for
  the test class** (`setUpClass`/`tearDownClass` with `override_settings(...).enable()/
  .disable()` + `tempfile.mkdtemp()`). Django `TestCase`'s DB rollback does NOT undo file
  writes.

## Progress: the whole revision is built and verified end-to-end

**312 tests pass project-wide** (full `manage.py test`, not just `diagnostics`) — confirmed
2026-08-26. This is diagnostics' own suite plus `content`/`bank`/`assembly`'s, run together
because they share `static/css/paper.css`.

### Phase A — schema + listening pipeline (original plan, Tasks 1–12)
Full model schema; `AudioClip`/`ListeningQuestion` imported from the client's
`.docx`/`.md`/audio files (20 clips, 100 questions, 25 images in verified document order, 20
audio files); a tolerant answer-key parser handling 6+ real formatting inconsistencies;
`verify_listening_keys` command + `KeyVerification` model built. **Task 12's human
listening sign-off has still not happened** — `KeyVerification` has 0 rows in the live
database. This is unchanged from every earlier version of this file — see "What's left."

Note: an earlier version of this file claimed listening question stems were still generic
placeholders (`"Clip 3, question 2"`). That claim was itself stale/wrong by the time this
revision started — the stems are, and were, real question text. Correcting the record here;
nothing in this revision needed to fix a placeholder-stems problem because it didn't exist.

### Phase B — real content bank + sampling model (revision plan, all 10 tasks, all done)
Reading schema widened (word bounds 150–300, 5 subtypes); `WritingSet`/`SpeakingSet`
fixed-container models retired in favor of standalone shared-pool items sampled per paper via
`PaperWritingQuestion`/`PaperSpeakingPrompt` through-models; 15 real reading passages (150
questions), 200 real writing questions, 50 real speaking prompts + 5-row marking rubric
imported from the client's workbook, with several genuine source-data inconsistencies found,
verified, and preserved per the "master key wins" authority rule (see code comments in
`diagnostics/extraction/` for specifics — writing items 123/135). `diagnostics/sampling.py`
(the random-with-exclusion sampler) is built and is what every `build_papers` run actually
calls.

Also fixed in this phase: **7 mis-subtyped reading questions (R04/R10)** — reclassified from
`mcq` to `paragraph_matching` after independent verification against the raw source
workbook. See `diagnostics/migrations/0006_alter_readingquestion_subtype.py` and the
extraction/test files under `diagnostics/tests/` and `diagnostics/extraction/xlsx_reading.py`
for the detail.

### Phase C — Design Revision 2: 16 variants, listening rebalance, layout, downloads, audio
Everything management asked for in their 2026-08-25 review, all built and verified:

1. **16 variants per grade (48 papers total)**, replacing 4. `diagnostics/constants.py`'s
   `VARIANTS` is now `"ABCDEFGHIJKLMNOP"`. Verified live: `Paper.objects.count()` == 48,
   16 per grade for grades 9/10/11.
2. **Deterministic allocator, capped reuse** — `diagnostics/allocation.py` replaces the old
   "zero sharing" rule with `REUSE_CAPS` from `constants.py` (see "Absolute constraints"
   above for why and the exact caps). `check_papers` independently re-derives and confirms
   every paper obeys its component's cap, within its grade.
3. **Listening rebalanced — the core original complaint, fixed.** Every paper now gets
   exactly one of the 5 "picture" clips (which carry all 25 images in the bank) plus one
   rotating clip from the other 15. Old world: A/C variants had 5 photos and the two easiest
   task types, B/D variants had 0 photos and the two hardest — same problem, one root cause.
   New world, verified live against all 48 real papers: every single paper has **exactly 5**
   photo questions (`ListeningQuestion` rows with a non-blank `image`, restricted to the
   paper's two clips) — zero papers with 0, zero with any count other than 5.
4. **Layout overhaul** (`diagnostics/rendering.py`): bold stems, options laid out in shared
   lines (2/3/4-option questions get 2, 1, or 1 line respectively instead of one line per
   option), no separate answer line for option-less questions (students write/circle
   inline), reading questions grouped by subtype with one instruction per group instead of
   one per question.
5. **Downloads simplified, ZIP removed.** `diagnostics:paper_file` serves five independent
   downloads per paper — `student`, `answer_key`, `examiner` (docx, via `export.py`'s
   `examiner_docx`), `audio_1`, `audio_2` (the paper's two source `.mp3` files, served as
   plain attachments) — each recorded as its own `GenerationEvent`. No ZIP code remains
   anywhere in `diagnostics/` (confirmed by grep — the only `zipfile` usage left is in
   `diagnostics/extraction/docx_images.py`, which reads `.docx` files as zip containers
   during *import*, unrelated to the removed download feature). Photos are not independently
   downloadable by design — only embedded in the rendered documents.
6. **Audio embedded natively in the web preview.** `paper_detail` renders one `<audio
   controls>` element per recording with a real `src` pointing at `/media/...`. Verified live
   via the Django test client against a real paper: exactly 2 `<audio>` tags, both with
   populated `src` values resolving to real files under `MEDIA_ROOT`.

### Phase D — navigation restructure (concurrent session, on top of Phase C)
Grade picker → 4 class packs per grade → that class's 4 variants, matching how the school
actually hands papers to classes (4 classes per grade, 4 papers per class, sequential — class
1 gets variants A–D, class 2 gets E–H, etc.). New module `diagnostics/navigation.py`
(`variants_for_class`, `class_for_variant`, `variant_span` — pure functions, nothing stored,
derived from `VARIANTS` positionally so the grouping can't drift from the paper set). New
views `grade_detail`/`class_pack` in `diagnostics/views.py`, new templates
`templates/diagnostics/grade_detail.html` and `templates/diagnostics/class_pack.html`;
`templates/diagnostics/paper_index.html` rewritten as the top-level grade picker instead of
listing all papers flat.

## Task 12 verification pass — what was actually run and confirmed (2026-08-26)

All of the following were run for real against the live database and a real render, not
inferred from tests alone:

- **Full project test suite:** `manage.py test -v 2` → **312 tests, OK** (0 failures, 0
  errors).
- **Paper rebuild:** `manage.py build_papers --resample` → "Built 48 papers (48 sampled, 0
  already complete and left unchanged)."
- **Paper check:** `manage.py check_papers` → "All 48 papers pass: complete sections, and no
  component shared beyond its reuse cap within any grade."
- **16 variants:** live query confirmed `Paper.objects.count()` == 48, and exactly 16 for
  each of grade 9, 10, 11.
- **Photo distribution:** live query across all 48 real papers, counting
  `ListeningQuestion`s with a non-blank `image` restricted to each paper's two listening
  clips, produced `Counter({5: 48})` — every paper has exactly 5 photo questions, no
  exceptions. This was flagged as the single most important thing to verify; it passed.
- **Audio embedding:** rendered `paper_detail` for a real paper (grade 9, variant A) via the
  Django test client, logged in as staff. Response 200. Exactly 2 `<audio>` tags found, both
  with real `src` values (`/media/diagnostics/audio/clip-01.mp3`,
  `/media/diagnostics/audio/clip-02.mp3`).
- **Five separate downloads, no ZIP:** same real paper, same test client — `paper_file`
  resolved and served all of `student`/`answer_key`/`examiner`/`audio_1`/`audio_2` with HTTP
  200 and correct `Content-Type`/`Content-Disposition` (e.g. `G9-A-Student.docx`,
  `G9-A-clip-01.mp3`). Grep confirmed no `build_pack`/ZIP-download code remains in
  `diagnostics/`.
- **Real renders:** `manage.py render_paper` run for grade 9 variant A, grade 10 variant H,
  grade 11 variant P — all three rendered without error (student + answer-key `.docx` each;
  the examiner pack is generated by the web download path via `export.py`'s `examiner_docx`,
  not by this management command, which is expected — see its `--help` text).
  Paragraph/table counts as a rough manual-review proxy (from `python-docx`):

  | File | Paragraphs (non-empty) | Tables |
  |---|---|---|
  | G9-A-Student.docx | 84 (76) | 18 |
  | G9-A-AnswerKey.docx | 7 (7) | 4 |
  | G10-H-Student.docx | 90 (82) | 20 |
  | G10-H-AnswerKey.docx | 7 (7) | 4 |
  | G11-P-Student.docx | 86 (78) | 20 |
  | G11-P-AnswerKey.docx | 7 (7) | 4 |

  These numbers are a sanity-check proxy only, not a substitute for a human opening the files
  and reading them.

**Verdict: DONE_WITH_CONCERNS.** Every automatable check passed. The one thing that remains
unautomatable and outstanding is Task 12's human listening sign-off (see below) — carried
forward unchanged from every earlier version of this file, not newly discovered.

## Real database state right now (verified by live query, 2026-08-26)

| Model | Count |
|---|---|
| `AudioClip` | 20 |
| `ListeningQuestion` | 100 |
| `ReadingPassage` | 15 |
| `ReadingQuestion` | 150 |
| `WritingQuestion` | 200 |
| `SpeakingPrompt` | 50 |
| `SpeakingRubric` | 5 |
| `Paper` | **48** (16 per grade × 3 grades) |
| `KeyVerification` | **0** — the human listening sign-off has not happened |

## What's left

Genuinely still open, not superseded by this revision:

- **Task 12's human listening sign-off has still not happened.** Someone with ears needs to
  run `.venv\Scripts\python.exe manage.py verify_listening_keys` and check the printed
  answers against the real audio in
  `D:\Diagnostics Gate\Listening Diagnostic Audio files\`, then re-run with
  `--sign-off "Name"`. An AI agent cannot do this. Don't fabricate a sign-off. This has been
  true and unchanged since the very first version of this file.
- **Human review of extraction accuracy.** The client should review the extracted content
  for correctness before it's trusted for real students — separate from, and in addition to,
  the listening sign-off above. Not automatable.
- **Human review of the six freshly-rendered `.docx` files** from this verification pass
  (see the table above) — the paragraph/table counts are a sanity-check proxy only, nobody
  has opened these specific files and read them end-to-end since the 16-variant/layout
  revision landed.
- **CEFR conversion table** — noticed in the workbook (`CEFR Conversion table LRW` tab: raw
  marks → CEFR level, per-skill and overall) but never extracted or wired into any export.
  Should feed the answer-key/scoring guide once that exists. Out of scope for every revision
  so far, including this one (Design Revision 2 §0 explicitly names it out of scope).
- Sections 4–8 of the original design spec beyond what's been built (generation tracking
  beyond `GenerationEvent`/`GenerationWindow`, admin coverage reporting, Expert Council merge
  seams) still aren't planned in task-by-task detail.

**Superseded — do not act on these, kept here only so an old cached memory of them doesn't
mislead you:**

- ~~`diagnostics/sampling.py` not built~~ — built, and every `build_papers` run depends on it.
- ~~`build_papers`/`check_papers`/`render_paper` not built~~ — all three exist, all three
  work, all three were re-run for real as part of this verification pass.
- ~~Listening question stems are generic placeholders~~ — they were already real question
  text before this revision started; the earlier claim to the contrary was itself wrong.
- ~~12 papers, 4 variants per grade~~ — 48 papers, 16 variants per grade, since Design
  Revision 2.
- ~~ZIP export pack~~ — removed entirely, replaced by 5 independent downloads.
- ~~Audio not embedded in the web UI~~ — embedded, one `<audio>` player per recording.
- ~~Uneven photo distribution across variants~~ — fixed; every paper now gets exactly 5.

## How to continue

The pattern used throughout this build: for each task, (1) dispatch a fresh subagent with
the full task text plus enough context to work independently, requiring TDD and a
self-review before reporting back; (2) dispatch a second fresh subagent to independently
verify spec compliance by reading the actual code, not trusting the implementer's report;
(3) a third for code quality (or combine 2+3 for low-risk tasks); (4) fix real findings
before moving on. **For extraction tasks against real, messy data specifically**: expect the
starting/planned code to be wrong in real ways, budget time for actual debugging against raw
`openpyxl` rows, and manually spot-check output against the source — tests passing does not
by itself prove semantic correctness. When something looks like "the source data is
inconsistent," verify that directly against raw rows before accepting it.

Don't skip straight to writing code from memory of "what a diagnostic test generator
probably needs." The plan documents encode decisions that took real investigation and
back-and-forth to settle — the listening allocation table, the reuse-cap numbers, the
sampling-vs-fixed-set architecture, the class-pack grouping. Read the spec and plan documents
listed at the top before changing direction, especially Design Revision 2 if the work touches
paper counts, layout, downloads, or listening/photo distribution.
