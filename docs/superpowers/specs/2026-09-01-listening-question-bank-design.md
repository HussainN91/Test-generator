# Listening Question Bank — Design

**Goal:** Put every listening question on one staff-only page, each question set
titled with the grades and groups that actually sit it, so the bank can be
checked against its transcripts in one pass instead of paper by paper.

**Status:** design approved 2026-09-01. Not yet implemented.

---

## 1. Why this is not a five-minute job

The obvious reading of the request — "title each set with its grade and group" —
does not survive contact with the data.

Listening questions are stored per **clip**, not per grade. A grade is an
allocation-time concept: `allocation.py` hands a clip pair to a group, and the
same clip is handed to several groups across several grades. So a question set
belongs to many grade/group combinations at once:

```
clip 1, set 1  ->  Grade 9 groups 1, 6 · Grade 10 groups 3, 8 · Grade 11 group 5
clip 2, set 1  ->  Grade 9 group 1 · Grade 10 group 8
clip 3, set 1  ->  Grade 9 group 2 · Grade 11 group 1
```

Measured across all 40 sets in use:

| (grade, group) pairs a set serves | number of sets |
|---|---|
| 1 | 12 |
| 2 | 18 |
| 4 | 2 |
| 5 | 8 |

**No question set is exclusive to a single grade.** A title of the form
"Grade X, groups Y Z" is therefore correct for none of them on its own, and the
page has to carry a compound title or repeat content under each grade.

## 2. Decisions

| Decision | Choice | Why |
|---|---|---|
| Organisation | One canonical list of all 40 sets, with grade tabs as a filter | No duplication, so every question is proofread once; the tab still answers "what does Grade 10 sit?" |
| Purpose | Checking the questions are right | Answers always visible, transcript alongside, picture strips inline |
| Access | Staff only | The page shows all 200 answer keys. Grade-scoping was rejected: because sets are shared, a grade-scoped teacher would still be reading the questions other grades sit, so the separation would be cosmetic |
| Title source | Derived from stored `Paper` rows | Matches `verification.py`'s existing stance — re-derive from what is stored, so a paper written by a bulk update is described truthfully, not theoretically |
| Transcript storage | One `AudioClip.transcript` text field | See §4 |
| Placement | `diagnostics` app, not `bank` | The existing "Bank coverage" page is the vocabulary/grammar item bank for the test generator — a different subsystem. Listening content lives in `diagnostics` |

### Rejected alternatives

- **Repeat each set under every grade.** Turns ~200 questions into ~460 entries
  and makes a proofreading pass read the same question three times. Rejected in
  favour of tabs, which give the same "one grade at a time" view without the
  duplication.
- **Read the transcript markdown at render time.** Saves the migration, but
  couples a web view to a file in `media/`, re-parses per request, leaves the
  transcript outside the database backups, and 500s if the file is absent.
- **Extend the Django admin instead.** The admin already lists listening
  questions, but it is row-oriented: checking one answer means opening the row,
  finding the transcript elsewhere, and going back. Wrong shape for reading 200
  questions against their source.

## 3. Page structure

```
Listening bank                                    staff only
20 clips · 40 question sets · 200 questions

[ All ] [ Grade 9 ] [ Grade 10 ] [ Grade 11 ]     <- ?grade=9

Answer key balance     picture A/B/C · mcq3 A/B/C · true_false A/B

+-------------------------------------------------------------+
| Grade 9 groups 1, 6 · Grade 10 groups 3, 8 · Grade 11 group 5|
| Clip 1 · picture · set 1 · first recording                   |
| [audio player]                                               |
|                                                              |
|  Questions                        |  Transcript              |
|  1. Which dish did Mark cook?     |  **1. Which dish...**    |
|     [picture strip A B C]         |  Interviewer: So you've  |
|     answer: C                     |  won the teenage chef... |
|  ...                              |  (scrollable panel)      |
+-------------------------------------------------------------+
```

Ordered by clip number, then set number. The grade filter hides sets no paper in
that grade sits; it is a convenience, not a permission boundary.

### Per question

Stem; options lettered with the correct one marked; the picture strip inline for
picture clips; `acceptable_answers` listed for gap-fill. Reuses
`rendering.option_rows` and `rendering.needs_inline_blank` so the page agrees
with how the same question renders on a paper.

### Answer key balance panel

Counts of each answer letter per task type, across the visible sets. Cheap to
render and it is exactly what surfaced the set 2 mcq3 skew (A=6 B=14 C=5, since
corrected) during the content review on 2026-09-01.

## 4. Transcripts

Transcripts are currently **not in the database**. They exist only as
`media/diagnostics/audio/transcripts-full.md` (40 KB), which is gitignored, and
for clips 11–20 that file is the sole copy — the checked-in `Transcripts.docx`
holds only clips 1–10.

Adding `AudioClip.transcript` and importing that file therefore does two jobs:
it supplies the page, and it moves an irreplaceable single-copy artefact into
the database, where it is covered by the server's existing backup routine.

**Stored whole, not per item.** One text field per clip holding the clip's body
verbatim. Picture clips contain seven discrete items and it is tempting to split
them so each question sits beside its own item — but the item headings are
already inside the text (`**6. Where will the friends meet?**`), so a reviewer
can match them by eye. Splitting would need either a new model or a JSON schema
for no real gain. Explicitly out of scope.

The import is idempotent and re-runnable: it overwrites `transcript` on each
clip from the file, and never touches questions.

## 5. Components

| File | Change | Responsibility after |
|---|---|---|
| `diagnostics/models/content.py` | modify | `AudioClip.transcript` |
| `diagnostics/migrations/0018_audioclip_transcript.py` | create | nullable-safe text field, default `""` |
| `diagnostics/management/commands/import_transcripts.py` | create | parse the markdown, write one transcript per clip |
| `diagnostics/listening_bank.py` | create | pure: set -> (grade, group) usage, titles, key-balance counts |
| `diagnostics/views.py` | modify | `listening_bank` view, staff-gated |
| `diagnostics/urls.py` | modify | `listening/` route |
| `templates/diagnostics/listening_bank.html` | create | the page |
| `templates/base.html` | modify | nav link, `{% if user.is_staff %}` |
| `diagnostics/tests/test_listening_bank.py` | create | mapping, filter, access |
| `diagnostics/tests/test_import_transcripts.py` | create | parse, idempotency |
| `README.md` | modify | document `import_transcripts` |

`listening_bank.py` exists so the grade/group derivation is a pure function
testable without HTTP — the view then only arranges what it returns.

## 6. Error handling

| Case | Behaviour |
|---|---|
| Non-staff user | 404, consistent with `_get_visible_paper`'s "no paper here" stance rather than advertising the page exists |
| Clip with no transcript imported | Panel shows "No transcript imported" — the page still works; the transcript is an aid, not a dependency |
| Set no paper uses | Titled "Not currently allocated to any paper" and shown under All. A set with no home is exactly what a reviewer needs to see, not something to hide |
| Transcript file missing at import | `CommandError` naming the path. The command fails; the page is unaffected |
| Unknown `?grade=` value | Falls back to All rather than erroring |

## 7. Testing

- `import_transcripts` parses all 20 clips from the real file; re-running changes
  nothing; a missing file raises `CommandError`.
- The usage mapping returns the known multiplicities from §1 (12 sets serve one
  pair, 18 serve two, 2 serve four, 8 serve five) against a built bank.
- A set used by no paper is reported as unallocated rather than omitted.
- Non-staff get 404; staff get 200.
- No filter shows 40 sets and 200 questions; `?grade=9` shows only sets a
  grade 9 paper uses.
- Key-balance counts match a direct query.

## 8. Deployment

Adds migration `0018` and one new command. On the server:

```bash
git pull
docker compose up -d --build      # required: the command lives in the image
docker compose exec testgen python manage.py migrate
docker compose exec testgen python manage.py import_transcripts
```

The rebuild is not optional — see the README's deployment note. The transcript
markdown itself is under `media/`, which is bind-mounted and so already current,
but the command that reads it is not.

No paper rebuild. Nothing here touches `Paper`, allocation, or question content.

## 9. Out of scope

- Editing questions from this page. Read-only; the admin already edits.
- Reading, writing and speaking banks. Listening only, as asked.
- Per-item transcript splitting (§4).
- A check that question order follows the recording order. The 2026-09-01
  content review found and fixed that defect by hand, and nothing currently
  guards it. Worth a `verification.py` check, but it belongs with the other
  invariants, not on a display page.
