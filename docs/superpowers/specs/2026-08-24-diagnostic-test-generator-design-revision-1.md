# Design Revision 1 — Real Content Bank Discovered

**Date:** 2026-08-24
**Status:** Approved
**Supersedes:** §3 (Content design) and parts of §4 (Architecture) of the original spec, for Reading/Writing/Speaking only. Listening (§3.2, §4.2 listening portions) is untouched.

---

## 0. The workbook is the living source of truth

Everything in this revision treats `Question Bank -Diagnostic Test.xlsx` as the authoritative, evolving content source — not a one-time snapshot to hardcode against. Import tooling must adapt to whatever the workbook actually contains each time it runs (15 reading passages today, 200 writing items today, 50 speaking prompts today — these are today's observed facts, not permanent constants baked into validation logic). The only hard requirement enforced at import time is **sufficiency**: enough content that one grade's 4 variants can be assembled without repeating anything within that grade, per the inviolable rule. If the client's bank grows or changes shape, the system should follow it, not reject it for not matching an earlier count.

## 1. What changed

The original spec's content plan (§3) was built from two sources: `Question Bank -Diagnostic Test - Overall Pattern.csv` (structure/marks/time only) and `Diagnostic_Test_Version_1.docx` (one worked example). Both are, it turns out, extracts from a single larger workbook, `Question Bank -Diagnostic Test.xlsx`, which was not available when the original spec was written. That workbook contains a real, substantial, pre-authored content bank for Reading, Writing, and Speaking. This revision replaces the "author 11 new sets of each from scratch" plan (original §3.3) with a plan built on that real content.

The workbook has 8 tabs:

| Tab | Contents |
|---|---|
| Overall Pattern | Identical to the CSV already known — no new information |
| CEFR Conversion table LRW | Raw-mark → CEFR-level conversion tables, per skill and overall |
| Reading QB with answers | **15 complete reading passages** with questions and answer keys |
| Writing QB with key | **200 writing questions** (50 grammar, 50 vocabulary, 50 jumbled-paragraph, 50 fill-blank) with answer keys |
| Writing sample Question papers | 5 pre-assembled 10-question writing papers, each sampled from the 200-item bank |
| Speaking QB | **50 speaking prompts** across 5 sections of 10, matching the 5 fixed task types |
| Speaking Assessment Rubrics | Detailed marking rubric per speaking task (skill indicators, marks) |
| Listening QB | Empty placeholder — listening content genuinely lives in the separate `.docx`/`.md`/audio files already being used; unaffected by this revision |

## 2. Reading — findings and resolution

**Findings**, verified directly against all 15 passages:

- **Every passage exceeds the client's own stated 150–180 word limit.** Measured range: 203–274 words (Passage 1 — "The School Garden," already known to be 221 — is representative, not an outlier).
- **Question-subtype patterns vary passage to passage.** Three passages (1, 5, 6) use the pattern the original schema assumed (5× TRUE/FALSE/NOT GIVEN, 3× four-option MCQ, 2× completion). The rest vary: passage 2 and 4 open with MCQ instead of TF/NG; passage 3 uses **heading-matching** (match each paragraph to one of six headings); passage 4's second half uses **paragraph-matching** (match a statement to the paragraph it describes); passages 7–15 mostly follow a 3+3+2+2 split (MCQ / TF-NG / completion / a fourth category labeled variously "vocabulary in context," "choose the correct meaning," or "matching").
- **The "fourth category" is not structurally new.** Checked directly: every instance of "vocabulary in context," "choose the correct meaning," and "matching" in this bank is a plain four-option, single-letter-answer question — identical in shape to `mcq`. Only **heading-matching** and **paragraph-matching** are genuinely new answer/option shapes.
- **Answer-key formatting is inconsistent** across passages — three different column layouts observed (`KEY:`/Q/Answer in columns A–C; a bare `Q`/`Answer` header in columns A–B; `Answer Key` followed by numbers in column A and answers in column B). This is the same class of problem already solved once for listening (Task 9's tolerant parser) and needs the same treatment here.

**Resolution** (per user decision — relax to match reality, not trim/restrict):

- `MIN_PASSAGE_WORDS`/`MAX_PASSAGE_WORDS` widen to accommodate the real range with headroom: **150–300** (was 150–180). The client's stated 150–180 was aspirational; their own vetted bank is the actual standard.
- `ReadingSubtype` gains two members: `heading_matching`, `paragraph_matching`.
- The reading validator drops the strict `READING_SUBTYPE_COUNTS` (exact 5+3+2) requirement. Replacement rule: exactly 10 questions, numbered 1–10, each with a subtype from the now five-member `ReadingSubtype` set — no fixed distribution required, since the real bank doesn't have one.
- All 15 real passages are imported as-is, unedited. No trimming, no invention of new content. (This directly reverses the original plan's instruction to trim Version 1's 221-word passage — it now imports unedited like the other 14.)

## 3. Writing — findings and resolution

**Findings:**

- Not 11 new sets to author. A real, complete 200-question bank exists: 50 grammar, 50 vocabulary, 50 jumbled-paragraph, 50 fill-blank, each with an answer key.
- The client has already demonstrated the intended assembly pattern: a "Writing sample Question papers" tab shows **5 papers**, each independently sampling 3 grammar + 2 vocabulary + 3 jumbled + 2 fill-blank (10 questions total) from the 200-item bank — the exact 3/2/3/2 split the original spec derived from Version 1 alone, now confirmed as the real, repeated pattern across 5 independent examples.

**Resolution:**

- `WritingSet` as "one fixed 10-question authored set, one per paper" (original Task 4 model) is retired. Writing becomes a single shared item bank: import all 200 `WritingQuestion` rows once (tagged by subtype), and each `Paper` gets its own **sampled selection** of 10, recorded via a through-table (see §5).
- The existing `WritingQuestion` model (subtype, stem, options, answer) needs no field changes — its shape already matches individual bank items correctly. Only its relationship to `Paper` changes, from "child of one `WritingSet`" to "member of the shared pool, selected per-paper via a join table."

## 4. Speaking — findings and resolution

**Findings:**

- Not 11 new sets to author. A real 50-prompt bank exists, organized into 5 sections of 10 matching the 5 fixed task types (personal introduction, experience, picture/comparison, role play, opinion/discussion) — the same 5 tasks already in `SpeakingTask`.
- A **Speaking Assessment Rubrics** tab gives a detailed marking rubric per task (skill indicators, 2 marks each, totaling 10) — richer than the placeholder "2 marks — examiner judgement" the original render plan assumed.

**Resolution:**

- Same shift as Writing: `SpeakingSet` as "one fixed 5-prompt authored set" is retired in favor of a shared 50-prompt bank, sampled 1-per-section (5 total) per paper via a through-table.
- `SpeakingPrompt`'s shape (task, prompt, bullets, marks) is unchanged — only its relationship to `Paper` changes.
- The rubric content should be imported and surfaced in the examiner export pack (was previously going to be a bare placeholder). Exact storage (a new small model, or a static per-task rubric table keyed by `SpeakingTask`) is left to the implementation task, since the rubric is fixed and shared across all prompts of the same task type, not per-prompt.

## 5. Architecture changes

**`Paper` model** (`diagnostics/models/paper.py`, originally Task 5): `writing_set`/`speaking_set` single foreign keys are replaced with many-to-many relationships through explicit position-tracking join tables — the same pattern the *existing* `assembly` app already uses for `TestVariant`/`TestQuestion` (`bank`/`assembly`, not `diagnostics` — no import, just the same proven pattern reimplemented locally, since `diagnostics` still imports nothing from `bank`/`assembly`):

- `PaperWritingQuestion` (paper FK, writing_question FK, position 1–10)
- `PaperSpeakingPrompt` (paper FK, speaking_prompt FK, position 1–5)

`listening_clip_1`/`listening_clip_2`/`reading_passage` FKs are **unchanged** — listening still picks exactly 2 fixed clips per the allocation table, and reading still picks exactly 1 fixed passage per paper. Only writing/speaking move to the sampled-selection model.

**The within-grade uniqueness rule is unaffected in principle but changes in mechanism for writing/speaking.** It was previously enforced by comparing which `WritingSet`/`SpeakingSet` object a paper pointed to. Under sampling, it must be enforced by comparing the *sets of individual writing-question/speaking-prompt IDs* selected for each paper within a grade — no two of the 4 variants in a grade may share even one sampled item, exactly as the rule already requires for listening clips (item-level, not container-level, comparison). `Paper.clean()` and `check_papers` both need updating for this; the underlying rule and its inviolability are unchanged from the original spec.

**Sampling headroom, checked against the actual rule (within-grade uniqueness only — cross-grade reuse is explicitly fine, so the binding constraint is 4-per-grade against each pool, never a 12-across-all-grades total):**

- **Reading**: 4 distinct passages needed per grade, 15 available. Comfortable.
- **Writing**: worst case 4 × 3 = 12 needed per grade (grammar and jumbled-paragraph, the two subtypes sampled 3 per paper), 50 available per subtype. Comfortable.
- **Speaking**: 4 distinct prompts needed per grade per section (one per variant), 10 available per section. Comfortable.

No pool is remotely tight — unlike listening (20 clips against 24 needed slots, which forced the designed allocation table), reading/writing/speaking all have 2–4× headroom at the per-grade level. **No fixed allocation table is needed for any of the three** — a straightforward random-with-exclusion sampler (same shape as the existing `assembly/services.py` in the sibling app, reimplemented locally since `diagnostics` imports nothing from `assembly`) is sufficient, drawing from "eligible pool minus items already used by other variants in this grade" each time.

## 6. What Task 15 becomes

The original Task 15 ("Author the 33 content sets") is replaced. The new task is primarily an **import task**, not an authoring task:

1. Extract and import all 15 real reading passages (with the tolerant answer-key parser adaptation from §2).
2. Extract and import all 200 writing questions (with their answer key).
3. Extract and import all 50 speaking prompts, plus the assessment rubric.
4. Extract and import the CEFR conversion table (for the answer-key/scoring export, not previously planned at all).
5. No new passages, writing questions, or speaking prompts need to be authored by us. Client review is still required (this is still their content, still needs their sign-off before being trusted for real students) but the review is of *extraction accuracy*, not of *new writing*.

This makes Task 15 much smaller in original-authoring terms and much more like Task 11 (`import_listening`) in shape — an extraction-and-import problem with a tolerant-parser risk, not a creative-writing problem with a review-gate risk. The extraction-accuracy risk (getting 15 passages × 10 questions × answer + 200 writing items + 50 speaking items right) is real and needs the same care Tasks 9/12 gave listening — this is not a lower-stakes task, just a different kind of risk.

## 7. Non-goals of this revision

- No change to the listening pipeline (Tasks 7–12), which is complete, tested, and imported.
- No change to the tracking layer (Task 6).
- No change to the merge-path constraints (original §7).
- Does not revisit the decision to keep `test_type` off `Paper`.
