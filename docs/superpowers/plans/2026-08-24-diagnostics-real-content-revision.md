# Diagnostics Real-Content Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the `diagnostics` app's reading/writing/speaking layer to use the real content bank found in `Question Bank -Diagnostic Test.xlsx` (15 reading passages, 200 writing questions, 50 speaking prompts, a marking rubric, and a CEFR conversion table) instead of the 33-fixed-set authoring plan, per [Design Revision 1](../specs/2026-08-24-diagnostic-test-generator-design-revision-1.md).

**Architecture:** Reading keeps its current shape (`Paper.reading_passage` stays a single FK — pick 1 of 15). Writing and Speaking move from "one fixed `WritingSet`/`SpeakingSet` per paper" to "shared item bank + per-paper sampled selection," via two new through-tables (`PaperWritingQuestion`, `PaperSpeakingPrompt`) mirroring the sibling `assembly` app's `TestVariant`/`TestQuestion` pattern (reimplemented locally — no cross-app import). The reading schema widens (5 subtypes, 150–300 words) to match the real bank instead of the real bank being trimmed to match the schema.

**Tech Stack:** Django 5.2/6.1, `openpyxl` (new dependency — reads the `.xlsx` source), Python 3.14, SQLite, Django `TestCase`.

**Source documents:**
- [Design Revision 1](../specs/2026-08-24-diagnostic-test-generator-design-revision-1.md) — read this first, it has the full rationale
- Original spec: `docs/superpowers/specs/2026-08-24-diagnostic-test-generator-design.md`
- Prior plan (Tasks 1–17): `docs/superpowers/plans/2026-08-24-diagnostics-content-foundation.md` — Tasks 1–12 stand unchanged; this plan replaces Tasks 13–16's reading/writing/speaking portions and Task 15 entirely. Task 17 (`render_paper`) is not started yet and will need a follow-up once this plan lands, since `paper_sections()`/`answer_key()` will need updating for the new writing/speaking relationship shape — noted, not covered here.

---

## The workbook is the living source of truth

The import commands (Tasks 7–9) must adapt to whatever the workbook actually contains, not enforce today's snapshot counts (15 passages, 200 writing items, 50 speaking prompts) as permanent requirements. If the client adds a 16th reading passage next term, `import_reading_bank` must import 16, not fail because it isn't 15. Each command's only hard requirement is **sufficiency for the diagnostic's actual need** — enough that one grade's 4 variants can be built without repeating content within that grade (the inviolable rule's real floor, per the headroom analysis in Design Revision 1 §5) — checked as a minimum, never an exact match.

Test files still assert today's real counts (15/200/50) where they read the live workbook — that's a legitimate characterization test of the actual current file, not a contradiction of the above. If the bank's size changes, those specific test assertions are expected to need updating; the command logic underneath them should not.

## Conventions for this plan

- **Working directory** is always `D:\Test generator`.
- **Python** is `.venv\Scripts\python.exe`.
- **No version control** — no commit steps, by the user's explicit standing decision.
- Source workbook: `D:\Diagnostics Gate\Question Bank -Diagnostic Test.xlsx`, read-only, never modified.
- As of the start of this plan: `diagnostics` has 86 passing tests (Tasks 1–14 of the prior plan). Task 12's human listening sign-off is still pending — unrelated to this plan, do not block on it.

## File structure

| File | Responsibility |
|---|---|
| `diagnostics/constants.py` | Modify: widen `MIN_PASSAGE_WORDS`/`MAX_PASSAGE_WORDS`, drop the fixed `READING_SUBTYPE_COUNTS` requirement concept (keep the constant for reference but stop enforcing it strictly) |
| `diagnostics/models/content.py` | Modify: `ReadingSubtype` gains `heading_matching`, `paragraph_matching` |
| `diagnostics/models/paper.py` | Modify: drop `writing_set`/`speaking_set` FKs; add `PaperWritingQuestion`, `PaperSpeakingPrompt` through-models; update `components()`/`clean()` for item-level uniqueness |
| `diagnostics/authored/schema.py` | Modify: `validate_reading` drops the fixed-count requirement, accepts any of the 5 subtypes; `validate_writing`/`validate_speaking` — scope changes, see Task 4 |
| `diagnostics/extraction/xlsx_reading.py` | Create: extract 15 passages from the `Reading QB with answers` tab |
| `diagnostics/extraction/xlsx_writing.py` | Create: extract 200 questions from the `Writing QB with key` tab |
| `diagnostics/extraction/xlsx_speaking.py` | Create: extract 50 prompts from `Speaking QB` + rubric from `Speaking Assessment Rubrics` |
| `diagnostics/extraction/xlsx_cefr.py` | Create: extract the CEFR conversion table from `CEFR Conversion table LRW` |
| `diagnostics/sampling.py` | Create: the random-with-exclusion sampler shared by writing/speaking assembly |
| `diagnostics/management/commands/import_reading_bank.py` | Create: imports all 15 passages |
| `diagnostics/management/commands/import_writing_bank.py` | Create: imports all 200 writing questions |
| `diagnostics/management/commands/import_speaking_bank.py` | Create: imports all 50 prompts + rubric |
| `diagnostics/management/commands/import_authored.py` | Retire (delete) — superseded by the three commands above; the old fixed-JSON-set format no longer matches how content arrives |
| `diagnostics/tests/*.py` | New/updated test modules per the above |

---

### Task 1: Add `openpyxl` and confirm workbook access

**Files:**
- Modify: `requirements.txt`
- Test: `diagnostics/tests/test_xlsx_access.py`

- [ ] **Step 1: Write the failing test**

Create `diagnostics/tests/test_xlsx_access.py`:

```python
"""Confirms the real content workbook is readable before anything depends on it."""

from django.conf import settings
from django.test import TestCase

WORKBOOK = settings.DIAGNOSTICS_SOURCE_DIR / "Question Bank -Diagnostic Test.xlsx"


class WorkbookAccessTests(TestCase):
    def test_workbook_exists(self):
        self.assertTrue(WORKBOOK.exists(), f"Missing: {WORKBOOK}")

    def test_workbook_has_the_expected_tabs(self):
        import openpyxl

        workbook = openpyxl.load_workbook(WORKBOOK, data_only=True, read_only=True)
        expected = {
            "Overall Pattern", "CEFR Conversion table LRW", "Speaking QB",
            "Reading QB with answers", "Listening QB", "Speaking Assessment Rubrics",
            "Writing QB with key", "Writing sample Question papers ",
        }
        self.assertEqual(set(workbook.sheetnames), expected)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_xlsx_access -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'openpyxl'`

- [ ] **Step 3: Install and pin the dependency**

Run: `.venv\Scripts\python.exe -m pip install openpyxl`

Add to `requirements.txt`:
```
openpyxl>=3.1        # reads the real content workbook (diagnostics content import, offline)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_xlsx_access -v 2`
Expected: PASS, 2 tests

Note the trailing space in `"Writing sample Question papers "` — this is genuinely in the source workbook's sheet name, confirmed by direct inspection. Do not "fix" it; match it exactly or `load_workbook(...)['Writing sample Question papers ']` will `KeyError`.

- [ ] **Step 5: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics`
Expected: OK

---

### Task 2: Widen the reading schema — constants and subtypes

**Files:**
- Modify: `diagnostics/constants.py`, `diagnostics/models/content.py`
- Test: `diagnostics/tests/test_constants.py`, `diagnostics/tests/test_models_authored.py`

- [ ] **Step 1: Update the failing assertions**

In `diagnostics/tests/test_constants.py`, no structural test currently pins `MIN_PASSAGE_WORDS`/`MAX_PASSAGE_WORDS` to specific values (confirm this by reading the file — if a test does pin the old 150/180 values, update it). Add:

```python
class PassageWordBoundsTests(TestCase):
    def test_bounds_cover_the_real_bank_range(self):
        from diagnostics.constants import MAX_PASSAGE_WORDS, MIN_PASSAGE_WORDS
        # Real bank range, verified 2026-08-24: 203-274 words across 15 passages.
        self.assertLessEqual(MIN_PASSAGE_WORDS, 200)
        self.assertGreaterEqual(MAX_PASSAGE_WORDS, 280)
```

In `diagnostics/tests/test_models_authored.py`, update `test_subtypes_are_the_version_one_shape` (it currently asserts exactly 3 subtypes) to:

```python
    def test_subtypes_include_the_real_bank_shapes(self):
        values = {s.value for s in ReadingSubtype}
        self.assertEqual(
            values,
            {"true_false_ng", "mcq", "completion", "heading_matching", "paragraph_matching"},
        )
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_constants diagnostics.tests.test_models_authored -v 2`
Expected: FAIL on the updated assertions

- [ ] **Step 3: Update the constants**

In `diagnostics/constants.py`, change:
```python
MIN_PASSAGE_WORDS = 150
MAX_PASSAGE_WORDS = 180
```
to:
```python
#: Widened 2026-08-24 to match the real content bank (203-274 words across
#: 15 passages) rather than the client's aspirational 150-180 stated pattern
#: — see Design Revision 1, spec section 2.
MIN_PASSAGE_WORDS = 150
MAX_PASSAGE_WORDS = 300
```

- [ ] **Step 4: Update `ReadingSubtype`**

In `diagnostics/models/content.py`, change:
```python
class ReadingSubtype(models.TextChoices):
    TRUE_FALSE_NG = "true_false_ng", "TRUE / FALSE / NOT GIVEN"
    MCQ = "mcq", "Four-option multiple choice"
    COMPLETION = "completion", "Sentence completion (max two words)"
```
to:
```python
class ReadingSubtype(models.TextChoices):
    TRUE_FALSE_NG = "true_false_ng", "TRUE / FALSE / NOT GIVEN"
    MCQ = "mcq", "Four-option multiple choice"
    COMPLETION = "completion", "Sentence completion (max two words)"
    HEADING_MATCHING = "heading_matching", "Match paragraph to heading"
    PARAGRAPH_MATCHING = "paragraph_matching", "Match statement to paragraph"
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_constants diagnostics.tests.test_models_authored -v 2`
Expected: PASS

- [ ] **Step 6: No migration needed**

`ReadingSubtype` is a `CharField(choices=...)`, not an enum-backed DB constraint — adding choices doesn't change the schema. Confirm: `.venv\Scripts\python.exe manage.py makemigrations diagnostics --check --dry-run` should report no changes. If it reports a change, something else drifted — investigate before proceeding.

- [ ] **Step 7: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics`
Expected: OK

---

### Task 3: Relax `validate_reading`'s subtype-count requirement

**Files:**
- Modify: `diagnostics/authored/schema.py`
- Test: `diagnostics/tests/test_authored_schema.py`

- [ ] **Step 1: Update the tests**

In `diagnostics/tests/test_authored_schema.py`, `test_wrong_subtype_distribution_is_rejected` currently asserts a fixed 5+3+2 split is enforced. Replace it — the real bank has no fixed split — with:

```python
    def test_any_mix_of_valid_subtypes_is_accepted(self):
        payload = reading_payload()
        payload["questions"][0]["subtype"] = "mcq"
        payload["questions"][0]["options"] = ["a", "b", "c", "d"]
        payload["questions"][0]["answer"] = "A"
        validate_reading(payload)  # must not raise

    def test_heading_matching_and_paragraph_matching_are_accepted(self):
        payload = reading_payload()
        payload["questions"][0]["subtype"] = "heading_matching"
        payload["questions"][0]["options"] = ["i", "ii", "iii", "iv", "v", "vi"]
        payload["questions"][0]["answer"] = "iii"
        payload["questions"][1]["subtype"] = "paragraph_matching"
        payload["questions"][1]["options"] = []
        payload["questions"][1]["answer"] = "C"
        validate_reading(payload)  # must not raise

    def test_still_requires_exactly_ten_questions(self):
        payload = reading_payload()
        payload["questions"] = payload["questions"][:9]
        with self.assertRaisesMessage(ContentError, "exactly 10"):
            validate_reading(payload)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_authored_schema -v 2`
Expected: FAIL (new tests don't exist as passing behavior yet — `mcq`/`heading_matching`/`paragraph_matching` mixed freely currently trips `_require_subtype_counts`)

- [ ] **Step 3: Update `validate_reading`**

In `diagnostics/authored/schema.py`, change:

```python
def validate_reading(payload):
    label = payload.get("label", "<unlabelled>")
    if "label" not in payload:
        raise ContentError(f"{label}: missing required \"label\" field.")
    word_count = len(payload["body"].split())
    if not MIN_PASSAGE_WORDS <= word_count <= MAX_PASSAGE_WORDS:
        raise ContentError(
            f"{label}: passage must be {MIN_PASSAGE_WORDS}-{MAX_PASSAGE_WORDS} words; "
            f"this one is {word_count}."
        )

    questions = payload["questions"]
    _require_positions(questions, 10, label)
    _require_subtype_counts(questions, READING_SUBTYPE_COUNTS, label)

    for question in questions:
```

to:

```python
VALID_READING_SUBTYPES = {
    "true_false_ng", "mcq", "completion", "heading_matching", "paragraph_matching",
}


def validate_reading(payload):
    """Validate one reading passage + its 10 questions.

    No fixed subtype distribution is enforced — the real content bank mixes
    subtypes freely per passage (see Design Revision 1). Only the total count
    (exactly 10) and each question's subtype membership are checked.
    """
    label = payload.get("label", "<unlabelled>")
    if "label" not in payload:
        raise ContentError(f"{label}: missing required \"label\" field.")
    word_count = len(payload["body"].split())
    if not MIN_PASSAGE_WORDS <= word_count <= MAX_PASSAGE_WORDS:
        raise ContentError(
            f"{label}: passage must be {MIN_PASSAGE_WORDS}-{MAX_PASSAGE_WORDS} words; "
            f"this one is {word_count}."
        )

    questions = payload["questions"]
    _require_positions(questions, 10, label)
    for question in questions:
        if question["subtype"] not in VALID_READING_SUBTYPES:
            raise ContentError(
                f"{label} Q{question['position']}: unknown subtype "
                f"{question['subtype']!r}; must be one of {sorted(VALID_READING_SUBTYPES)}."
            )

    for question in questions:
```

Remove the now-unused `READING_SUBTYPE_COUNTS` import from the top of the file (it's still used elsewhere in `diagnostics/constants.py` — only remove the import in `schema.py` if `validate_reading` no longer references it; check `validate_writing` still needs `WRITING_SUBTYPE_COUNTS` and keep that import).

Leave the per-subtype answer-shape checks (`true_false_ng`/`mcq`/`completion` branches) exactly as they are. Add two new branches for the two new subtypes — minimal validation, since these are real vetted content, not freshly authored:

```python
        elif subtype == "heading_matching":
            if not question["options"]:
                raise ContentError(f"{label} Q{position}: heading_matching needs options.")
            if answer not in question["options"]:
                raise ContentError(
                    f"{label} Q{position}: answer must be one of the given headings."
                )
        elif subtype == "paragraph_matching":
            if not answer:
                raise ContentError(f"{label} Q{position}: paragraph_matching needs an answer.")
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_authored_schema -v 2`
Expected: PASS

- [ ] **Step 5: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics`
Expected: OK (existing `validate_writing`/`validate_speaking` tests untouched by this task — writing/speaking schema changes come in Task 4)

---

### Task 4: Retire fixed-set writing/speaking validation and models

This is the largest structural change in the plan. `WritingSet`/`SpeakingSet` as "one fixed authored set" are replaced by treating `WritingQuestion`/`SpeakingPrompt` as members of one shared pool each, selected per-paper via new through-models built in Task 6.

**Files:**
- Modify: `diagnostics/models/content.py` (drop `WritingSet`, `SpeakingSet`; adjust `WritingQuestion`/`SpeakingPrompt` FKs)
- Modify: `diagnostics/authored/schema.py` (retire `validate_writing`/`validate_speaking` — content now arrives as whole-bank imports, not one-set-at-a-time JSON, so per-set validation no longer applies; individual-item validation moves into the new import commands in Tasks 8–9)
- Test: `diagnostics/tests/test_models_authored.py`, `diagnostics/tests/test_authored_schema.py`

- [ ] **Step 1: Update model tests first**

In `diagnostics/tests/test_models_authored.py`, remove `WritingTests.test_question_belongs_to_a_set` and `SpeakingTests.test_prompt_defaults_to_two_marks`'s dependency on `SpeakingSet` (see below), replacing with:

```python
class WritingTests(TestCase):
    def test_subtypes_match_the_pattern(self):
        self.assertEqual(
            [s.value for s in WritingSubtype],
            ["grammar", "vocabulary", "jumbled", "fill_blank"],
        )

    def test_question_is_a_standalone_bank_item(self):
        question = WritingQuestion.objects.create(
            subtype=WritingSubtype.GRAMMAR,
            stem="Maria ___ to work by bus.", options=["go", "goes", "going", "gone"],
            answer="B",
        )
        self.assertIsNotNone(question.pk)


class SpeakingTests(TestCase):
    def test_five_fixed_task_slots(self):
        self.assertEqual(len(SpeakingTask.choices), 5)

    def test_prompt_defaults_to_two_marks(self):
        prompt = SpeakingPrompt.objects.create(
            task=SpeakingTask.INTRODUCTION, prompt="What is your name?",
        )
        self.assertEqual(prompt.marks, 2)
```

Remove `SpeakingSet`, `WritingSet` from the test file's imports.

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_models_authored -v 2`
Expected: FAIL (models still require `set=`/have no default)

- [ ] **Step 3: Update the models**

In `diagnostics/models/content.py`, delete the `WritingSet` and `SpeakingSet` classes entirely. Change `WritingQuestion`:

```python
class WritingQuestion(models.Model):
    set = models.ForeignKey(WritingSet, on_delete=models.CASCADE, related_name="questions")
    position = models.PositiveSmallIntegerField(validators=_position_validators(10))
    subtype = models.CharField(max_length=16, choices=WritingSubtype.choices)
    stem = models.TextField()
    options = models.JSONField(default=list)
    answer = models.CharField(max_length=8, help_text="Option letter A-D.")

    class Meta:
        ordering = ["set__label", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["set", "position"], name="unique_writing_position"
            )
        ]

    def __str__(self):
        return f"{self.set.label} Q{self.position}"
```

to:

```python
class WritingQuestion(models.Model):
    """One item in the shared 200-question writing bank (Design Revision 1).

    No longer a child of a fixed WritingSet — each Paper selects 10 of these
    via PaperWritingQuestion (diagnostics/models/paper.py).
    """

    subtype = models.CharField(max_length=16, choices=WritingSubtype.choices)
    stem = models.TextField()
    options = models.JSONField(default=list)
    answer = models.CharField(max_length=8, help_text="Option letter A-D.")

    class Meta:
        ordering = ["subtype", "pk"]

    def __str__(self):
        return f"{self.get_subtype_display()}: {self.stem[:40]}"
```

Change `SpeakingPrompt` the same way:

```python
class SpeakingPrompt(models.Model):
    """One item in the shared 50-prompt speaking bank (Design Revision 1).

    No longer a child of a fixed SpeakingSet — each Paper selects 5 of these
    (one per task type) via PaperSpeakingPrompt (diagnostics/models/paper.py).
    """

    task = models.CharField(max_length=16, choices=SpeakingTask.choices)
    prompt = models.TextField()
    bullets = models.JSONField(default=list, blank=True)
    marks = models.PositiveSmallIntegerField(default=2)

    class Meta:
        ordering = ["task", "pk"]

    def __str__(self):
        return f"{self.get_task_display()}: {self.prompt[:40]}"
```

Update `diagnostics/models/__init__.py`: remove `WritingSet`/`SpeakingSet` from both the import and `__all__`.

- [ ] **Step 4: Retire `validate_writing`/`validate_speaking`**

In `diagnostics/authored/schema.py`, delete `validate_writing` and `validate_speaking` entirely (their "one fixed 10-question set" / "one fixed 5-prompt set" contract no longer matches how content arrives — Tasks 8–9 validate individual bank items inline during import instead). Delete now-unused imports (`WRITING_SUBTYPE_COUNTS`, `SPEAKING_TASK_ORDER`) if nothing else in the file uses them — check first with a grep.

In `diagnostics/tests/test_authored_schema.py`, delete `WritingValidationTests` and `SpeakingValidationTests` entirely, and delete the now-unused `writing_payload`/`speaking_payload` factory functions (check `diagnostics/tests/test_import_authored.py` — it imports these factories; Task 5 retires that whole file, so this is safe once Task 5 runs, but do Task 4 and Task 5 in order and don't leave `test_import_authored.py` broken in between within the same work session).

- [ ] **Step 5: Create the migration**

Run: `.venv\Scripts\python.exe manage.py makemigrations diagnostics`

This will prompt interactively about the field/model removal (Django's migration prompt asks whether to provide a default for data loss, since `WritingSet`/`SpeakingSet` deletion cascades). Since no real `WritingSet`/`SpeakingSet` rows exist yet in the database (Task 14 of the prior plan only imported test-fixture data inside test transactions, never real rows — confirm this first: `.venv\Scripts\python.exe manage.py shell -c "from diagnostics.models import WritingSet; print(WritingSet.objects.count())"` should print `0`), this is safe. Run non-interactively with `--no-input` if the prompt blocks: `.venv\Scripts\python.exe manage.py makemigrations diagnostics --no-input`.

Then: `.venv\Scripts\python.exe manage.py migrate`

- [ ] **Step 6: Run to verify pass**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_models_authored diagnostics.tests.test_authored_schema -v 2`
Expected: PASS

- [ ] **Step 7: Checkpoint (expect failures — do not fix yet)**

Run: `.venv\Scripts\python.exe manage.py test diagnostics -v 2`
Expected: FAILURES in `test_import_authored.py` (imports `WritingSet`/`SpeakingSet`, references `validate_writing`/`validate_speaking`) and possibly `test_models_paper.py` (uses `WritingSet`/`SpeakingSet` in its `make_paper` helper). **This is expected and handled by Task 5.** Do not attempt to fix these here — report the exact failing test names so Task 5 knows its starting point.

---

### Task 5: Retire `import_authored`; delete its tests

**Files:**
- Delete: `diagnostics/management/commands/import_authored.py`, `diagnostics/tests/test_import_authored.py`

- [ ] **Step 1: Delete both files**

`import_authored.py`'s whole contract (walk a directory of one-JSON-file-per-fixed-set) no longer matches the content model. It is superseded by three new commands in Tasks 7–9 (`import_reading_bank`, `import_writing_bank`, `import_speaking_bank`), each importing directly from the real `.xlsx` workbook — there is no more "author individual JSON files" step at all.

Delete `diagnostics/management/commands/import_authored.py` and `diagnostics/tests/test_import_authored.py`.

- [ ] **Step 2: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics -v 2`
Expected: The `test_import_authored` failures from Task 4 are gone (the file no longer exists). Remaining failures, if any, should only be in `test_models_paper.py` — confirm and hand off to Task 6.

---

### Task 6: `Paper` model — replace `writing_set`/`speaking_set` with sampled-selection through-models

**Files:**
- Modify: `diagnostics/models/paper.py`
- Test: `diagnostics/tests/test_models_paper.py`

- [ ] **Step 1: Update the test file**

Read the current `diagnostics/tests/test_models_paper.py` in full first — it currently builds `Paper` instances via a `make_paper` helper that creates `WritingSet`/`SpeakingSet` objects and passes them as `writing_set=`/`speaking_set=` kwargs. Replace the whole file:

```python
from django.core.exceptions import ValidationError
from django.test import TestCase

from diagnostics.constants import TaskType
from diagnostics.models import (
    AudioClip, Paper, PaperSpeakingPrompt, PaperWritingQuestion,
    ReadingPassage, SpeakingPrompt, SpeakingTask, WritingQuestion, WritingSubtype,
)


def make_writing_questions(n, suffix):
    return [
        WritingQuestion.objects.create(
            subtype=WritingSubtype.GRAMMAR, stem=f"stem-{suffix}-{i}",
            options=["a", "b", "c", "d"], answer="A",
        )
        for i in range(n)
    ]


def make_speaking_prompts(suffix):
    return [
        SpeakingPrompt.objects.create(task=task, prompt=f"prompt-{suffix}-{task}")
        for task in SpeakingTask.values
    ]


def make_paper(grade, variant, clip_a, clip_b, suffix, writing_questions=None, speaking_prompts=None):
    paper = Paper.objects.create(
        grade=grade,
        variant=variant,
        listening_clip_1=clip_a,
        listening_clip_2=clip_b,
        reading_passage=ReadingPassage.objects.create(
            label=f"R{suffix}", title="T", body=" ".join(["word"] * 220)
        ),
    )
    for position, question in enumerate(writing_questions or [], start=1):
        PaperWritingQuestion.objects.create(paper=paper, question=question, position=position)
    for position, prompt in enumerate(speaking_prompts or [], start=1):
        PaperSpeakingPrompt.objects.create(paper=paper, prompt=prompt, position=position)
    return paper


class PaperUniquenessTests(TestCase):
    def setUp(self):
        self.clips = {
            n: AudioClip.objects.create(number=n, task_type=TaskType.MCQ3)
            for n in range(1, 9)
        }

    def test_valid_paper_saves(self):
        paper = make_paper(9, "A", self.clips[1], self.clips[2], "01")
        paper.full_clean()
        self.assertEqual(Paper.objects.count(), 1)

    def test_a_paper_cannot_use_the_same_clip_twice(self):
        paper = Paper(
            grade=9, variant="A",
            listening_clip_1=self.clips[1], listening_clip_2=self.clips[1],
            reading_passage=ReadingPassage.objects.create(
                label="R01", title="T", body=" ".join(["word"] * 220)
            ),
        )
        with self.assertRaises(ValidationError) as ctx:
            paper.full_clean()
        self.assertIn("twice", str(ctx.exception))

    def test_clip_reuse_within_a_grade_is_rejected(self):
        make_paper(9, "A", self.clips[1], self.clips[2], "01")
        clash = Paper(
            grade=9, variant="B",
            listening_clip_1=self.clips[2], listening_clip_2=self.clips[3],
            reading_passage=ReadingPassage.objects.create(
                label="R02", title="T", body=" ".join(["word"] * 220)
            ),
        )
        with self.assertRaises(ValidationError) as ctx:
            clash.full_clean()
        self.assertIn("Grade 9", str(ctx.exception))

    def test_clip_reuse_across_grades_is_allowed(self):
        make_paper(9, "A", self.clips[1], self.clips[2], "01")
        other = Paper(
            grade=11, variant="C",
            listening_clip_1=self.clips[2], listening_clip_2=self.clips[3],
            reading_passage=ReadingPassage.objects.create(
                label="R02", title="T", body=" ".join(["word"] * 220)
            ),
        )
        other.full_clean()
        other.save()
        self.assertEqual(Paper.objects.count(), 2)

    def test_reading_passage_reuse_within_a_grade_is_rejected(self):
        first = make_paper(9, "A", self.clips[1], self.clips[2], "01")
        clash = Paper(
            grade=9, variant="B",
            listening_clip_1=self.clips[3], listening_clip_2=self.clips[4],
            reading_passage=first.reading_passage,
        )
        with self.assertRaises(ValidationError) as ctx:
            clash.full_clean()
        self.assertIn("Grade 9", str(ctx.exception))

    def test_shared_writing_question_within_a_grade_is_rejected(self):
        questions = make_writing_questions(2, "shared")
        make_paper(9, "A", self.clips[1], self.clips[2], "01", writing_questions=questions[:1])
        clash = make_paper(9, "B", self.clips[3], self.clips[4], "02")
        PaperWritingQuestion.objects.create(paper=clash, question=questions[0], position=1)
        with self.assertRaises(ValidationError) as ctx:
            clash.full_clean()
        self.assertIn("Grade 9", str(ctx.exception))

    def test_shared_writing_question_across_grades_is_allowed(self):
        questions = make_writing_questions(1, "cross-grade")
        make_paper(9, "A", self.clips[1], self.clips[2], "01", writing_questions=questions)
        other = make_paper(11, "A", self.clips[3], self.clips[4], "02")
        PaperWritingQuestion.objects.create(paper=other, question=questions[0], position=1)
        other.full_clean()  # must not raise

    def test_shared_speaking_prompt_within_a_grade_is_rejected(self):
        prompts = make_speaking_prompts("shared")
        make_paper(9, "A", self.clips[1], self.clips[2], "01", speaking_prompts=prompts)
        clash = make_paper(9, "B", self.clips[3], self.clips[4], "02")
        PaperSpeakingPrompt.objects.create(paper=clash, prompt=prompts[0], position=1)
        with self.assertRaises(ValidationError) as ctx:
            clash.full_clean()
        self.assertIn("Grade 9", str(ctx.exception))

    def test_str_is_the_paper_code(self):
        paper = make_paper(10, "C", self.clips[1], self.clips[2], "01")
        self.assertEqual(str(paper), "G10-C")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_models_paper -v 2`
Expected: FAIL — `ImportError: cannot import name 'PaperWritingQuestion'`

- [ ] **Step 3: Rewrite `paper.py`**

Replace `diagnostics/models/paper.py` in full:

```python
"""The twelve fixed diagnostic papers (spec 4.2, paper layer; Design Revision 1).

Listening (2 clips) and Reading (1 passage) are still single foreign keys —
each paper picks exactly one fixed component. Writing and Speaking moved to a
shared-bank-plus-sampled-selection model (Design Revision 1 section 5): each
paper picks 10 WritingQuestion rows and 5 SpeakingPrompt rows out of a shared
pool, recorded via PaperWritingQuestion/PaperSpeakingPrompt.

clean() enforces the one rule the client called inviolable — the four
variants within a grade share nothing, now checked at the level of individual
sampled items for writing/speaking, not just at the container level.
"""

from django.core.exceptions import ValidationError
from django.db import models

from diagnostics.constants import GRADES, VARIANTS
from diagnostics.models.content import (
    AudioClip, ReadingPassage, SpeakingPrompt, WritingQuestion,
)


class Paper(models.Model):
    grade = models.PositiveSmallIntegerField(choices=[(g, f"Grade {g}") for g in GRADES])
    variant = models.CharField(max_length=1, choices=[(v, v) for v in VARIANTS])

    listening_clip_1 = models.ForeignKey(
        AudioClip, on_delete=models.PROTECT, related_name="papers_as_first"
    )
    listening_clip_2 = models.ForeignKey(
        AudioClip, on_delete=models.PROTECT, related_name="papers_as_second"
    )
    reading_passage = models.ForeignKey(
        ReadingPassage, on_delete=models.PROTECT, related_name="papers"
    )
    writing_questions = models.ManyToManyField(
        WritingQuestion, through="PaperWritingQuestion", related_name="papers"
    )
    speaking_prompts = models.ManyToManyField(
        SpeakingPrompt, through="PaperSpeakingPrompt", related_name="papers"
    )

    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ["grade", "variant"]
        constraints = [
            models.UniqueConstraint(fields=["grade", "variant"], name="unique_grade_variant")
        ]

    def __str__(self):
        return f"G{self.grade}-{self.variant}"

    def shared_components(self):
        """Every component this paper occupies that must not repeat within its
        grade, as (label, pk) pairs. Listening clips and the reading passage
        are single objects; writing/speaking are sets of sampled item pks."""
        pairs = []
        if self.listening_clip_1_id:
            pairs.append(("listening clip", self.listening_clip_1_id))
        if self.listening_clip_2_id:
            pairs.append(("listening clip", self.listening_clip_2_id))
        if self.reading_passage_id:
            pairs.append(("reading passage", self.reading_passage_id))
        if self.pk:
            pairs += [
                ("writing question", pk)
                for pk in self.writing_questions.values_list("pk", flat=True)
            ]
            pairs += [
                ("speaking prompt", pk)
                for pk in self.speaking_prompts.values_list("pk", flat=True)
            ]
        return pairs

    def clean(self):
        if self.listening_clip_1_id and self.listening_clip_1_id == self.listening_clip_2_id:
            raise ValidationError(
                {"listening_clip_2": "A paper cannot use the same clip twice."}
            )

        mine = set(self.shared_components())
        siblings = Paper.objects.filter(grade=self.grade).exclude(pk=self.pk)
        for sibling in siblings:
            clash = mine & set(sibling.shared_components())
            if clash:
                label = sorted(clash)[0][0]
                raise ValidationError(
                    f"Grade {self.grade} variant {sibling.variant} already uses this "
                    f"{label}. The four variants in a grade must share nothing."
                )


class PaperWritingQuestion(models.Model):
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="writing_slots")
    question = models.ForeignKey(WritingQuestion, on_delete=models.PROTECT)
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["paper", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["paper", "position"], name="unique_paper_writing_position"
            ),
            models.UniqueConstraint(
                fields=["paper", "question"], name="unique_paper_writing_question"
            ),
        ]


class PaperSpeakingPrompt(models.Model):
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="speaking_slots")
    prompt = models.ForeignKey(SpeakingPrompt, on_delete=models.PROTECT)
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["paper", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["paper", "position"], name="unique_paper_speaking_position"
            ),
            models.UniqueConstraint(
                fields=["paper", "prompt"], name="unique_paper_speaking_prompt"
            ),
        ]
```

Note the change from `SHARED_COMPONENT_FIELDS`/`components()` (a fixed list of FK field names) to `shared_components()` (dynamically includes the M2M-sampled items). Anything downstream that imported `SHARED_COMPONENT_FIELDS` (the prior plan's Task 16 `check_papers`, not yet built) will need `shared_components()` instead — noted for Task 10 of this plan.

Update `diagnostics/models/__init__.py`: replace the `Paper`/`SHARED_COMPONENT_FIELDS` import line with:
```python
from diagnostics.models.paper import Paper, PaperSpeakingPrompt, PaperWritingQuestion

__all__ += ["Paper", "PaperSpeakingPrompt", "PaperWritingQuestion"]
```

- [ ] **Step 4: Create the migration**

Run: `.venv\Scripts\python.exe manage.py makemigrations diagnostics`
Expected: creates `PaperWritingQuestion`, `PaperSpeakingPrompt`, alters `Paper` (removes `writing_set`/`speaking_set` FKs, adds the two M2M-through relations)

Then: `.venv\Scripts\python.exe manage.py migrate`

- [ ] **Step 5: Run to verify pass**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_models_paper -v 2`
Expected: PASS, 9 tests

- [ ] **Step 6: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics -v 2`
Expected: OK — this should be the first fully-green run since Task 4 started. If anything outside `test_models_paper.py`/`test_import_authored.py` (already deleted) is still failing, investigate before proceeding — nothing else in the plan should have touched other test files.

---

### Task 7: Extract and import the 15 reading passages

**Files:**
- Create: `diagnostics/extraction/xlsx_reading.py`, `diagnostics/management/commands/import_reading_bank.py`
- Test: `diagnostics/tests/test_xlsx_reading.py`, `diagnostics/tests/test_import_reading_bank.py`

- [ ] **Step 1: Write the extraction test**

Create `diagnostics/tests/test_xlsx_reading.py`:

```python
from django.conf import settings
from django.test import TestCase

from diagnostics.extraction.xlsx_reading import extract_passages

WORKBOOK = settings.DIAGNOSTICS_SOURCE_DIR / "Question Bank -Diagnostic Test.xlsx"


class ExtractPassagesTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not WORKBOOK.exists():
            raise AssertionError(f"Source file missing: {WORKBOOK}")
        cls.passages = extract_passages(WORKBOOK)

    def test_finds_fifteen_passages(self):
        self.assertEqual(len(self.passages), 15)

    def test_every_passage_has_ten_questions(self):
        for passage in self.passages:
            self.assertEqual(len(passage["questions"]), 10, passage["title"])

    def test_every_passage_body_is_within_the_widened_bounds(self):
        from diagnostics.constants import MAX_PASSAGE_WORDS, MIN_PASSAGE_WORDS

        for passage in self.passages:
            count = len(passage["body"].split())
            self.assertTrue(
                MIN_PASSAGE_WORDS <= count <= MAX_PASSAGE_WORDS,
                f"{passage['title']}: {count} words",
            )

    def test_known_passage_one_matches_the_verified_content(self):
        passage = self.passages[0]
        self.assertEqual(passage["title"], "The School Garden")
        self.assertEqual(passage["questions"][0]["subtype"], "true_false_ng")
        self.assertEqual(passage["questions"][0]["answer"], "FALSE")
        self.assertEqual(passage["questions"][8]["answer"], "height")

    def test_heading_matching_passage_is_recognised(self):
        heading_passage = next(
            p for p in self.passages if p["title"] == "Why Some Cities Are Becoming Greener"
        )
        self.assertEqual(heading_passage["questions"][0]["subtype"], "heading_matching")
        self.assertEqual(heading_passage["questions"][0]["answer"], "iii")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_xlsx_reading -v 2`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the extractor**

Create `diagnostics/extraction/xlsx_reading.py`:

```python
"""Extract the 15 reading passages from the real content workbook.

Source: 'Reading QB with answers' tab in Question Bank -Diagnostic Test.xlsx.
Answer-key layout is NOT consistent across passages (at least three column
arrangements observed — verified 2026-08-24) so the key parser is tolerant,
matching by scanning for numbered rows near a 'Key'/'Answer' marker rather
than assuming one fixed layout.
"""

import re

import openpyxl

PASSAGE_HEADER_RE = re.compile(r"^READING PASSAGE[\s\-]*(\d+)", re.IGNORECASE)
QUESTIONS_MARKER_RE = re.compile(r"^Questions?\s+[\d\u2013\u2014-]+", re.IGNORECASE)
KEY_MARKER_RE = re.compile(r"key", re.IGNORECASE)
OPTION_LINE_RE = re.compile(r"^([A-D])[.)]\s*(.+)$")
NUMBERED_QUESTION_RE = re.compile(r"^(\d{1,2})[.)]\s*(.+)$")

SUBTYPE_HINTS = [
    (re.compile(r"heading", re.IGNORECASE), "heading_matching"),
    (re.compile(r"paragraph\s*[A-E\u2013\u2014-]", re.IGNORECASE), "paragraph_matching"),
    (re.compile(r"true.*false|not given", re.IGNORECASE), "true_false_ng"),
    (re.compile(r"complete|sentence completion|fill", re.IGNORECASE), "completion"),
]


def _guess_subtype(instruction_text):
    for pattern, subtype in SUBTYPE_HINTS:
        if pattern.search(instruction_text):
            return subtype
    return "mcq"  # multiple choice, "matching" (4-option), vocabulary-in-context all share this shape


def _sheet_rows(workbook):
    sheet = workbook["Reading QB with answers"]
    for row in sheet.iter_rows(values_only=False):
        yield [cell.value for cell in row[:4]]


def extract_passages(path):
    """Return a list of 15 dicts: {title, body, questions: [...]}."""
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    rows = list(_sheet_rows(workbook))

    boundaries = [
        i for i, row in enumerate(rows)
        if row[0] and isinstance(row[0], str) and PASSAGE_HEADER_RE.match(row[0])
    ]
    boundaries.append(len(rows))

    passages = []
    for start, end in zip(boundaries, boundaries[1:]):
        passages.append(_parse_one_passage(rows[start:end]))
    return passages


def _parse_one_passage(block):
    title = next(
        (row[0] for row in block[1:6] if row[0] and isinstance(row[0], str)), None
    )

    # Body: every string cell in column A between the title and the first
    # 'Questions N...' marker, skipping blank rows.
    body_lines = []
    questions_start = None
    started = False
    for i, row in enumerate(block):
        text = row[0]
        if isinstance(text, str) and text.strip() == (title or "").strip():
            started = True
            continue
        if not started:
            continue
        if isinstance(text, str) and QUESTIONS_MARKER_RE.match(text.strip()):
            questions_start = i
            break
        if isinstance(text, str) and text.strip() and not PASSAGE_HEADER_RE.match(text):
            body_lines.append(text.strip())
    body = " ".join(body_lines)

    questions = _parse_questions(block[questions_start:] if questions_start else [])
    answers = _parse_answer_key(block)
    for question in questions:
        question["answer"] = answers.get(question["position"], question.get("answer", ""))

    return {"title": title, "body": body, "questions": questions}


def _parse_questions(rows):
    questions = []
    current_subtype = "mcq"
    current_options = []
    pending = None

    for row in rows:
        text = row[0]
        if not isinstance(text, str) or not text.strip():
            continue
        text = text.strip()

        if QUESTIONS_MARKER_RE.match(text):
            current_subtype = _guess_subtype(text)
            continue

        option_match = OPTION_LINE_RE.match(text)
        if option_match and pending is not None:
            current_options.append(option_match.group(2))
            continue

        number_match = NUMBERED_QUESTION_RE.match(text)
        if number_match:
            if pending is not None:
                pending["options"] = current_options
                questions.append(pending)
            position = int(number_match.group(1))
            if position > 10:
                pending = None
                continue
            pending = {
                "position": position, "subtype": current_subtype,
                "stem": number_match.group(2), "options": [], "answer": "",
            }
            current_options = []

    if pending is not None:
        pending["options"] = current_options
        questions.append(pending)

    return sorted(questions, key=lambda q: q["position"])


def _parse_answer_key(block):
    key_start = next(
        (i for i, row in enumerate(block)
         if isinstance(row[0], str) and KEY_MARKER_RE.search(row[0]) and len(row[0]) < 20),
        None,
    )
    if key_start is None:
        return {}

    answers = {}
    for row in block[key_start:]:
        cells = [c for c in row if c is not None]
        numeric = [c for c in cells if isinstance(c, (int, float))]
        rest = [c for c in cells if not isinstance(c, (int, float))]
        if len(numeric) == 1 and rest:
            position = int(numeric[0])
            if 1 <= position <= 10:
                value = rest[0]
                answers[position] = "TRUE" if value is True else "FALSE" if value is False else str(value)
    return answers
```

**This extractor is a best-effort heuristic against genuinely inconsistent real-world formatting** — unlike Task 9's listening-key parser (which had exactly six known, enumerated formats), the reading bank's variety wasn't fully catalogued question-by-question before this plan was written. Expect the test suite to reveal gaps. If a test fails because a specific passage doesn't parse correctly, **read that passage's actual raw rows directly** (same technique used during the discovery investigation — `openpyxl.load_workbook(..., data_only=True)` then `ws.iter_rows(values_only=True)` over that passage's row range) and adjust the extractor's heuristics to handle the real pattern found, rather than special-casing around a hypothetical. Report exactly which passages needed extra handling.

- [ ] **Step 4: Run and fix until green**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_xlsx_reading -v 2`

Iterate: this is the step most likely to need real debugging against real data. Expected outcome: PASS, 5 tests — but budget real time for this, and validate final output by eye (print all 15 passages' titles, word counts, and first two answers) before moving on, not just by test-green.

- [ ] **Step 5: Write the import command test**

Create `diagnostics/tests/test_import_reading_bank.py`:

```python
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diagnostics.models import ReadingPassage, ReadingQuestion


class ImportReadingBankTests(TestCase):
    def test_imports_fifteen_passages_and_one_hundred_fifty_questions(self):
        call_command("import_reading_bank", stdout=StringIO())
        self.assertEqual(ReadingPassage.objects.count(), 15)
        self.assertEqual(ReadingQuestion.objects.count(), 150)

    def test_idempotent(self):
        call_command("import_reading_bank", stdout=StringIO())
        call_command("import_reading_bank", stdout=StringIO())
        self.assertEqual(ReadingPassage.objects.count(), 15)
```

- [ ] **Step 6: Write the import command**

Create `diagnostics/management/commands/import_reading_bank.py`:

```python
"""Import the real 15-passage reading bank from the client's workbook."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from diagnostics.extraction.xlsx_reading import extract_passages
from diagnostics.models import ReadingPassage, ReadingQuestion

WORKBOOK_NAME = "Question Bank -Diagnostic Test.xlsx"


class Command(BaseCommand):
    help = "Import the real reading passage bank."

    def handle(self, *args, **options):
        path = settings.DIAGNOSTICS_SOURCE_DIR / WORKBOOK_NAME
        if not path.exists():
            raise CommandError(f"Missing source file: {path}")

        passages = extract_passages(path)
        # The bank is the living source of truth: import whatever it holds,
        # and only object if there isn't enough for 4 non-overlapping
        # passages within a single grade (the inviolable rule's floor) — not
        # if the count differs from a snapshot taken on any particular day.
        if len(passages) < 4:
            raise CommandError(
                f"Need at least 4 reading passages (one grade's worth of "
                f"non-overlapping variants), only found {len(passages)}."
            )

        with transaction.atomic():
            for index, data in enumerate(passages, start=1):
                label = f"R{index:02d}"
                passage, _ = ReadingPassage.objects.update_or_create(
                    label=label,
                    defaults={"title": data["title"] or label, "body": data["body"]},
                )
                passage.questions.all().delete()
                for question in data["questions"]:
                    ReadingQuestion.objects.create(
                        passage=passage,
                        position=question["position"],
                        subtype=question["subtype"],
                        stem=question["stem"],
                        options=question["options"],
                        answer=question["answer"],
                    )

        self.stdout.write(self.style.SUCCESS(
            f"Imported {ReadingPassage.objects.count()} passages, "
            f"{ReadingQuestion.objects.count()} questions."
        ))
```

- [ ] **Step 7: Run to verify pass**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_import_reading_bank -v 2`
Expected: PASS, 2 tests

- [ ] **Step 8: Import into the real database and manually spot-check**

Run: `.venv\Scripts\python.exe manage.py import_reading_bank`
Expected: `Imported 15 passages, 150 questions.`

Then spot-check by hand (not just tests): `.venv\Scripts\python.exe manage.py shell` and print 3 passages' full question/answer sets, comparing against the raw workbook rows for the same passages. This extraction has no prior art to lean on (unlike listening's well-catalogued 6 formats) — treat the first real import as something to actually read, not just trust because tests pass.

- [ ] **Step 9: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics`
Expected: OK

---

### Task 8: Extract and import the 200-question writing bank

**Files:**
- Create: `diagnostics/extraction/xlsx_writing.py`, `diagnostics/management/commands/import_writing_bank.py`
- Test: `diagnostics/tests/test_xlsx_writing.py`, `diagnostics/tests/test_import_writing_bank.py`

- [ ] **Step 1: Write the extraction test**

Create `diagnostics/tests/test_xlsx_writing.py`:

```python
from django.conf import settings
from django.test import TestCase

from diagnostics.extraction.xlsx_writing import extract_writing_items

WORKBOOK = settings.DIAGNOSTICS_SOURCE_DIR / "Question Bank -Diagnostic Test.xlsx"


class ExtractWritingItemsTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not WORKBOOK.exists():
            raise AssertionError(f"Source file missing: {WORKBOOK}")
        cls.items = extract_writing_items(WORKBOOK)

    def test_two_hundred_items_total(self):
        self.assertEqual(len(self.items), 200)

    def test_fifty_of_each_subtype(self):
        from collections import Counter

        counts = Counter(item["subtype"] for item in self.items)
        self.assertEqual(
            counts,
            Counter({"grammar": 50, "vocabulary": 50, "jumbled": 50, "fill_blank": 50}),
        )

    def test_every_item_has_four_options_and_a_letter_answer(self):
        for item in self.items:
            self.assertEqual(len(item["options"]), 4, item["stem"])
            self.assertIn(item["answer"], {"A", "B", "C", "D"}, item["stem"])

    def test_known_first_grammar_item(self):
        first = next(i for i in self.items if i["subtype"] == "grammar")
        self.assertIn("Maria", first["stem"])
        self.assertEqual(first["answer"], "B")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_xlsx_writing -v 2`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the extractor**

Create `diagnostics/extraction/xlsx_writing.py`:

```python
"""Extract the 200-question writing bank from the real content workbook.

Source: 'Writing QB with key' tab. Layout, verified 2026-08-24: four labelled
sections (A. GRAMMAR, B. VOCABULARY, C. JUMBLED PARAGRAPHS, D. FILL IN THE
BLANKS), 50 questions each, each question as one 'N. stem' row followed by
one 'A) opt B) opt C) opt D) opt' row. Jumbled-paragraph stems are the four
sentences themselves; the 'stem' field stores them newline-joined verbatim.
The answer key is a separate block near the end of the sheet, grouped by
section and numbered 1-200 (grammar 1-50, vocabulary 51-100, etc.), which
this extractor maps back onto each section's local 1-50 numbering.
"""

import re

import openpyxl

SECTION_HEADER_RE = re.compile(
    r"^([A-D])\.\s*(GRAMMAR|VOCABULARY|JUMBLED PARAGRAPHS|FILL IN THE BLANKS)", re.IGNORECASE
)
QUESTION_LINE_RE = re.compile(r"^(\d{1,3})\.\s*(.+)$")
OPTIONS_LINE_RE = re.compile(
    r"A\)\s*(.+?)\s*B\)\s*(.+?)\s*C\)\s*(.+?)\s*D\)\s*(.+?)$"
)
ANSWER_LINE_RE = re.compile(r"Answer:\s*([A-D](?:-[A-D]){0,3})", re.IGNORECASE)
KEY_RANGE_RE = re.compile(r"(\d+)\D+(\d+)")

SECTION_TO_SUBTYPE = {
    "GRAMMAR": "grammar", "VOCABULARY": "vocabulary",
    "JUMBLED PARAGRAPHS": "jumbled", "FILL IN THE BLANKS": "fill_blank",
}


def extract_writing_items(path):
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    sheet = workbook["Writing QB with key"]
    rows = [
        [cell.value for cell in row[:1]][0]
        for row in sheet.iter_rows(values_only=False)
    ]

    section_bounds = []
    for i, text in enumerate(rows):
        if isinstance(text, str):
            match = SECTION_HEADER_RE.match(text.strip())
            if match:
                section_bounds.append((i, SECTION_TO_SUBTYPE[match.group(2).upper()]))
    section_bounds.append((len(rows), None))

    items_by_subtype = {}
    for (start, subtype), (end, _) in zip(section_bounds, section_bounds[1:]):
        items_by_subtype[subtype] = _parse_section(rows[start:end], subtype)

    key_by_number = _parse_master_key(rows)
    all_items = []
    offset = 0
    for subtype in ("grammar", "vocabulary", "jumbled", "fill_blank"):
        for local_number, item in enumerate(items_by_subtype[subtype], start=1):
            global_number = offset + local_number
            if global_number in key_by_number:
                item["answer"] = key_by_number[global_number]
            all_items.append(item)
        offset += 50
    return all_items


def _parse_section(rows, subtype):
    items = []
    pending_stem_lines = []
    pending_number = None

    for text in rows:
        if not isinstance(text, str) or not text.strip():
            continue
        text = text.strip()

        options_match = OPTIONS_LINE_RE.search(text)
        if options_match and pending_number is not None:
            items.append({
                "subtype": subtype,
                "stem": "\n".join(pending_stem_lines).strip(),
                "options": list(options_match.groups()),
                "answer": "",
            })
            pending_number = None
            pending_stem_lines = []
            continue

        answer_match = ANSWER_LINE_RE.search(text)
        if answer_match and subtype == "jumbled" and items:
            items[-1]["answer"] = answer_match.group(1)
            continue

        question_match = QUESTION_LINE_RE.match(text)
        if question_match:
            pending_number = int(question_match.group(1))
            pending_stem_lines = [question_match.group(2)]
            continue

        if pending_number is not None:
            pending_stem_lines.append(text)

    return items


def _parse_master_key(rows):
    """The answer-key block at the end of the sheet: 'A. Grammar - 1-50' style
    section headers followed by 50 numbered answer rows each."""
    key_by_number = {}
    in_key_section = False
    current_offset = None

    for text in rows:
        if not isinstance(text, str):
            continue
        stripped = text.strip()
        if not in_key_section and "answer key" in stripped.lower():
            in_key_section = True
            continue
        if not in_key_section:
            continue

        range_match = KEY_RANGE_RE.search(stripped)
        if range_match and any(
            word in stripped.lower()
            for word in ("grammar", "vocabulary", "jumbled", "fill")
        ):
            current_offset = int(range_match.group(1)) - 1
            continue

        numbered = re.match(r"^(\d{1,3})[.):]?\s*(.+)$", stripped)
        if numbered and current_offset is not None:
            key_by_number[int(numbered.group(1))] = numbered.group(2).strip()

    return key_by_number
```

**Same caveat as Task 7**: this is a best-effort extractor against real, organically-formatted data. Iterate against actual test failures by reading the real rows directly, not by guessing.

- [ ] **Step 4: Run and fix until green**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_xlsx_writing -v 2`

Iterate as needed. Once passing, additionally spot-check by hand: print 5 items per subtype and manually compare 2-3 against the raw workbook to confirm the stem/options/answer alignment is genuinely correct, not just internally consistent.

- [ ] **Step 5: Write the import command test**

Create `diagnostics/tests/test_import_writing_bank.py`:

```python
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diagnostics.models import WritingQuestion


class ImportWritingBankTests(TestCase):
    def test_imports_two_hundred_questions(self):
        call_command("import_writing_bank", stdout=StringIO())
        self.assertEqual(WritingQuestion.objects.count(), 200)

    def test_idempotent(self):
        call_command("import_writing_bank", stdout=StringIO())
        call_command("import_writing_bank", stdout=StringIO())
        self.assertEqual(WritingQuestion.objects.count(), 200)
```

- [ ] **Step 6: Write the import command**

Create `diagnostics/management/commands/import_writing_bank.py`:

```python
"""Import the real 200-question writing bank. Idempotent: clears and reloads."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from diagnostics.extraction.xlsx_writing import extract_writing_items
from diagnostics.models import WritingQuestion

WORKBOOK_NAME = "Question Bank -Diagnostic Test.xlsx"


class Command(BaseCommand):
    help = "Import the real writing question bank (200 items)."

    def handle(self, *args, **options):
        path = settings.DIAGNOSTICS_SOURCE_DIR / WORKBOOK_NAME
        if not path.exists():
            raise CommandError(f"Missing source file: {path}")

        items = extract_writing_items(path)
        # Adaptive, not a snapshot check: import whatever the bank holds, and
        # only object if a subtype's pool is too small to give one grade
        # (4 variants) a non-overlapping selection — the inviolable rule's
        # actual floor, from the headroom analysis in Design Revision 1 §5.
        from collections import Counter

        from diagnostics.constants import WRITING_SUBTYPE_COUNTS

        counts = Counter(item["subtype"] for item in items)
        for subtype, per_paper in WRITING_SUBTYPE_COUNTS.items():
            floor = per_paper * 4
            if counts.get(subtype, 0) < floor:
                raise CommandError(
                    f"Need at least {floor} '{subtype}' writing questions "
                    f"(4 variants x {per_paper} each), only found {counts.get(subtype, 0)}."
                )

        with transaction.atomic():
            WritingQuestion.objects.all().delete()
            for item in items:
                WritingQuestion.objects.create(
                    subtype=item["subtype"], stem=item["stem"],
                    options=item["options"], answer=item["answer"],
                )

        self.stdout.write(self.style.SUCCESS(
            f"Imported {WritingQuestion.objects.count()} writing questions."
        ))
```

Note: this command deletes and reloads the whole bank on every run, rather than the `update_or_create`-by-label pattern used elsewhere — `WritingQuestion` has no natural unique label (unlike `ReadingPassage`/`AudioClip`), and re-importing the whole bank is cheap (200 rows) and always correct. **This means any `Paper` referencing a `WritingQuestion` via `PaperWritingQuestion` would break (`on_delete=PROTECT`) if re-run after papers are built** — acceptable for now since this command only runs before `build_papers` (a later task), but worth a one-line comment in the code and a note here for whoever builds that later task.

- [ ] **Step 7: Run to verify pass**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_import_writing_bank -v 2`
Expected: PASS, 2 tests

- [ ] **Step 8: Import into the real database**

Run: `.venv\Scripts\python.exe manage.py import_writing_bank`
Expected: `Imported 200 writing questions.`

- [ ] **Step 9: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics`
Expected: OK

---

### Task 9: Extract and import the 50-prompt speaking bank + rubric

**Files:**
- Create: `diagnostics/extraction/xlsx_speaking.py`, `diagnostics/management/commands/import_speaking_bank.py`
- Test: `diagnostics/tests/test_xlsx_speaking.py`, `diagnostics/tests/test_import_speaking_bank.py`

- [ ] **Step 1: Write the extraction test**

Create `diagnostics/tests/test_xlsx_speaking.py`:

```python
from django.conf import settings
from django.test import TestCase

from diagnostics.extraction.xlsx_speaking import extract_rubric, extract_speaking_prompts

WORKBOOK = settings.DIAGNOSTICS_SOURCE_DIR / "Question Bank -Diagnostic Test.xlsx"


class ExtractSpeakingTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not WORKBOOK.exists():
            raise AssertionError(f"Source file missing: {WORKBOOK}")
        cls.prompts = extract_speaking_prompts(WORKBOOK)
        cls.rubric = extract_rubric(WORKBOOK)

    def test_fifty_prompts_total(self):
        self.assertEqual(len(self.prompts), 50)

    def test_ten_per_task(self):
        from collections import Counter

        from diagnostics.constants import SPEAKING_TASK_ORDER

        counts = Counter(p["task"] for p in self.prompts)
        for task in SPEAKING_TASK_ORDER:
            self.assertEqual(counts.get(task), 10, task)

    def test_rubric_has_all_five_tasks(self):
        from diagnostics.constants import SPEAKING_TASK_ORDER

        self.assertEqual(sorted(self.rubric), sorted(SPEAKING_TASK_ORDER))

    def test_rubric_marks_sum_to_ten(self):
        self.assertEqual(sum(entry["marks"] for entry in self.rubric.values()), 10)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_xlsx_speaking -v 2`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the extractor**

Create `diagnostics/extraction/xlsx_speaking.py`:

```python
"""Extract the 50-prompt speaking bank and its marking rubric.

Sources, verified 2026-08-24:
  - 'Speaking QB' tab: 5 sections (A-E) of 10 numbered prompts each, mapped
    to the 5 fixed SpeakingTask values in section order.
  - 'Speaking Assessment Rubrics' tab: one row per task with its mark value
    and skill-indicator description (rows 7-11, 'Q1'..'Q5' in column A).
"""

import re

import openpyxl

SECTION_HEADER_RE = re.compile(r"^SECTION\s+([A-E])", re.IGNORECASE)
NUMBERED_ITEM_RE = re.compile(r"^(\d{1,2})\.\s*(.+)$")

SECTION_TO_TASK = {
    "A": "introduction", "B": "experience", "C": "description",
    "D": "role_play", "E": "opinion",
}


def extract_speaking_prompts(path):
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    sheet = workbook["Speaking QB"]
    rows = [row[0].value if row else None for row in sheet.iter_rows(max_col=1)]

    section_bounds = []
    for i, text in enumerate(rows):
        if isinstance(text, str):
            match = SECTION_HEADER_RE.match(text.strip())
            if match:
                section_bounds.append((i, SECTION_TO_TASK[match.group(1).upper()]))
    section_bounds.append((len(rows), None))

    prompts = []
    for (start, task), (end, _) in zip(section_bounds, section_bounds[1:]):
        prompts.extend(_parse_section(rows[start:end], task))
    return prompts


def _parse_section(rows, task):
    items = []
    pending = None
    bullets = []

    for text in rows:
        if not isinstance(text, str) or not text.strip():
            continue
        text = text.strip()

        numbered = NUMBERED_ITEM_RE.match(text)
        if numbered:
            if pending is not None:
                items.append({"task": task, "prompt": pending, "bullets": bullets})
            pending = numbered.group(2)
            bullets = []
            continue

        if pending is not None and text not in ("Include:", "Talk about:", "Explain:"):
            bullets.append(text)

    if pending is not None:
        items.append({"task": task, "prompt": pending, "bullets": bullets})
    return items


def extract_rubric(path):
    """Return {task: {"marks": int, "indicators": str}} for the 5 fixed tasks."""
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    sheet = workbook["Speaking Assessment Rubrics"]

    task_order = ["introduction", "experience", "description", "role_play", "opinion"]
    rubric = {}
    for row in sheet.iter_rows(min_row=7, max_row=11, values_only=True):
        question_label, _task_desc, indicators, marks = row[0], row[1], row[2], row[3]
        if not question_label or not str(question_label).upper().startswith("Q"):
            continue
        index = int(str(question_label).upper().lstrip("Q")) - 1
        if 0 <= index < len(task_order):
            rubric[task_order[index]] = {"marks": int(marks), "indicators": indicators}
    return rubric
```

- [ ] **Step 4: Run and fix until green**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_xlsx_speaking -v 2`

Iterate against real data as needed, same approach as Tasks 7–8.

- [ ] **Step 5: Decide rubric storage and add a model if needed**

The rubric is fixed and shared per task type (5 rows total, not one per prompt). Add a small model rather than re-deriving it from a JSON blob at render time. In `diagnostics/models/content.py`, append:

```python
class SpeakingRubric(models.Model):
    """Fixed marking guidance per task type (Design Revision 1 section 4).

    One row per SpeakingTask value, shared across every prompt of that task —
    not per-prompt, since the rubric describes the task, not the specific
    question.
    """

    task = models.CharField(max_length=16, choices=SpeakingTask.choices, unique=True)
    marks = models.PositiveSmallIntegerField(default=2)
    indicators = models.TextField()

    class Meta:
        ordering = ["task"]

    def __str__(self):
        return f"{self.get_task_display()} rubric"
```

Add to `diagnostics/models/__init__.py`'s import/`__all__`.

Write a model test in `diagnostics/tests/test_models_authored.py` under `SpeakingTests`:

```python
    def test_rubric_is_keyed_by_task_uniquely(self):
        SpeakingRubric.objects.create(task=SpeakingTask.OPINION, marks=2, indicators="x")
        with self.assertRaises(Exception):
            SpeakingRubric.objects.create(task=SpeakingTask.OPINION, marks=2, indicators="y")
```

(Import `SpeakingRubric` in the test file.)

Run `.venv\Scripts\python.exe manage.py makemigrations diagnostics` then `migrate`.

- [ ] **Step 6: Write the import command test**

Create `diagnostics/tests/test_import_speaking_bank.py`:

```python
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diagnostics.models import SpeakingPrompt, SpeakingRubric


class ImportSpeakingBankTests(TestCase):
    def test_imports_fifty_prompts_and_five_rubric_rows(self):
        call_command("import_speaking_bank", stdout=StringIO())
        self.assertEqual(SpeakingPrompt.objects.count(), 50)
        self.assertEqual(SpeakingRubric.objects.count(), 5)

    def test_idempotent(self):
        call_command("import_speaking_bank", stdout=StringIO())
        call_command("import_speaking_bank", stdout=StringIO())
        self.assertEqual(SpeakingPrompt.objects.count(), 50)
```

- [ ] **Step 7: Write the import command**

Create `diagnostics/management/commands/import_speaking_bank.py`:

```python
"""Import the real 50-prompt speaking bank and its marking rubric."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from diagnostics.extraction.xlsx_speaking import extract_rubric, extract_speaking_prompts
from diagnostics.models import SpeakingPrompt, SpeakingRubric

WORKBOOK_NAME = "Question Bank -Diagnostic Test.xlsx"


class Command(BaseCommand):
    help = "Import the real speaking prompt bank (50 items) and its rubric."

    def handle(self, *args, **options):
        path = settings.DIAGNOSTICS_SOURCE_DIR / WORKBOOK_NAME
        if not path.exists():
            raise CommandError(f"Missing source file: {path}")

        prompts = extract_speaking_prompts(path)
        # Adaptive: only object if a task's pool can't cover one grade's 4
        # non-overlapping variants (1 prompt per task per variant).
        from collections import Counter

        from diagnostics.constants import SPEAKING_TASK_ORDER

        counts = Counter(item["task"] for item in prompts)
        for task in SPEAKING_TASK_ORDER:
            if counts.get(task, 0) < 4:
                raise CommandError(
                    f"Need at least 4 '{task}' speaking prompts (one per grade "
                    f"variant), only found {counts.get(task, 0)}."
                )
        rubric = extract_rubric(path)
        missing_rubric = set(SPEAKING_TASK_ORDER) - set(rubric)
        if missing_rubric:
            raise CommandError(f"Missing rubric rows for tasks: {sorted(missing_rubric)}")

        with transaction.atomic():
            SpeakingPrompt.objects.all().delete()
            for item in prompts:
                SpeakingPrompt.objects.create(
                    task=item["task"], prompt=item["prompt"], bullets=item["bullets"],
                )
            for task, entry in rubric.items():
                SpeakingRubric.objects.update_or_create(
                    task=task, defaults={"marks": entry["marks"], "indicators": entry["indicators"]},
                )

        self.stdout.write(self.style.SUCCESS(
            f"Imported {SpeakingPrompt.objects.count()} speaking prompts, "
            f"{SpeakingRubric.objects.count()} rubric rows."
        ))
```

Same `on_delete=PROTECT` caveat as Task 8 applies here — noted, not a blocker at this stage.

- [ ] **Step 8: Run to verify pass**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_import_speaking_bank -v 2`
Expected: PASS, 2 tests

- [ ] **Step 9: Import into the real database**

Run: `.venv\Scripts\python.exe manage.py import_speaking_bank`
Expected: `Imported 50 speaking prompts, 5 rubric rows.`

- [ ] **Step 10: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics`
Expected: OK

---

### Task 10: Random-with-exclusion sampler for writing/speaking

**Files:**
- Create: `diagnostics/sampling.py`
- Test: `diagnostics/tests/test_sampling.py`

- [ ] **Step 1: Write the failing test**

Create `diagnostics/tests/test_sampling.py`:

```python
from django.test import TestCase

from diagnostics.constants import TaskType
from diagnostics.models import (
    AudioClip, Paper, PaperWritingQuestion, ReadingPassage, WritingQuestion, WritingSubtype,
)
from diagnostics.sampling import SamplingError, sample_writing_questions


def make_writing_bank():
    for subtype, count in [
        (WritingSubtype.GRAMMAR, 6), (WritingSubtype.VOCABULARY, 4),
        (WritingSubtype.JUMBLED, 6), (WritingSubtype.FILL_BLANK, 4),
    ]:
        for i in range(count):
            WritingQuestion.objects.create(
                subtype=subtype, stem=f"{subtype}-{i}",
                options=["a", "b", "c", "d"], answer="A",
            )


def make_bare_paper(grade, variant, suffix):
    clip1 = AudioClip.objects.create(number=1000 + hash((grade, variant, "a")) % 900, task_type=TaskType.MCQ3)
    clip2 = AudioClip.objects.create(number=2000 + hash((grade, variant, "b")) % 900, task_type=TaskType.MCQ3)
    return Paper.objects.create(
        grade=grade, variant=variant,
        listening_clip_1=clip1, listening_clip_2=clip2,
        reading_passage=ReadingPassage.objects.create(
            label=f"R{suffix}", title="T", body=" ".join(["word"] * 220)
        ),
    )


class SampleWritingQuestionsTests(TestCase):
    def setUp(self):
        make_writing_bank()

    def test_samples_ten_with_the_required_subtype_mix(self):
        paper = make_bare_paper(9, "A", "01")
        sample_writing_questions(paper)
        slots = list(PaperWritingQuestion.objects.filter(paper=paper).select_related("question"))
        self.assertEqual(len(slots), 10)
        from collections import Counter
        counts = Counter(slot.question.subtype for slot in slots)
        self.assertEqual(
            counts,
            Counter({"grammar": 3, "vocabulary": 2, "jumbled": 3, "fill_blank": 2}),
        )

    def test_no_overlap_within_a_grade(self):
        first = make_bare_paper(9, "A", "01")
        sample_writing_questions(first)
        second = make_bare_paper(9, "B", "02")
        sample_writing_questions(second)
        first_ids = set(PaperWritingQuestion.objects.filter(paper=first).values_list("question_id", flat=True))
        second_ids = set(PaperWritingQuestion.objects.filter(paper=second).values_list("question_id", flat=True))
        self.assertEqual(first_ids & second_ids, set())

    def test_raises_when_pool_is_too_small(self):
        from diagnostics.models import WritingQuestion as WQ

        WQ.objects.filter(subtype=WritingSubtype.VOCABULARY).delete()
        paper = make_bare_paper(9, "A", "01")
        with self.assertRaises(SamplingError):
            sample_writing_questions(paper)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_sampling -v 2`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the sampler**

Create `diagnostics/sampling.py`:

```python
"""Random-with-exclusion sampling for writing/speaking (Design Revision 1).

Mirrors the sibling assembly app's TestVariant/TestQuestion sampling shape,
reimplemented locally (diagnostics imports nothing from assembly). Headroom
was checked analytically before this was built: the tightest pool (writing
grammar/jumbled, 3 needed per paper) only needs 12 of 50 per grade, and
speaking needs 4 of 10 per grade per section — comfortable in every case, so
no fixed allocation table is needed here (unlike listening).
"""

import random

from django.db import transaction

from diagnostics.constants import SPEAKING_TASK_ORDER, WRITING_SUBTYPE_COUNTS
from diagnostics.models import PaperSpeakingPrompt, PaperWritingQuestion, SpeakingPrompt, WritingQuestion


class SamplingError(Exception):
    """A paper's grade cannot be satisfied from the remaining pool."""


def _used_ids_in_grade(model, paper, field_name):
    """Every {field_name} id already used by another paper in this grade."""
    return set(
        model.objects.filter(paper__grade=paper.grade)
        .exclude(paper=paper)
        .values_list(f"{field_name}_id", flat=True)
    )


@transaction.atomic
def sample_writing_questions(paper):
    """Assign 10 writing questions to `paper`: 3 grammar, 2 vocabulary,
    3 jumbled, 2 fill_blank, none shared with a sibling in the same grade."""
    used_ids = _used_ids_in_grade(PaperWritingQuestion, paper, "question")

    PaperWritingQuestion.objects.filter(paper=paper).delete()
    position = 0
    for subtype, count in WRITING_SUBTYPE_COUNTS.items():
        pool = list(
            WritingQuestion.objects.filter(subtype=subtype)
            .exclude(pk__in=used_ids)
            .values_list("pk", flat=True)
        )
        if len(pool) < count:
            raise SamplingError(
                f"Grade {paper.grade}: need {count} '{subtype}' writing questions, "
                f"only {len(pool)} available after excluding grade siblings."
            )
        chosen = random.sample(pool, count)
        for question_id in chosen:
            position += 1
            PaperWritingQuestion.objects.create(
                paper=paper, question_id=question_id, position=position,
            )


@transaction.atomic
def sample_speaking_prompts(paper):
    """Assign 5 speaking prompts to `paper`, one per fixed task, in task
    order, none shared with a sibling in the same grade."""
    used_ids = _used_ids_in_grade(PaperSpeakingPrompt, paper, "prompt")

    PaperSpeakingPrompt.objects.filter(paper=paper).delete()
    for position, task in enumerate(SPEAKING_TASK_ORDER, start=1):
        pool = list(
            SpeakingPrompt.objects.filter(task=task)
            .exclude(pk__in=used_ids)
            .values_list("pk", flat=True)
        )
        if not pool:
            raise SamplingError(
                f"Grade {paper.grade}: no '{task}' speaking prompts left "
                f"after excluding grade siblings."
            )
        chosen_id = random.choice(pool)
        PaperSpeakingPrompt.objects.create(paper=paper, prompt_id=chosen_id, position=position)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_sampling -v 2`
Expected: PASS, 3 tests

- [ ] **Step 5: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics`
Expected: OK

---

## Done when

- `openpyxl` is a declared dependency and the real workbook is readable
- Reading schema accepts all 5 real subtypes and the real word-count range; all 15 real passages import correctly (150 questions total)
- The 200-item writing bank and 50-item speaking bank + rubric import correctly
- `Paper.writing_questions`/`speaking_prompts` work as sampled M2M selections, with within-grade uniqueness enforced at the individual-item level (`Paper.clean()`, tested)
- The sampler assigns a full paper's worth of writing/speaking content respecting the subtype mix and the uniqueness rule
- `diagnostics/authored/` (JSON-based fixed-set authoring) is fully retired — `import_authored.py` deleted, `validate_writing`/`validate_speaking` deleted
- `python manage.py test diagnostics` is green throughout

## Explicitly not covered here (follow-up work)

- **`build_papers`/`check_papers`** (original plan's Task 16) — needs rewriting against the new `Paper` shape: reading still uses the fixed allocation approach (pick from 15, respecting the rule), listening is unchanged, writing/speaking now call `sample_writing_questions`/`sample_speaking_prompts` from this plan instead of pointing at a pre-built set. `check_papers` needs to use `Paper.shared_components()` instead of the retired `SHARED_COMPONENT_FIELDS`.
- **`render_paper`** (original plan's Task 17) — `paper_sections()`/`answer_key()` need updating: reading section gains subtype-aware rendering (heading list for `heading_matching`, paragraph mapping note for `paragraph_matching`); writing/speaking sections iterate `paper.writing_slots`/`paper.speaking_slots` (ordered through-table) instead of `paper.writing_set.questions`/`paper.speaking_set.prompts`; the speaking section should render `SpeakingRubric` per task instead of a bare "examiner judgement" placeholder.
- **CEFR conversion table** — extraction not built in this plan (flagged in the design revision, §6 item 4) — needs its own small extraction task feeding into whatever renders the answer key/scoring guide.
- **Human review of extraction accuracy** — per Design Revision 1 §6, the client still needs to review the *extracted* content (not author new content) before any of it is trusted for real students. Not automatable, same category of gate as Task 12's listening-key sign-off.
