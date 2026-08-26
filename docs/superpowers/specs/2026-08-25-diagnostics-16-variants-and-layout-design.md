# Design Revision 2 — 16 variants per grade, listening rebalance, paper layout

Written 2026-08-25. Supersedes parts of the original design spec
(`2026-08-24-diagnostic-test-generator-design.md`) and Design Revision 1
(`2026-08-24-diagnostic-test-generator-design-revision-1.md`). Where this
document and either earlier one disagree, **this one wins**; where it is
silent, they still stand.

Driven by client management feedback received 2026-08-25 after the 12-paper
build was complete. Five changes were asked for: more variants, embedded
audio, better listening-question distribution, better photo distribution, and
a simpler download model.

---

## 0. What is already built, and what this revision does not touch

The `diagnostics` app is complete through content import and paper assembly:
20 audio clips / 100 listening questions, 15 reading passages / 150 questions,
200 writing questions, 50 speaking prompts + 5 rubrics, and 12 assembled
papers with a teacher-facing browse/preview/download UI. 106 app tests pass.

**Unchanged by this revision**, and explicitly still in force:

- No git. The project has no `.git` and the user has declined version
  control. No commit steps appear anywhere in this spec or its plan.
- `D:\Diagnostics Gate` is read-only client source material.
- Flat B1 difficulty across all three grades.
- No `test_type` field on `Paper` — mid-term/placement remains the other
  generator's job.
- The workbook is the living source of truth; importers enforce minimum
  sufficiency, never an exact historical count.
- Cross-grade content reuse is permitted and expected.
- The `static/css/paper.css` "Examinations Office" design system is the
  single source of truth for visual styling. Extend it; do not fork it.

**Out of scope here** (raised in earlier docs, not raised by management, and
deliberately left alone): Task 12's human listening sign-off, the CEFR
conversion table, teacher-assignment UI beyond what exists, and the Expert
Council merge seams.

---

## 1. The problem, stated in numbers

Management asked for **16 variants per grade** instead of 4 — 48 papers
instead of 12. Measured against the real bank, at one paper per variant:

| Component | Per paper | Pool | Needed per grade @16 | Under the old "share nothing" rule |
|---|---|---|---|---|
| Listening clips | 2 | 20 | 32 | **impossible** — short 12 |
| Reading passages | 1 | 15 | 16 | **impossible** — short 1 |
| Speaking prompts, per task | 1 | 10 each | 16 each | **impossible** — short 6, five times over |
| Writing grammar | 3 | 50 | 48 | possible, 2 spare |
| Writing jumbled | 3 | 50 | 48 | possible, 2 spare |
| Writing vocabulary | 2 | 50 | 32 | comfortable |
| Writing fill-blank | 2 | 50 | 32 | comfortable |

The original spec called "the four variants within one grade share *zero*
content" **inviolable**. At 16 variants that rule is not merely hard, it is
arithmetically unsatisfiable for three of the four sections. No amount of
cleverness in the sampler changes that. Either the bank grows by roughly
threefold, or the rule changes.

Management's other two complaints are confirmed exactly by the assembled data:

```
G9-A  | clips 1,2  | picture + mcq3        | photos: 5
G9-B  | clips 3,4  | gap_fill + true_false | photos: 0
G9-C  | clips 5,6  | picture + mcq3        | photos: 5
G9-D  | clips 7,8  | gap_fill + true_false | photos: 0
```

Every A and C variant carries 5 photos and the two most approachable
listening task types. Every B and D carries zero photos and the two hardest.
All 25 images in the bank hang off the 5 `picture`-type clips, so *photo
distribution and listening-task distribution are one problem, not two*.

---

## 2. Decision: capped reuse replaces the zero-sharing rule

The "share nothing within a grade" rule is **retired**, by explicit client
decision on 2026-08-25, and replaced with a two-part rule:

1. **No two variants within a grade are the same combination** of components.
   (Already guaranteed in practice, and still verified.)
2. **Each individual component may repeat within a grade, up to a per-component
   cap** chosen from the real pool size:

| Component | Pool | Cap per grade | Slots available | Slots needed |
|---|---|---|---|---|
| Picture listening clip | 5 | 4 | 20 | 16 |
| Rotating listening clip (mcq3 / gap_fill / true_false) | 15 | 2 | 30 | 16 |
| Reading passage | 15 | 2 | 30 | 16 |
| Speaking prompt, per task | 10 each | 2 | 20 per task | 16 per task |
| Writing question, per subtype | 50 each | 1 (no reuse) | 50 per subtype | ≤48 per subtype |

Writing keeps genuine zero-reuse because the pool supports it — the cap
mechanism applies there with a cap of 1, so one code path covers every
component rather than writing being a special case.

Caps are scoped **per grade**. Grade 9's budget is independent of grade 10's,
which is what makes cross-grade reuse continue to work unchanged.

This is a deliberate, documented reversal of a rule earlier specs called
inviolable. It is recorded here so that a future reader does not "fix" the
sampler back to zero-sharing and break the 48-paper build.

### 2.1 Variant labels

`VARIANTS` grows from `("A","B","C","D")` to `A`–`P` (16 letters).
`Paper.variant` is already `max_length=1`, so no field-width change is needed;
the `choices` list changes, which Django will want a migration for.
`EXPECTED_PAPER_COUNT` derives from `len(GRADES) * len(VARIANTS)` and becomes
48 automatically.

### 2.2 Allocation must be deterministic

`PAPER_ALLOCATION` is currently a hand-written 12-entry table. A hand-written
48-entry table is unmaintainable and easy to get subtly wrong. It is replaced
by a **pure, deterministic allocation function** — a function of
`(grade, variant)` alone, with no RNG — that yields the listening pair and
reading passage for every paper.

Determinism is a correctness requirement, not a preference: `build_papers`
uses `update_or_create` for listening and reading, so those fields are
rewritten on every run. If allocation were random, re-running the build would
silently reissue different content under the same paper name, and two
teachers holding "G9-A" would have different tests.

Writing and speaking remain randomly sampled, but keep their existing
protection: a paper that already has its full complement is left untouched
unless `--resample` is passed.

---

## 3. Listening section rebalance

**Every paper is one picture clip plus one rotating clip.** The rotating clip
cycles evenly through the three non-picture task types across a grade's 16
variants (6 / 5 / 5 across mcq3 / gap_fill / true_false, or any split the
allocation function makes even and cap-legal).

Consequences, each mapping to a stated complaint:

- Every paper carries **exactly 5 photo questions**. Photo distribution
  becomes perfectly uniform — the complaint is resolved at its root, because
  the photos live on the picture clips and now every paper has one.
- Every paper carries an **identical difficulty shape**: one visual/recognition
  set and one text-based set. No variant is systematically easier than another.
- The **two-recording, 5+5 test shape stays unchanged**. No new audio needs to
  be authored, and the listening section does not get longer.

The cost, accepted knowingly: only 5 picture clips exist, so each is reused up
to 4 times per grade (hence the cap of 4 in §2). Within one grade, 16 students
sitting different variants will encounter one of 5 photo sets. This is a
direct consequence of the bank's composition; the only alternative is
commissioning more picture-based clips.

`CLIP_TASK_TYPES`, `PROFILE_X` and `PROFILE_Y` remain accurate descriptions of
the bank. `PROFILE_X`/`PROFILE_Y` become unused by the allocator (they encoded
the old hardest-with-easiest pairing) and should be removed rather than left
as dead constants that imply a rule no longer in force.

---

## 4. Content defects

### 4.0 Listening stems are already correct — no work needed

`HANDOFF.md` states that all 100 listening question stems are placeholders
(`"Clip 3, question 2"`) and that fixing them blocks any printable paper.
**This is stale and wrong.** Verified directly against the database on
2026-08-25: **0 of 100** stems are placeholders. Every one carries real text,
and mcq3/true_false questions carry their real options:

```
clip 1 (picture)     "Which dish did Mark cook in the competition?"      options []      answer C
clip 2 (mcq3)        "Simon's mum decided to take him to the centre..."  options [3]     answer A
clip 3 (gap_fill)    "Caspar's mother dances across a ______ in the..."  options []      answer rope
clip 4 (true_false)  "Lucas thinks Candy Floss gave a great perf..."     options [YES,NO] answer A
```

`diagnostics/extraction/listening_content.py` already parses all four task
shapes, `import_listening.py` already consumes it, and the data is loaded.
Text encoding is clean too — apostrophes are proper U+2019, and no row in any
content model contains a U+FFFD replacement character.

`HANDOFF.md` is stale in the same way about `sampling.py`, `build_papers`,
`check_papers` and `render_paper`, all of which it lists as unbuilt and all of
which exist. Treat its "What's left" section as unreliable and verify against
the code and database before acting on it.

**Consequence for this revision:** one line of gap-fill evidence above
directly confirms the §5.4 rule. Clip 3's stem already ends
`"...dances across a ______ in the circus."` — it carries its own blank. Any
renderer that unconditionally appends `______` to option-less questions would
print two blanks on 25 listening questions. §5.4 is not a hypothetical guard.

### 4.1 Seven reading questions are mis-subtyped

Seven questions stored with `subtype="mcq"` have **zero options**:

```
R04 positions 6-10  | answers D, A, C, B, E  | stems are statements, not questions
R10 positions 9-10  | answers B, A           | stems are "Shared gardens" / "Rooftop gardens"
```

An answer of `E` is impossible for a four-option MCQ, and the stems are
match-to-paragraph statements. These are **`paragraph_matching` items imported
under the wrong subtype**, not MCQs missing their options.

Fix: re-verify both passages against the raw workbook rows, correct the
subtype, and add a regression guard — mirroring the existing writing-bank
mismatch guard — that fails loudly if a future re-import produces an `mcq`
row with no options.

---

## 5. Paper layout — print and screen

All of the following apply **identically to the printed `.docx` and the
on-screen preview**. The preview's stated purpose is showing "the paper as it
will print"; a preview that differs from the print is worse than no preview.

Target: reduce a paper from roughly 5 pages to roughly 3, printed
double-sided.

### 5.1 Question stems are bold

Every question stem renders bold, in both outputs.

### 5.2 Options go on shared lines

| Options | Layout |
|---|---|
| 4 (reading mcq, all writing subtypes) | Two per line — `A) … B) …` then `C) … D) …` |
| 3 (listening mcq3) | All three on one line |
| 2 (listening true/false — YES/NO) | Both on one line |

In `.docx` this is a **borderless table** with the appropriate column count —
the reliable way to get aligned columns out of `python-docx`. On screen it is
a CSS grid column-count change in the existing `.qopts` rule; the listening
override that currently forces `grid-template-columns:1fr` is removed.

### 5.3 The separate answer line is removed

`Answer: ______` is deleted from every question. Students circle their choice
directly. This removes one line per question across roughly 35 questions per
paper.

### 5.4 Questions with nothing to circle get an inline blank

Around 11 questions per paper have no options and cannot be circled:
listening gap-fill, reading true/false/NG, reading completion, heading
matching, paragraph matching. These get a short ruled blank appended to the
stem line itself — `3. The class starts at ______` — costing no extra line.

**One conditional, and it is not hypothetical:** the 25 listening gap-fill
stems already end with their own `______` marker, because the extractor
authored them that way — verified in §4.0. Appending a second blank to those
would print two. The renderer appends a blank **only when the stem contains no
existing gap marker** (`______`, `…………`, or a `(n)` gap reference).

### 5.5 Section instructions change to match

The current instruction text tells students to write answers in spaces that
will no longer exist:

- Reading: *"Write your answers in the spaces provided"* → must describe
  circling for the MCQ-style items and writing on the line for the rest.
- Writing: *"…write its letter (A, B, C or D) in the space provided"* →
  becomes circling.

### 5.6 Reading questions get grouped sub-instructions

The student `.docx` currently prints a bracketed subtype label after every
reading stem (`[True / False / Not Given]`). That is clutter, and 10 of them
cost 10 lines' worth of visual noise.

They are replaced by grouping the reading questions by subtype under a single
short italic instruction per group. This is what real exam papers do, it
costs about 3 lines instead of 10, and — unlike simply deleting the labels —
it does not leave the student unable to tell a T/F/NG item from an MCQ.

*Judgement call flagged for review:* this is the one layout change in §5 not
directly requested. It is included because §5.3 removes the answer line that
was implicitly signalling "this one is different," and without a replacement
signal the paper becomes ambiguous to sit.

### 5.7 Page count is measured, not assumed

The 5→3 page target cannot be asserted by a unit test. A real `.docx` is
rendered per grade and inspected before this revision is called done. If three
pages is not reached, the shortfall is reported rather than quietly accepted.

---

## 6. Audio embedded in the site

The Listening section of the paper preview gains a native HTML `<audio>`
player **per recording, at the top of that recording's block** — two players
per paper — streaming the existing clip file from `/media/`.

No new infrastructure: the files are already on disk and already served.
Player placement mirrors how the section is actually run (a recording is
played twice to the whole room, not per question), which is why it is one
player per recording rather than one per question.

---

## 7. Downloads — separate files, no ZIP

The ZIP pack is **removed**. Management's stated reason is that a zip is
awkward for teachers; each file becomes its own plain download.

The paper page offers:

| Download | File |
|---|---|
| Test | `G9-A-Student.docx` — no answers, photos embedded inline |
| Answer Key | `G9-A-AnswerKey.docx` — listening/reading/writing answers |
| Speaking Pack | `G9-A-Examiner.docx` — 5 prompts, rubric, mark sheet |
| Audio 1 | the first recording, as its own file |
| Audio 2 | the second recording, as its own file |

**Photos are not downloadable separately.** They exist only embedded inside
the Test document. This is explicit: an earlier draft of this design proposed
a `photos/` folder and it was rejected.

`README.txt` is dropped — it existed to explain the contents of a bundle that
no longer exists. Any administration guidance a teacher needs belongs on the
page itself, which is a display concern, not a deliverable.

`build_pack()` and its zipping logic are deleted. The three document builders
(`student_docx`, `answer_key_docx`, `examiner_docx`) are unchanged in purpose
and are served directly.

### 7.1 Generation tracking

`GenerationEvent.export_format` currently defaults to `"zip"`. It gains
explicit choices — `student`, `answer_key`, `examiner`, `audio_1`, `audio_2` —
so the register records *which* file a teacher pulled, not just that they
pulled something. All values fit the existing `max_length=16`. The two
existing rows carry the historical value `"zip"` and are left as they are.

---

## 8. Testing

- **Allocation**: caps are respected per grade; the rotating clip type is
  evenly distributed across 16 variants; every paper has exactly one picture
  clip; no two variants in a grade share a combination; the function is
  deterministic across repeated calls.
- **Sampling**: cap boundary behaviour, and a clear `SamplingError` when a
  pool genuinely cannot satisfy a cap.
- **Verification**: `check_papers` catches an over-cap state written directly
  to the database, bypassing `clean()` — the independence that makes it worth
  having.
- **Content fixes**: the 7 reassigned reading items keep their answers and
  gain the right subtype; a guard rejects an option-less `mcq`.
- **Rendering**: no `Answer:` string survives for circle-able questions; an
  inline blank appears for write-in questions; a stem that already contains a
  gap marker does **not** gain a second one; 3-option questions render on one
  line; stems are bold.
- **Downloads**: each of the five downloads returns the right content type and
  filename; each records a `GenerationEvent` with the correct `export_format`;
  the closed-generation-window refusal still applies to all five.
- **Manual**: all 100 listening stems eyeballed against source; one rendered
  `.docx` per grade inspected for page count and layout.

Any test touching `ImageField`/`FileField` writes must override `MEDIA_ROOT`
to a temp directory — Django's `TestCase` rollback does not undo file writes,
and this project has been bitten by that before.

---

## 9. Risk: this changes the 12 existing papers

The listening rebalance in §3 means variants B and D of every grade — which
today have no picture clip — get different listening content. Their reading,
writing and speaking may shift too as the allocator is rebuilt.

`GenerationEvent` holds 2 rows, so at least two downloads have occurred.
**Before rebuilding, confirm those were test downloads and that no paper has
been sat by real students.** If any has, the affected variants must be pinned
rather than reallocated, and that becomes a change to this design.
