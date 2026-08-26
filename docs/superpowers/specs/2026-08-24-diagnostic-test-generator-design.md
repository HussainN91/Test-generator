# Diagnostic Test Generator — Design

**Date:** 2026-08-24
**Status:** Approved (design); implementation not started
**Scope:** 12 fixed beginning-of-year diagnostic papers (Grades 9, 10, 11 × 4 variants), delivered and tracked through a Django app.

---

## 1. Overview

Produce **12 pre-authored diagnostic papers** — 4 variants for each of Grades 9, 10 and 11 — and a Django application that lets teachers retrieve their papers and lets admins see who has and has not generated theirs.

This is **not a generative engine**. The 12 papers are built once, offline, by us. Non-repetition is guaranteed at authoring time, not by a runtime algorithm. The deployed app is a catalogue, exporter, and tracker over fixed content.

The diagnostic is a compliance deliverable specified by the client's own pattern document. Mid-term and placement tests are **out of scope** and will be served by the existing unit-based generator, not by this app.

### 1.1 The pattern (fixed, from the client's CSV)

| Skill | Content | Marks | Time |
|---|---|---|---|
| Listening | 2 audio clips × 5 questions | 10 | 10 min |
| Reading | 1 passage (150–180 words) × 10 questions | 10 | 10 min |
| Writing | grammar 3 + vocabulary 2 + jumbled paragraph 3 + fill-in-blanks 2 | 10 | 10 min |
| Speaking | 5 prompts, IELTS/CEFR style | 10 | 10 min |
| **Total** | | **40** | **40 min** |

All sections target **CEFR B1** for every grade. The source pattern specifies no grade-differentiated difficulty; grade determines *which* paper a student sits, not how hard it is.

### 1.2 The inviolable rule

> **The 4 variants within a single grade must share no content whatsoever.**

Cross-grade overlap is permitted as an explicit, authorised fallback where a content pool runs dry. This distinction drives the entire content allocation in §3.

---

## 2. Source materials (verified 2026-08-24)

Located in `D:\Diagnostics Gate`.

| File | Contents | Verified findings |
|---|---|---|
| `Question Bank -Diagnostic Test - Overall Pattern.csv` | The 40-mark pattern above | Authoritative for structure |
| `Listening Question Bank -2026 EC.docx` | 20 worksheets + **25 original JPG images** | Images are **not** in filename order — must walk `r:embed` order in `document.xml` |
| `Listening Question Bank -2026 EC.md` | Same 20 worksheets as text + 25 base64 PNGs | Text intact and easier to parse. **Images are lossy re-renders and Clip 1's are cropped** — they lose the A/B/C label row (624×128 vs. expected 624×193). Do not use `.md` images. |
| `Listening Diagnostic Audio files\` | 20 MP3s, ~68 MB total | Filenames align to clip numbers. Naming is inconsistent (`Audio 1.mp3`, `Audio4.mp3`, `Audio10.mp3`) — the importer must normalise. |
| `Diagnostic_Test_Version_1.docx` | One complete reading + writing + speaking set | The authoring template. Becomes Grade 9 Variant A. |

### 2.1 Listening bank composition

The bank is **perfectly balanced by task type** — 5 clips of each:

| Task type | Clips | Guess floor | Demand |
|---|---|---|---|
| Note/form gap-fill | 3, 7, 11, 18, 19 | 0% | production |
| Picture MCQ (A/B/C) | 1, 5, 9, 13, 15 | 33% | recognition |
| 3-option MCQ | 2, 6, 10, 14, 16 | 33% | recognition |
| True/False (YES/NO) | 4, 8, 12, 17, 20 | 50% | recognition |

Each of the 25 images is a **self-contained A/B/C option strip** (three line drawings with labelled tick boxes) — one image serves one complete question. Verified: document-order image 1 is three plates of food, matching Clip 1 Q1 *"Which dish did Mark cook in the competition?"* (key C). No cropping or compositing is needed at render time.

### 2.2 What the existing item bank does *not* provide

`D:\Test generator` contains a syllabus-unit item bank (736 items). It supplies **effectively none** of this diagnostic, for three reasons:

1. **Composition.** 620 multiple-choice, 107 matching, 9 word-formation, and **zero** gap-fill, key-word-transformation or error-correction — the inverse of what its own spec claims.
2. **Content.** Every one of those MCQs is a vocabulary *definition* item ("Which word means…?"), including items tagged to grammar points. It cannot supply grammar questions.
3. **Pedagogical direction.** Items are tagged to *current-year* Prepare units. A beginning-of-year diagnostic measures what students **arrive with**; sampling Grade 10 Unit 18 for a Grade 10 September diagnostic tests unlearned material.

Additionally all 1110 vocabulary entries have an empty `cefr_level`, so the B1 constraint cannot be enforced against that bank today.

**Conclusion:** the diagnostics app reuses the existing project's *infrastructure*, never its *content*.

---

## 3. Content design

### 3.1 Listening — difficulty-balanced pairing

Pairing the hardest task type with the easiest keeps every paper in a narrow difficulty band rather than ranging from 1.7 to 4.2 out of 10 on guessing alone:

- **Profile X** = gap-fill + True/False → guess floor **2.5/10**
- **Profile Y** = picture MCQ + 3-option MCQ → guess floor **3.3/10**

Every grade receives **2 X-profile and 2 Y-profile papers**, so no grade draws a systematically easier or harder set.

### 3.2 The 12-paper listening allocation

| Grade | Variant A (Y) | Variant B (X) | Variant C (Y) | Variant D (X) |
|---|---|---|---|---|
| **9** | 1 + 2 | 3 + 4 | 5 + 6 | 7 + 8 |
| **10** | 9 + 10 | 11 + 12 | 13 + 14 | 18 + 17 |
| **11** | 15 + 16 | 19 + 20 | **9 + 6** ↺ | **7 + 12** ↺ |

↺ = re-used clips.

Properties:
- All 20 clips are used.
- **Zero repetition within any grade.** Grade 11's eight clips (15, 16, 19, 20, 9, 6, 7, 12) are mutually distinct.
- Grades 9 and 10 are fully fresh. Only Grade 11 re-uses, and only the 4 clips the arithmetic forces (24 slots vs. 20 clips).
- Borrowing is balanced: 2 clips from Grade 9 (6, 7), 2 from Grade 10 (9, 12).
- Re-used clips are **recombined**, never lifted as pairs. Clip 7 sits beside clip 8 in Grade 9 and beside clip 12 in Grade 11, so no whole paper is ever duplicated.

### 3.3 Authored content — 12 distinct sets each

All authored offline, patterned on `Diagnostic_Test_Version_1.docx`, reviewed and approved by the client before being locked in. Version 1 itself becomes Grade 9 Variant A, so **11 new sets of each** are required.

**Reading** — 12 passages, 150–180 words, B1, neutral and age-appropriate. Each with exactly 10 one-mark questions:
- Q1–5: TRUE / FALSE / NOT GIVEN
- Q6–8: four-option multiple choice
- Q9–10: sentence completion, *"NO MORE THAN TWO WORDS from the passage"*

**Writing** — 12 sets of exactly 10 one-mark questions, every item four-option and single-key so marking stays tick-based:
- 3 × grammar (tense/form in context)
- 2 × vocabulary (synonym in context)
- 3 × jumbled paragraph (four sentences A–D, four candidate orderings)
- 2 × fill in the blanks

**Speaking** — 12 sets across 5 fixed task slots, 2 marks each:
1. Personal introduction and familiar topic (30–45 s)
2. Describe an experience or event (four guiding bullets)
3. Topic description and comparison
4. Role play / problem solving
5. Opinion and discussion, with follow-ups

Assessed on logical coherence, relevance, grammar and sentence structure.

**Speaking requires no image assets.** Version 1's Q3 reads *"Describe a picture of students studying in a classroom"* but ships no picture — it is an examiner-read topic prompt, and all 12 sets follow that convention.

**Authoring total:** 11 passages, 11 writing sets, 11 speaking sets = 11 passages + 363 new questions. Listening requires no authoring.

---

## 4. Architecture

### 4.1 Placement

A new `diagnostics` app inside `D:\Test generator`, sibling to `bank` and `assembly`, **importing nothing from either**.

Shared: Django auth, settings, `python-docx` export utilities, admin, deployment. The existing syllabus bank sits dormant beside it — untouched, independently fixable, and still available for the mid-term and placement work.

Rejected alternatives: a fresh standalone project (rebuilds auth/export/deploy and leaves two codebases to merge into Expert Council); generalising `bank`/`assembly` into one engine (rewrites working code to fit a content shape it was never designed for).

### 4.2 Models

**Content layer** — authored once, static. `label` is a short stable identifier used in exports and admin (`R01`–`R12`, `W01`–`W12`, `S01`–`S12`), not display text.

- `AudioClip` — `number` (1–20, unique), `intro_text`, `task_type`, `audio_file`
- `ListeningQuestion` — `clip` FK, `position` (1–5), `stem`, `options` (JSON), `image`, `answer`, `acceptable_answers` (JSON)
- `ReadingPassage` — `label`, `title`, `body`, `word_count`
- `ReadingQuestion` — `passage` FK, `position` (1–10), `subtype` (`true_false_ng` / `mcq` / `completion`), `stem`, `options`, `answer`, `acceptable_answers`
- `WritingSet` — `label`
- `WritingQuestion` — `set` FK, `position` (1–10), `subtype` (`grammar` / `vocabulary` / `jumbled` / `fill_blank`), `stem`, `options`, `answer`
- `SpeakingSet` — `label`
- `SpeakingPrompt` — `set` FK, `position` (1–5), `task_type`, `prompt`, `bullets` (JSON), `marks` (default 2)

**Paper layer** — the 12:

- `Paper` — `grade` (9/10/11), `variant` (A–D), unique together, plus five foreign keys: `listening_clip_1`, `listening_clip_2`, `reading_passage`, `writing_set`, `speaking_set`, and `is_published`.

A paper is five foreign keys. No sampling, no weights, no shortfall handling.

`test_type` is deliberately **omitted**. Mid-term and placement will be served by the existing generator; adding a speculative field for work that will live elsewhere is not justified. If that changes, it is one migration.

**Tracking layer:**

- `TeacherGradeAssignment` — `user` FK, `grade`. Required: without a declared expected set, "who has **not** generated" is unanswerable.
- `GenerationEvent` — `user` FK, `paper` FK, `generated_at`, `format`
- `GenerationWindow` — singleton, `is_open` boolean. The admin open/close toggle, modelled now and wired at merge time.

### 4.3 Enforcing the uniqueness rule

The within-grade rule is enforced in code, not by convention:

- `Paper.clean()` rejects a paper that collides with an existing variant in its grade.
- A `check_papers` management command fails loudly if any two variants within a grade share any of the five components.
- An automated test asserts the rule across all 12 papers, run in CI.

This is the one rule the client called inviolable, so it gets a test rather than a comment.

---

## 5. Flows

**Teacher:** log in → dashboard lists their assigned grades, each showing 4 variants with a generated / not-generated badge → select variant(s) → Generate → download pack. A `GenerationEvent` is recorded.

**Admin:** coverage report (teachers × grades, generated Y/N, variant counts, timestamps), paper preview, content review, generation-window toggle.

---

## 6. Output

One ZIP per paper:

```
G9-VariantA-Student.docx      4 sections, images inline, print-ready, no answers
G9-VariantA-AnswerKey.docx    listening + reading + writing keys, speaking rubric
G9-VariantA-Examiner.docx     5 speaking prompts + rubric + mark sheet
audio/Audio 1.mp3
audio/Audio 2.mp3
README.txt                    administration instructions, 10 minutes per section
```

Built on the existing `assembly/export.py` python-docx patterns.

**No PDF library.** Output is `.docx` plus printable HTML, with browser print-to-PDF for those who want PDF. This honours the original project's minimal-footprint constraint and adds no dependency.

---

## 7. Merge path to Expert Council

Four seams, cheap now and expensive later:

1. Reference `settings.AUTH_USER_MODEL`, never a concrete `User` import.
2. Put teacher → grade resolution behind a **swappable resolver** so Expert Council's roster model can supply it in place of `TeacherGradeAssignment`.
3. Zero imports from `bank` or `content`, verified by a test.
4. Templates extend a single replaceable `base.html`.

Plus `GenerationWindow`, already modelled. With these in place the app moves as a unit.

---

## 8. Build phases

| # | Phase | Output |
|---|---|---|
| 0 | Asset extraction | 20 MP3s normalised, 25 images extracted in **document order**, 20 worksheets parsed to fixtures, **human verification of all 100 listening answers** |
| 1 | App scaffold | `diagnostics` models, admin, migrations |
| 2 | **Content authoring** | 11 reading passages, 11 writing sets, 11 speaking sets — client review gate |
| 3 | Paper assembly | 12 papers as fixtures, uniqueness test passing |
| 4 | Teacher UI + export | working generate-and-download |
| 5 | Admin tracking | coverage report |
| 6 | Merge seams | resolver, window, decoupling test |

Phase 2 is the long pole: 75% of the test content, and the only phase gated on client judgement rather than code.

---

## 9. Risks

| Risk | Detail | Mitigation |
|---|---|---|
| **Answer-key parsing** | The `.md` keys use at least six formatting conventions — `Answers :1** C`, `3A` with no space, `2\. six/6 months3.` with a missing separator, and alternatives like `bakery / baker's`. A naive parser silently mis-assigns answers. | Tolerant parser **plus** a mandatory human verification pass over all 100 answers in Phase 0. Cheap to check, catastrophic to get wrong. |
| **Image ordering** | `.docx` media filenames do not match document order (`image6.jpg` is first). Sorting by filename silently attaches wrong options to picture questions. | Walk `r:embed` order in `document.xml`. Assert 25 images and 25 references. |
| **Audio volume** | ~68 MB across 20 MP3s. | Keep out of version control; ship as a separate asset drop with a documented media path. |
| **Speaking subjectivity** | Free speech cannot be tick-marked, which conflicts with the fast-marking priority. | Ship a real band rubric with the examiner pack — descriptors per mark, not a bare 2-mark slot. |
| **No transcripts** | Teachers cannot verify listening answers by reading; they must trust the key. | Raises the importance of the Phase 0 verification pass. |
| **No version control** | `D:\Test generator` has a `.gitignore` but no `.git`. Nothing is tracked. | Initialise a repository before Phase 1. |

---

## 10. Non-goals

- Runtime test generation, sampling, or randomisation
- Mid-term and placement tests (handled by the existing unit-based generator)
- Online test-taking or auto-marking by students
- Grade-differentiated difficulty (the pattern specifies flat B1)
- Repairing the existing 736-item syllabus bank
- PDF generation libraries
