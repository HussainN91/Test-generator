# English Test Generator — Project Specification

## 1. Overview

An application that generates large numbers of English-language tests for grades 9, 10, and 11, based on the vocabulary and grammar syllabus of the Cambridge "Prepare" book series. Sentences are generated from grammatical *patterns*, not copied from the books — the books supply vocabulary, grammar points, and example sentences that the system generalizes from, so output is effectively unlimited within the grade's scope. Every generated test is tagged as a distinct, traceable variant (Test A, Test B, Test C, ...).

Two priorities drive every design decision below:
1. **Test quality** — varied question types that genuinely assess student knowledge, not just multiple choice.
2. **Marking speed** — every question type must resolve to a fixed, unambiguous model answer a teacher can mark by ticking, so variety never increases grading burden.

A hard constraint during early development: minimal local disk footprint (the developer's dev machine has limited space) — this rules out running a local open-weight LLM even during prototyping. Generation goes through the Claude API. Production deployment targets the user's own VPS, and the deployed app itself has **no LLM dependency at runtime** — see §6.

---

## 2. Inputs (supplied by the user)

| Input | Description |
|---|---|
| Vocabulary lists | Per grade (9/10/11), tagged by unit/theme, sourced from the Prepare books |
| Grammar syllabus | The grammar point(s) taught per unit, per grade |
| Sample sentences | From the Prepare books — used only as **pattern references** for structure, never reused verbatim and never treated as the ceiling of possible output |
| Unit/theme tags | Used to keep generated vocabulary and context thematically coherent within a unit |

---

## 3. Architecture

### 3.1 Content layer
- Vocabulary database: word, part of speech, CEFR level (cross-referenced against the Cambridge English Vocabulary Profile), grade, unit/theme
- Grammar template library: sentence patterns (SV, SVO, SVC, SVOO, SVOC, etc.) mapped to the specific grammar point they realize
- Sample-sentence set: used as few-shot structural references during generation, not as a source pool to copy from

### 3.2 Generation engine (offline pipeline — not part of the deployed app)
- Runs separately from the production system, before deployment or as a standalone refresh step — the live app never calls an LLM
- Claude, called via API (no local model — respects the disk-space constraint)
- Uses the Claude API's native **Structured Outputs** feature: a JSON schema (sentence, target vocabulary word, grammar point, question type, model answer, etc.) is compiled into a grammar that constrains token generation server-side — guaranteeing schema-valid output with no local library required
- Given: the grammar template/constraints for the target unit, the eligible vocabulary pool, and pattern examples
- Instructed explicitly to generalize the pattern to new vocabulary combinations rather than reproduce example sentences
- Sentence type and subject/object type constraints enforced as part of the prompt structure
- **Item bank model**: generation runs once per unit to populate a reviewed item bank; output is imported into the production database — see §3.4

### 3.3 Validation layer (also offline, part of the same pipeline)
- **spaCy** (small English model, ~15MB) — verifies the item actually satisfies its intended constraints: the target grammar point is present, the target vocabulary word appears with the correct part of speech, the sentence matches the intended pattern. (spaCy parses structure; it does not itself judge grammaticality.)
- A second Claude pass reviews each generated item for genuine grammaticality/naturalness — an LLM judges this far better than a parser does
- Optional: human (teacher) review queue for items flagged by either check, or spot-checked before entering the bank
- Only vetted items are imported into the production database — the deployed app never runs unvalidated or freshly-generated content

### 3.4 Assembly & tracking layer
- Local database (SQLite, upgradeable to Postgres later without a rewrite thanks to the ORM) storing a reviewed **item bank** per grade/unit/theme/grammar point/question type, each item tagged with its model answer(s)
- Teacher selects one or more units (multi-select) before generation — assembly filters the bank to the selected unit set
- Test assembly is pure sampling from this bank (no LLM call) — pick N items matching the target unit(s)/tags for each new tagged test (Test A, Test B, Test C, ...)
- **Exclusion scope**: "already used" applies within a single generation batch (the set of variants requested together stays non-overlapping) — not globally across all teachers/time, since a shared multi-teacher bank would otherwise deplete quickly
- This makes test generation itself instant, free, and usable offline; only bank-filling costs API calls, and only once per unit

### 3.5 Question design layer

Six question types for v1, each with a single fixed correct answer (or a short list of acceptable variants) so marking stays tick-based regardless of variety:

| Type | Description | Item bank fields | Marking |
|---|---|---|---|
| Gap-fill (contextual) | One word blanked from a generated sentence | sentence_with_gap, target_word, grammar_point, eligible_word_list_checked (bool) | Single word |
| Word formation | Root word given in brackets, student produces derived form | sentence_with_gap, root_word, correct_form, target_pos | Single word |
| Key word transformation | Rewrite a sentence using a given keyword, meaning preserved | original_sentence, keyword, acceptable_answers (list) | Match against list |
| Error correction | One planted error per sentence | sentence_with_error, error_type, corrected_word_phrase | Single fix |
| Matching | Vocabulary↔definition or sentence-half pairs | item_set (list of pairs) | Pair key |
| Multiple choice | Minority type only — meaning/usage checks | sentence, options (list), correct_option | Single letter |

- **Gap-fill uniqueness constraint**: after generation, the validation layer (§3.3) must check the blank against the full eligible vocabulary set for that unit and reject the item if more than one word fits — this is the hardest correctness requirement in the system and must be enforced at generation/validation time, not left to the teacher to notice
- Mix weighted toward production types (gap-fill, word formation, transformation, error correction) over pure recognition (MCQ, matching), per the priority on genuinely testing knowledge
- **Deferred to v2**: open cloze (needs a function-word vocabulary layer) and sentence reordering (needs scrambled+correct order stored together) — both valuable, both add generation complexity better tackled after the core pipeline is proven

### 3.6 Output layer
- Formatted test export (docx/pdf, later phase)
- Matching answer key generated alongside each test for fast marking

---

## 4. Constraints

- No local LLM; total local library footprint should stay well under ~200MB (spaCy + small model)
- Generated tests must be tagged/traceable individually even at high generation volume
- Marking effort for teachers must stay low regardless of question variety

## 5. Out of scope for this phase

- Open cloze and sentence reordering question types (v2)
- Front-end / UI design
- Export formatting details

---

## 6. Deployment & Multi-User Architecture

- **Users**: multiple teachers, shared tool, hosted on the user's own VPS
- **Stack**: Django (Python) — built-in auth covers multiple teacher accounts; built-in admin panel doubles as the item-review queue from §3.3 with minimal custom UI; ORM handles the database layer
- **No LLM dependency in production**: the deployed app only reads from the item bank database — it never calls the Claude API, holds no API key, and has no runtime dependency on external LLM availability. All generation and review (§3.2–3.3) happens offline, before import
- **Database**: SQLite for v1; swappable to Postgres later if concurrent load requires it
- **Frontend**: server-rendered HTML templates for v1 (no separate JS framework)
- **Roles**:
  - Admin (project owner): triggers per-unit item-bank generation runs, reviews/approves flagged items
  - Teacher: selects grade + unit(s), configures question count and number of variants, generates and exports tests
- **Source materials**: grade 9/10/11 vocabulary-and-grammar guides (20 units each, vocabulary mapped to one grammar focus per unit) are the content source for the vocabulary database and grammar template library in §3.1

## 7. UI/UX Flow

1. **Bank import** (admin view): grade × unit grid showing which units have a populated, reviewed item bank vs. which don't yet; banks arrive via importing the output of the offline generation pipeline (§3.2), not via a live in-app trigger
2. **Test builder** (teacher view): pick grade, check one or more units, set question count and number of variants; default question-type mix pre-selected, with an optional customize toggle
3. **Generate & preview**: instant SQL sampling from the bank; each variant shown with its answer key before export; clear warning if selected units lack enough non-overlapping items for the request
4. **Export**: printable test files plus matching answer keys
