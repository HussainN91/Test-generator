# Diagnostics Revision 2 Implementation Plan — 16 variants, listening rebalance, paper layout

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the diagnostic test set from 12 papers to 48 (16 variants × 3 grades), rebalance every paper's listening section so photos and task difficulty spread evenly, compress the printed paper from ~5 pages to ~3, embed audio players in the web preview, and replace the ZIP download with five separate file downloads.

**Architecture:** The content banks are untouched. What changes is the *assembly* layer (a deterministic allocator plus a capped-reuse sampler replacing the hand-written 12-entry allocation table and the zero-sharing rule), the *rendering* layer (shared option-layout and inline-blank helpers used by both the `.docx` writer and the HTML template, so print and screen cannot drift), and the *delivery* layer (five single-file download views replacing one ZIP view).

**Tech Stack:** Django 6.1, Python 3.14.4, `python-docx`, `openpyxl`, SQLite. Interpreter is always `.venv\Scripts\python.exe`. Tests run with `.venv\Scripts\python.exe manage.py test diagnostics -v 2`.

**Spec:** `docs/superpowers/specs/2026-08-25-diagnostics-16-variants-and-layout-design.md`

---

## Project constraints that override this skill's defaults

- **NO GIT. This project has no `.git` and the user has explicitly declined
  version control.** The writing-plans skill's standard "Step N: Commit" is
  therefore **omitted from every task in this plan**. Do not run `git init`,
  `git add`, or `git commit`. This is intentional, not an oversight.
- `D:\Diagnostics Gate` is read-only client source. Open files there
  read-only; never write, move, or delete anything in it.
- If `~$Question Bank -Diagnostic Test.xlsx` exists, the workbook is open in
  Excel. Tell the user to close it before any task that re-reads the workbook
  (only Task 2 does).
- Any test that writes to an `ImageField`/`FileField` **must** override
  `MEDIA_ROOT` to a temp directory. Django's `TestCase` rollback does not undo
  file writes; this project leaked hundreds of orphaned files that way before.
- **`HANDOFF.md` is stale.** It lists `sampling.py`, `build_papers`,
  `check_papers`, `render_paper` as unbuilt and claims listening stems are
  placeholders. All four exist and the stems are real. Verify against code and
  database, never against that file's "What's left" section.

---

## File structure

| File | Responsibility | Change |
|---|---|---|
| `diagnostics/constants.py` | Static bank facts and fixed patterns | Modify — 16 variants, reuse caps, drop `PAPER_ALLOCATION`/`PROFILE_X`/`PROFILE_Y` |
| `diagnostics/allocation.py` | **New.** Pure deterministic `(grade, variant) → (picture clip, rotating clip, passage)` | Create |
| `diagnostics/sampling.py` | Random writing/speaking selection | Modify — cap-aware instead of exclude-all |
| `diagnostics/verification.py` | Independent re-derivation of the rules | Modify — cap checking instead of zero-sharing |
| `diagnostics/rendering.py` | Format-independent shape of a paper | Modify — add `option_rows()`, `needs_inline_blank()`, reading grouping, new instruction text |
| `diagnostics/export.py` | `.docx` builders | Modify — bold stems, option tables, no answer line; delete `build_pack` |
| `diagnostics/views.py` | Teacher-facing pages | Modify — five download views replacing one |
| `diagnostics/urls.py` | Route table | Modify — five download routes |
| `diagnostics/models/tracking.py` | `GenerationEvent` | Modify — `export_format` choices |
| `diagnostics/models/paper.py` | `Paper.clean()` | Modify — cap rule |
| `templates/diagnostics/paper_detail.html` | Preview page | Modify — audio players, option grid, bold stems, download buttons |
| `static/css/paper.css` | Design system, single source of truth | Modify — option grid + audio player styling only |
| `diagnostics/management/commands/build_papers.py` | Assembles papers | Modify — 48 papers via allocator |

New test files: `diagnostics/tests/test_allocation.py`. Modified:
`test_constants.py`, `test_sampling.py`, `test_build_papers.py`,
`test_rendering.py`, `test_models_paper.py`, `test_models_tracking.py`,
plus a new `diagnostics/tests/test_downloads.py`.

---

## Phase 0 — Pre-flight (do this before Task 1)

- [ ] **Step 1: Confirm no real student has sat an existing paper**

The listening rebalance changes what variants B and D of every grade contain.
`GenerationEvent` holds 2 rows, so downloads have happened.

Run:
```bash
.venv/Scripts/python.exe -c "import django,os;os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');django.setup();from diagnostics.models import GenerationEvent;[print(e.user, e.paper, e.generated_at, e.export_format) for e in GenerationEvent.objects.all()]"
```

Expected: two rows belonging to a developer/test account. **If either row
suggests a real teacher issued a paper to real students, STOP and raise it
with the user** — those variants must be pinned rather than reallocated, which
is a change to the spec, not something to decide during implementation.

- [ ] **Step 2: Record the baseline test count**

Run: `.venv\Scripts\python.exe manage.py test diagnostics -v 2`
Expected: 106 tests, all passing. Note the number; no task in this plan may
reduce it.

---

## Phase 1 — Content fix

### Task 1: Correct the 7 mis-subtyped reading questions

Seven rows stored as `subtype="mcq"` have zero options. Their answers include
`E`, impossible for a 4-option MCQ, and their stems are match-to-paragraph
statements. They are `paragraph_matching` items, not broken MCQs.

**Files:**
- Modify: `diagnostics/extraction/xlsx_reading.py`
- Test: `diagnostics/tests/test_import_reading_bank.py`

- [ ] **Step 1: Confirm the defect against the live database**

Run:
```bash
.venv/Scripts/python.exe -c "import django,os;os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');django.setup();from diagnostics.models import ReadingQuestion;[print(q.passage.label,q.position,repr(q.answer),repr(q.stem[:60])) for q in ReadingQuestion.objects.filter(subtype='mcq') if not q.options]"
```

Expected output — exactly these seven rows:
```
R04 6 'D' 'Students may have problems because they do not have suitable'
R04 7 'A' 'Online learning can help people who cannot easily attend trad'
R04 8 'C' 'Digital tools can make lessons more interesting.'
R04 9 'B' 'Students need to be responsible for managing their study time.'
R04 10 'E' 'Combining two forms of learning may provide advantages.'
R10 9 'B' 'Shared gardens'
R10 10 'A' 'Rooftop gardens'
```

- [ ] **Step 2: Verify against the raw workbook before changing anything**

Ask the user to close Excel if `~$Question Bank -Diagnostic Test.xlsx` exists.
Then read the raw rows for R04 and R10 from the `Reading QB with answers` tab
with `openpyxl` (`read_only=True`) and confirm the source labels these as
matching-type items. **Do not skip this.** This project has real,
confirmed source-data inconsistencies (writing items 123 and 135); establish
which case this is before writing a fix.

If the source says something other than paragraph-matching, stop and report —
the fix changes, and the spec's §4.1 assumption was wrong.

- [ ] **Step 3: Write the failing test**

Add to `diagnostics/tests/test_import_reading_bank.py`:

```python
def test_matching_items_are_not_imported_as_mcq(self):
    """R04 Q6-10 and R10 Q9-10 are match-to-paragraph items, not MCQs.

    They arrive with no options and answers outside A-D (R04 Q10 is 'E'),
    which is impossible for a four-option MCQ. Importing them as 'mcq'
    produces a question a student cannot answer: an MCQ with no choices.
    """
    stray = [
        q for q in ReadingQuestion.objects.filter(subtype=ReadingSubtype.MCQ)
        if not q.options
    ]
    self.assertEqual(
        stray, [],
        f"{len(stray)} MCQ questions have no options: "
        f"{[(q.passage.label, q.position) for q in stray]}",
    )

def test_paragraph_matching_items_keep_their_answers(self):
    matched = ReadingQuestion.objects.filter(
        passage__label="R04", position__in=[6, 7, 8, 9, 10],
    ).order_by("position")
    self.assertEqual(
        [q.subtype for q in matched],
        [ReadingSubtype.PARAGRAPH_MATCHING] * 5,
    )
    self.assertEqual([q.answer for q in matched], ["D", "A", "C", "B", "E"])
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_import_reading_bank -v 2`
Expected: FAIL — `test_matching_items_are_not_imported_as_mcq` reports 7 stray
questions.

- [ ] **Step 5: Fix the subtype classification in the extractor**

In `diagnostics/extraction/xlsx_reading.py`, the subtype is decided from the
source's own label text. Extend that decision so a row that produces **no
options** is never classified `mcq`. Classify it from the answer shape
instead: a single letter answer with no options is a matching item.

Add this guard function and call it at the point where each question's subtype
is finalised:

```python
def resolve_subtype(subtype, options, answer):
    """An MCQ with no options is not an MCQ.

    Seven rows across R04 and R10 carry matching-type items under an 'mcq'
    label in the source. They are recognisable without guessing: an MCQ
    always ships its options, so an option-less row labelled mcq is a
    matching item that was mislabelled upstream.
    """
    if subtype == ReadingSubtype.MCQ and not options:
        return ReadingSubtype.PARAGRAPH_MATCHING
    return subtype
```

- [ ] **Step 6: Add the loud runtime guard**

Mirroring the existing writing-bank mismatch guard, make the importer raise if
an `mcq` row still has no options *after* `resolve_subtype` has run — that
would mean a new, unrecognised source shape has appeared:

```python
if subtype == ReadingSubtype.MCQ and not options:
    raise ValueError(
        f"{label} Q{position}: MCQ with no options after subtype "
        f"resolution. A new source shape has appeared - inspect the raw "
        f"workbook row before relaxing this guard."
    )
```

- [ ] **Step 7: Re-run the import and the tests**

Run: `.venv\Scripts\python.exe manage.py import_reading_bank`
Then: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_import_reading_bank -v 2`
Expected: PASS, and the stray-question query from Step 1 returns nothing.

- [ ] **Step 8: Spot-check by eye**

Print all 10 questions for R04 and R10 with subtype, options and answer, and
read them. Tests passing does not prove semantic correctness — several genuine
bugs in this project were caught only by eyeballing output.

---

## Phase 2 — 48 papers

### Task 2: Widen the variant set and declare the reuse caps

**Files:**
- Modify: `diagnostics/constants.py`
- Test: `diagnostics/tests/test_constants.py`

- [ ] **Step 1: Write the failing test**

Add to `diagnostics/tests/test_constants.py`:

```python
def test_sixteen_variants_per_grade(self):
    self.assertEqual(len(VARIANTS), 16)
    self.assertEqual(VARIANTS[0], "A")
    self.assertEqual(VARIANTS[-1], "P")
    self.assertEqual(len(set(VARIANTS)), 16)

def test_every_variant_label_is_one_character(self):
    """Paper.variant is max_length=1; a two-character label would be
    silently truncated to a duplicate of another variant."""
    for variant in VARIANTS:
        self.assertEqual(len(variant), 1, variant)

def test_reuse_caps_cover_every_capped_component(self):
    self.assertEqual(
        set(REUSE_CAPS),
        {"picture_clip", "rotating_clip", "reading_passage",
         "speaking_prompt", "writing_question"},
    )

def test_caps_supply_enough_slots_for_sixteen_variants(self):
    """Each cap must yield at least 16 usable slots per grade, or the
    48-paper build is unsatisfiable before it starts."""
    pools = {
        "picture_clip": 5, "rotating_clip": 15, "reading_passage": 15,
        "speaking_prompt": 10, "writing_question": 50,
    }
    for component, pool in pools.items():
        slots = pool * REUSE_CAPS[component]
        self.assertGreaterEqual(
            slots, len(VARIANTS),
            f"{component}: {pool} items x cap {REUSE_CAPS[component]} "
            f"= {slots} slots, need {len(VARIANTS)}",
        )
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_constants -v 2`
Expected: FAIL — `VARIANTS` has 4 entries; `REUSE_CAPS` is not defined.

- [ ] **Step 3: Make the change**

In `diagnostics/constants.py`, replace the `VARIANTS` line and add the caps:

```python
GRADES = (9, 10, 11)

#: Sixteen variants per grade (Design Revision 2, section 2.1), up from four.
#: Single characters only - Paper.variant is max_length=1.
VARIANTS = tuple("ABCDEFGHIJKLMNOP")

#: How many times one component may repeat within a single grade
#: (Design Revision 2, section 2). This REPLACES the original
#: "variants within a grade share zero content" rule, which is
#: arithmetically unsatisfiable at 16 variants - the bank holds 20 clips,
#: 15 passages and 10 prompts per task against 32/16/16 slots needed.
#:
#: Caps are scoped per grade; cross-grade reuse remains unrestricted.
#: Writing keeps a cap of 1 (genuine zero reuse) because its pool of 50
#: per subtype supports it - expressed as a cap rather than a special case
#: so one code path covers every component.
REUSE_CAPS = {
    "picture_clip": 4,      # 5 in the bank x 4 = 20 slots, 16 needed
    "rotating_clip": 2,     # 15 in the bank x 2 = 30 slots, 16 needed
    "reading_passage": 2,   # 15 in the bank x 2 = 30 slots, 16 needed
    "speaking_prompt": 2,   # 10 per task x 2 = 20 slots, 16 needed
    "writing_question": 1,  # 50 per subtype, at most 48 needed
}
```

Then **delete** `PAPER_ALLOCATION`, `PAPER_ORDER`, `PROFILE_X` and
`PROFILE_Y`. The first two are replaced by Task 3's allocator; the profiles
encoded the old hardest-with-easiest pairing that §3 of the spec retires, and
leaving them implies a rule no longer in force.

Add the picture/rotating split the allocator needs:

```python
#: The five picture clips carry all 25 images in the bank. Every paper takes
#: exactly one, so every paper gets exactly five photo questions - this is
#: what fixes the uneven photo distribution (Design Revision 2, section 3).
PICTURE_CLIPS = tuple(
    number for number, task in CLIP_TASK_TYPES.items() if task == TaskType.PICTURE
)

#: The other fifteen clips, grouped by task type so the allocator can rotate
#: evenly across the three non-picture types.
ROTATING_CLIPS_BY_TYPE = {
    task: tuple(
        number for number, clip_task in CLIP_TASK_TYPES.items() if clip_task == task
    )
    for task in (TaskType.MCQ3, TaskType.GAP_FILL, TaskType.TRUE_FALSE)
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_constants -v 2`
Expected: PASS.

- [ ] **Step 5: Find every other reference to the deleted constants**

Run: `.venv\Scripts\python.exe -c "print()"` is not enough here — grep instead:

```bash
grep -rn "PAPER_ALLOCATION\|PAPER_ORDER\|PROFILE_X\|PROFILE_Y" diagnostics/
```

Expected: hits in `build_papers.py` and `test_constants.py`. Leave
`build_papers.py` broken for now — Task 4 rewrites it. Delete any
`test_constants.py` test that asserts on the removed profile constants,
because the rule they encoded no longer exists.

- [ ] **Step 6: Generate the migration for the widened choices**

Run: `.venv\Scripts\python.exe manage.py makemigrations diagnostics`
Expected: one `AlterField` on `paper.variant` (choices only — no data change).
Then: `.venv\Scripts\python.exe manage.py migrate`

---

### Task 3: The deterministic allocator

Every paper gets one picture clip, one rotating clip, and one reading passage,
decided by a pure function of `(grade, variant)`. Determinism is a correctness
requirement: `build_papers` rewrites these fields on every run, so a random
allocator would silently reissue different content under the same paper name.

**Files:**
- Create: `diagnostics/allocation.py`
- Test: `diagnostics/tests/test_allocation.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `diagnostics/tests/test_allocation.py`:

```python
"""The allocator decides which fixed content each of the 48 papers gets.

These tests exist because the allocation is the one part of paper assembly
that must never change between runs. build_papers uses update_or_create for
listening and reading, so those fields are rewritten every single build; if
the allocator were not deterministic, re-running the build would reissue
different content under the same paper name and two teachers holding "G9-A"
would be administering different tests.
"""

from collections import Counter
from django.test import SimpleTestCase

from diagnostics.allocation import allocate
from diagnostics.constants import (
    CLIP_TASK_TYPES, GRADES, PICTURE_CLIPS, REUSE_CAPS, TaskType, VARIANTS,
)


class AllocationTests(SimpleTestCase):
    def test_is_deterministic(self):
        first = {(g, v): allocate(g, v) for g in GRADES for v in VARIANTS}
        second = {(g, v): allocate(g, v) for g in GRADES for v in VARIANTS}
        self.assertEqual(first, second)

    def test_every_paper_gets_exactly_one_picture_clip(self):
        """The whole point of the rebalance: 5 photo questions on every
        paper, not 5 on half of them and 0 on the other half."""
        for grade in GRADES:
            for variant in VARIANTS:
                picture, rotating, _passage = allocate(grade, variant)
                self.assertIn(picture, PICTURE_CLIPS, f"G{grade}-{variant}")
                self.assertNotIn(rotating, PICTURE_CLIPS, f"G{grade}-{variant}")

    def test_the_two_clips_are_never_the_same(self):
        for grade in GRADES:
            for variant in VARIANTS:
                picture, rotating, _ = allocate(grade, variant)
                self.assertNotEqual(picture, rotating)

    def test_reuse_caps_are_respected_within_each_grade(self):
        for grade in GRADES:
            pictures, rotators, passages = Counter(), Counter(), Counter()
            for variant in VARIANTS:
                picture, rotating, passage = allocate(grade, variant)
                pictures[picture] += 1
                rotators[rotating] += 1
                passages[passage] += 1
            self.assertLessEqual(max(pictures.values()), REUSE_CAPS["picture_clip"])
            self.assertLessEqual(max(rotators.values()), REUSE_CAPS["rotating_clip"])
            self.assertLessEqual(max(passages.values()), REUSE_CAPS["reading_passage"])

    def test_rotating_task_types_are_evenly_spread(self):
        """No grade may lean on one task type. With 16 variants across three
        types the fairest split is 6/5/5, so no type may appear more than
        twice as often as another."""
        for grade in GRADES:
            types = Counter(
                CLIP_TASK_TYPES[allocate(grade, v)[1]] for v in VARIANTS
            )
            self.assertEqual(len(types), 3, f"G{grade} used {len(types)} types")
            self.assertLessEqual(max(types.values()) - min(types.values()), 1)

    def test_no_two_variants_in_a_grade_share_a_combination(self):
        for grade in GRADES:
            combos = [allocate(grade, v) for v in VARIANTS]
            self.assertEqual(len(set(combos)), len(VARIANTS))

    def test_rejects_an_unknown_variant(self):
        with self.assertRaises(ValueError):
            allocate(9, "Z")
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_allocation -v 2`
Expected: FAIL — `No module named 'diagnostics.allocation'`.

- [ ] **Step 3: Write the allocator**

Create `diagnostics/allocation.py`:

```python
"""Which fixed content each of the 48 papers gets - deterministically.

Replaces the hand-written 12-entry PAPER_ALLOCATION table, which does not
scale to 48 rows without becoming unmaintainable and subtly wrong.

Two properties matter more than elegance here:

  Determinism. build_papers rewrites a paper's listening and reading fields
  on every run via update_or_create. A random allocator would reissue
  different content under the same paper name, so "G9-A" would mean two
  different tests to two teachers. There is no RNG in this module.

  Cap compliance. The bank cannot give 16 variants per grade unique content
  (20 clips against 32 slots), so components repeat up to REUSE_CAPS. The
  round-robin below distributes that reuse as evenly as the pool allows
  rather than exhausting one clip before touching the next.
"""

from diagnostics.constants import (
    GRADES, PICTURE_CLIPS, ROTATING_CLIPS_BY_TYPE, VARIANTS,
)

#: Rotating clips flattened into one list that alternates task type, so
#: consecutive variants get different types and stepping through the list
#: spreads the three types evenly by construction rather than by luck.
_ROTATION = []
_by_type = [list(clips) for clips in ROTATING_CLIPS_BY_TYPE.values()]
for _index in range(max(len(clips) for clips in _by_type)):
    for _clips in _by_type:
        if _index < len(_clips):
            _ROTATION.append(_clips[_index])


def _passages():
    """Reading passage labels R01..R15, in canonical order."""
    return [f"R{number:02d}" for number in range(1, 16)]


def allocate(grade, variant):
    """Return (picture_clip_number, rotating_clip_number, passage_label).

    Pure: the same arguments always produce the same result, with no
    database access and no randomness.

    The grade offset staggers each grade's starting point so grades do not
    all open on the same clip - cross-grade reuse is permitted, but three
    identical-looking grade 9/10/11 variant As would look like a bug to a
    teacher holding two of them.
    """
    try:
        index = VARIANTS.index(variant)
    except ValueError:
        raise ValueError(
            f"Unknown variant {variant!r}; expected one of {''.join(VARIANTS)}."
        ) from None

    offset = (grade - min(GRADES)) * len(VARIANTS)
    picture = PICTURE_CLIPS[(index + offset) % len(PICTURE_CLIPS)]
    rotating = _ROTATION[(index + offset) % len(_ROTATION)]
    passages = _passages()
    passage = passages[(index + offset) % len(passages)]
    return picture, rotating, passage
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_allocation -v 2`
Expected: PASS, 7 tests.

If `test_reuse_caps_are_respected_within_each_grade` fails, the offset is
colliding — adjust the offset expression until all 7 pass. **Do not relax the
test to make it green;** the caps are what make the 48-paper build possible.

- [ ] **Step 5: Print the full allocation and read it**

```bash
.venv/Scripts/python.exe -c "import django,os;os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');django.setup();from diagnostics.allocation import allocate;from diagnostics.constants import GRADES,VARIANTS,CLIP_TASK_TYPES;[print(f'G{g}-{v}', allocate(g,v), CLIP_TASK_TYPES[allocate(g,v)[1]]) for g in GRADES for v in VARIANTS]"
```

Expected: 48 lines. Confirm by eye that picture clips vary, rotating task
types alternate, and no grade repeats a passage more than twice.

---

### Task 4: Cap-aware sampling and verification

**Files:**
- Modify: `diagnostics/sampling.py`
- Modify: `diagnostics/verification.py`
- Modify: `diagnostics/models/paper.py`
- Test: `diagnostics/tests/test_sampling.py`, `diagnostics/tests/test_models_paper.py`

- [ ] **Step 1: Write the failing test**

Add to `diagnostics/tests/test_sampling.py`:

```python
def test_speaking_prompts_may_repeat_up_to_the_cap(self):
    """10 prompts per task against 16 variants means reuse is mandatory.

    The old rule excluded every prompt a grade sibling used, which made a
    16-variant grade unsatisfiable at variant 11. The cap allows each prompt
    twice, giving 20 slots against the 16 needed.
    """
    for variant in VARIANTS:
        paper = Paper.objects.create(
            grade=9, variant=variant,
            listening_clip_1=self.picture_clip,
            listening_clip_2=self.rotating_clip,
            reading_passage=self.passage,
        )
        sample_speaking_prompts(paper)

    counts = Counter(
        PaperSpeakingPrompt.objects.filter(paper__grade=9)
        .values_list("prompt_id", flat=True)
    )
    self.assertLessEqual(max(counts.values()), REUSE_CAPS["speaking_prompt"])
    self.assertEqual(sum(counts.values()), len(VARIANTS) * 5)

def test_writing_questions_never_repeat_within_a_grade(self):
    """Writing keeps a cap of 1 - its pool of 50 per subtype supports
    genuine zero reuse even at 16 variants (3 x 16 = 48)."""
    for variant in VARIANTS:
        paper = Paper.objects.create(
            grade=9, variant=variant,
            listening_clip_1=self.picture_clip,
            listening_clip_2=self.rotating_clip,
            reading_passage=self.passage,
        )
        sample_writing_questions(paper)

    ids = list(
        PaperWritingQuestion.objects.filter(paper__grade=9)
        .values_list("question_id", flat=True)
    )
    self.assertEqual(len(ids), len(set(ids)), "a writing question repeated")

def test_raises_when_a_pool_cannot_satisfy_the_cap(self):
    SpeakingPrompt.objects.filter(task="introduction").delete()
    paper = Paper.objects.create(
        grade=9, variant="A",
        listening_clip_1=self.picture_clip,
        listening_clip_2=self.rotating_clip,
        reading_passage=self.passage,
    )
    with self.assertRaises(SamplingError):
        sample_speaking_prompts(paper)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_sampling -v 2`
Expected: FAIL — the sampler raises `SamplingError` partway through the 16
variants, because it still excludes every sibling's prompt.

- [ ] **Step 3: Replace the exclusion helper with a cap-aware one**

In `diagnostics/sampling.py`, replace `_used_ids_in_grade` with:

```python
from collections import Counter

from diagnostics.constants import REUSE_CAPS


def _at_cap_in_grade(model, paper, field_name, cap):
    """Ids that have already hit their reuse cap within this paper's grade.

    Replaces the old "every id a sibling used" exclusion. At 16 variants the
    bank cannot supply unique content for every paper (10 speaking prompts
    per task against 16 slots), so components repeat up to REUSE_CAPS
    instead of being banned outright - see Design Revision 2 section 2.
    """
    counts = Counter(
        model.objects.filter(paper__grade=paper.grade)
        .exclude(paper=paper)
        .values_list(f"{field_name}_id", flat=True)
    )
    return {item_id for item_id, used in counts.items() if used >= cap}
```

- [ ] **Step 4: Point both samplers at it**

In `sample_writing_questions`, replace the `used_ids` line with:

```python
    used_ids = _at_cap_in_grade(
        PaperWritingQuestion, paper, "question", REUSE_CAPS["writing_question"]
    )
```

In `sample_speaking_prompts`:

```python
    used_ids = _at_cap_in_grade(
        PaperSpeakingPrompt, paper, "prompt", REUSE_CAPS["speaking_prompt"]
    )
```

Update both `SamplingError` messages to name the cap, so a failure explains
itself:

```python
            raise SamplingError(
                f"Grade {paper.grade}: need {count} '{subtype}' writing "
                f"questions, only {len(pool)} available below the reuse cap "
                f"of {REUSE_CAPS['writing_question']}."
            )
```

Also update the module docstring — it currently describes the retired
zero-sharing rule and would actively mislead the next reader.

- [ ] **Step 5: Rewrite the verification to check caps**

In `diagnostics/verification.py`, replace `find_uniqueness_violations` with a
cap check. It must stay independent of `Paper.clean()` — recomputing from
stored data is the entire reason it exists.

```python
def find_reuse_violations():
    """Return human-readable problems; empty means the bank is legal.

    Deliberately does NOT call Paper.clean(). Writing and speaking slots are
    attached AFTER a paper is saved, so clean() cannot self-trigger at the
    moment the last slot lands. This recomputes the answer from what is
    actually stored, catching papers written by bulk updates or .create().
    """
    problems = []
    papers = Paper.objects.select_related(
        "listening_clip_1", "listening_clip_2", "reading_passage"
    ).prefetch_related("writing_questions", "speaking_prompts")

    by_grade = defaultdict(list)
    for paper in papers:
        by_grade[paper.grade].append(paper)

    for grade in GRADES:
        counts = defaultdict(list)
        for paper in by_grade.get(grade, []):
            for label, pk in paper.shared_components():
                counts[(label, pk)].append(paper.variant)

        for (label, _pk), variants in sorted(counts.items()):
            cap = REUSE_CAPS[label]
            if len(variants) > cap:
                problems.append(
                    f"Grade {grade}: {label} used by {len(variants)} variants "
                    f"({', '.join(sorted(variants))}), cap is {cap}."
                )

        combos = [
            tuple(sorted(paper.shared_components()))
            for paper in by_grade.get(grade, [])
        ]
        if len(combos) != len(set(combos)):
            problems.append(
                f"Grade {grade}: two variants have an identical combination "
                f"of components."
            )
    return problems
```

`shared_components()` on `Paper` must now return cap keys matching
`REUSE_CAPS`. Update it in `diagnostics/models/paper.py`:

```python
    def shared_components(self):
        """Every capped component this paper occupies, as (cap key, pk).

        Cap keys match REUSE_CAPS. The listening clips are distinguished by
        task type because they carry different caps: only five picture clips
        exist against sixteen variants, so they are allowed four uses each,
        while the fifteen rotating clips are allowed two.
        """
        pairs = []
        for clip in (self.listening_clip_1, self.listening_clip_2):
            if clip is None:
                continue
            key = (
                "picture_clip"
                if clip.number in PICTURE_CLIPS
                else "rotating_clip"
            )
            pairs.append((key, clip.pk))
        if self.reading_passage_id:
            pairs.append(("reading_passage", self.reading_passage_id))
        if self.pk:
            pairs += [
                ("writing_question", pk)
                for pk in self.writing_questions.values_list("pk", flat=True)
            ]
            pairs += [
                ("speaking_prompt", pk)
                for pk in self.speaking_prompts.values_list("pk", flat=True)
            ]
        return pairs
```

Then replace `Paper.clean()`'s zero-sharing loop with a cap check over the
same keys, keeping the existing "a paper cannot use the same clip twice"
guard:

```python
    def clean(self):
        if self.listening_clip_1_id and self.listening_clip_1_id == self.listening_clip_2_id:
            raise ValidationError(
                {"listening_clip_2": "A paper cannot use the same clip twice."}
            )

        siblings = Paper.objects.filter(grade=self.grade).exclude(pk=self.pk)
        used = Counter()
        for sibling in siblings:
            used.update(sibling.shared_components())

        for key, pk in self.shared_components():
            cap = REUSE_CAPS[key]
            if used[(key, pk)] >= cap:
                raise ValidationError(
                    f"Grade {self.grade}: this {key.replace('_', ' ')} is "
                    f"already used by {used[(key, pk)]} variants, and the "
                    f"reuse cap is {cap}."
                )
```

This needs `from collections import Counter` and
`from diagnostics.constants import PICTURE_CLIPS, REUSE_CAPS` at the top of
`diagnostics/models/paper.py`. Update the module docstring too — it currently
states the zero-sharing rule as inviolable, which is exactly the claim this
revision retires.

Keep `find_completeness_problems` as it is, and update
`EXPECTED_PAPER_COUNT` — it already derives from `len(GRADES) * len(VARIANTS)`
and becomes 48 automatically. Update `check_papers.py`'s import and its
success message, which currently says "the four variants in each grade".

- [ ] **Step 6: Run the full suite**

Run: `.venv\Scripts\python.exe manage.py test diagnostics -v 2`
Expected: PASS. Some existing `test_models_paper.py` tests assert the retired
zero-sharing rule and will need rewriting to assert the cap rule instead —
rewrite them, do not delete them.

---

### Task 5: Build 48 papers

**Files:**
- Modify: `diagnostics/management/commands/build_papers.py`
- Test: `diagnostics/tests/test_build_papers.py`

- [ ] **Step 1: Write the failing test**

```python
def test_builds_forty_eight_papers(self):
    call_command("build_papers", stdout=StringIO())
    self.assertEqual(Paper.objects.count(), 48)
    for grade in GRADES:
        self.assertEqual(Paper.objects.filter(grade=grade).count(), 16)

def test_every_paper_has_a_picture_clip(self):
    call_command("build_papers", stdout=StringIO())
    for paper in Paper.objects.all():
        numbers = {paper.listening_clip_1.number, paper.listening_clip_2.number}
        self.assertEqual(
            len(numbers & set(PICTURE_CLIPS)), 1,
            f"{paper} has {len(numbers & set(PICTURE_CLIPS))} picture clips",
        )

def test_rebuilding_does_not_change_listening_or_reading(self):
    """update_or_create rewrites these fields on every run, so the
    allocator must be deterministic or a rebuild silently reissues
    different content under the same paper name."""
    call_command("build_papers", stdout=StringIO())
    before = {
        str(p): (p.listening_clip_1_id, p.listening_clip_2_id, p.reading_passage_id)
        for p in Paper.objects.all()
    }
    call_command("build_papers", stdout=StringIO())
    after = {
        str(p): (p.listening_clip_1_id, p.listening_clip_2_id, p.reading_passage_id)
        for p in Paper.objects.all()
    }
    self.assertEqual(before, after)
```

`seed_content` in this file builds enough clips/passages for 12 papers. Widen
it to seed all 20 clips with their real task types (from `CLIP_TASK_TYPES`)
and all 15 passages, or the 48-paper build cannot run.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_build_papers -v 2`
Expected: FAIL — `build_papers` still imports the deleted `PAPER_ALLOCATION`.

- [ ] **Step 3: Rewrite the command's allocation loop**

Replace the `PAPER_ALLOCATION`/`PAPER_ORDER` imports with the allocator, and
the paper loop body with:

```python
        from diagnostics.allocation import allocate
        from diagnostics.constants import GRADES, VARIANTS

        passages = {p.label: p for p in ReadingPassage.objects.all()}

        for grade in GRADES:
            for variant in VARIANTS:
                picture, rotating, passage_label = allocate(grade, variant)
                if passage_label not in passages:
                    raise CommandError(
                        f"G{grade}-{variant} needs reading passage "
                        f"{passage_label}, which is not imported. "
                        f"Run import_reading_bank first."
                    )
                paper, _ = Paper.objects.update_or_create(
                    grade=grade,
                    variant=variant,
                    defaults={
                        "listening_clip_1": clips[picture],
                        "listening_clip_2": clips[rotating],
                        "reading_passage": passages[passage_label],
                        "is_published": True,
                    },
                )
                already_complete = (
                    paper.writing_questions.count() == 10
                    and paper.speaking_prompts.count() == 5
                )
                if already_complete and not resample:
                    left_alone += 1
                    continue
                sample_writing_questions(paper)
                sample_speaking_prompts(paper)
                sampled += 1
```

Update the pre-flight clip check to require every clip the allocator can
return, and swap `find_uniqueness_violations` for `find_reuse_violations` in
the rollback guard. Update the module docstring — it describes the retired
allocation table and hand-designed pairing.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_build_papers -v 2`
Expected: PASS.

- [ ] **Step 5: Build for real and verify**

```bash
.venv/Scripts/python.exe manage.py build_papers --resample
```
Expected: "Built 48 papers".

```bash
.venv/Scripts/python.exe manage.py check_papers
```
Expected: "All 48 papers pass".

- [ ] **Step 6: Confirm photo distribution is actually fixed**

```bash
.venv/Scripts/python.exe -c "import django,os;os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');django.setup();from diagnostics.models import Paper,ListeningQuestion;from collections import Counter;c=Counter(ListeningQuestion.objects.filter(clip__in=[p.listening_clip_1,p.listening_clip_2]).exclude(image='').count() for p in Paper.objects.all());print(c)"
```

Expected: `Counter({5: 48})` — every one of the 48 papers has exactly 5 photo
questions. Any other output means the rebalance did not work; stop and
diagnose before continuing.

---

## Phase 3 — Paper layout

### Task 6: Shared layout helpers in rendering.py

Both the `.docx` writer and the HTML template need the same answers to "how
many options per line" and "does this stem need a blank". Putting them in
`rendering.py` is what stops print and screen drifting apart.

**Files:**
- Modify: `diagnostics/rendering.py`
- Test: `diagnostics/tests/test_rendering.py`

- [ ] **Step 1: Write the failing tests**

```python
class OptionLayoutTests(SimpleTestCase):
    def test_four_options_go_two_per_line(self):
        rows = option_rows(["a", "b", "c", "d"])
        self.assertEqual(rows, [[("A", "a"), ("B", "b")],
                                [("C", "c"), ("D", "d")]])

    def test_three_options_share_one_line(self):
        rows = option_rows(["a", "b", "c"])
        self.assertEqual(rows, [[("A", "a"), ("B", "b"), ("C", "c")]])

    def test_two_options_share_one_line(self):
        rows = option_rows(["YES", "NO"])
        self.assertEqual(rows, [[("A", "YES"), ("B", "NO")]])

    def test_no_options_yields_no_rows(self):
        self.assertEqual(option_rows([]), [])


class InlineBlankTests(SimpleTestCase):
    def test_option_less_question_needs_a_blank(self):
        self.assertTrue(needs_inline_blank("The class starts at", []))

    def test_question_with_options_needs_no_blank(self):
        self.assertFalse(needs_inline_blank("Pick one", ["a", "b"]))

    def test_stem_that_already_has_a_blank_gets_no_second_one(self):
        """All 25 listening gap-fill stems already carry their own marker,
        e.g. "Caspar's mother dances across a ______ in the circus."
        Appending another would print two blanks on one line."""
        self.assertFalse(
            needs_inline_blank("Caspar's mother dances across a ______ in the circus.", [])
        )

    def test_stem_with_an_ellipsis_gap_gets_no_second_blank(self):
        self.assertFalse(needs_inline_blank("She arrives at ………… on Monday.", []))

    def test_stem_with_a_numbered_gap_reference_gets_no_second_blank(self):
        self.assertFalse(needs_inline_blank("He bought (1) … apples.", []))
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_rendering -v 2`
Expected: FAIL — `option_rows` and `needs_inline_blank` are not defined.

- [ ] **Step 3: Implement both helpers**

Add to `diagnostics/rendering.py`:

```python
import re

#: How many options share one printed line, by option count
#: (Design Revision 2, section 5.2). Four options split two and two; three
#: or fewer all fit on one line.
OPTIONS_PER_LINE = {2: 2, 3: 3, 4: 2}

#: Markers that mean a stem already carries its own gap. All 25 listening
#: gap-fill stems end with "______" because the extractor wrote them that
#: way, and some reading completion stems use the source's ellipsis run or
#: a numbered "(1) ..." reference. Appending a second blank to any of these
#: prints two blanks on one line.
_EXISTING_GAP_RE = re.compile(r"_{3,}|\u2026{2,}|\.{4,}|\(\d+\)")

INLINE_BLANK = "_" * 12


def option_rows(options):
    """Group lettered options into printed lines.

    Returns a list of lines, each a list of (letter, option) pairs, so the
    docx writer and the HTML template lay options out identically. A paper
    preview that differs from the printed paper is worse than no preview.
    """
    pairs = _lettered(options)
    if not pairs:
        return []
    per_line = OPTIONS_PER_LINE.get(len(pairs), 2)
    return [pairs[i:i + per_line] for i in range(0, len(pairs), per_line)]


def needs_inline_blank(stem, options):
    """Whether this question needs a ruled blank appended to its stem.

    The separate "Answer: ____" line is gone from every question (Design
    Revision 2, section 5.3) - students circle their choice. Questions with
    nothing to circle need somewhere to write instead, but only if the stem
    does not already contain its own gap.
    """
    if options:
        return False
    return not _EXISTING_GAP_RE.search(stem or "")
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_rendering -v 2`
Expected: PASS, 10 new tests.

- [ ] **Step 5: Update the section instruction text**

The current instructions tell students to write in spaces that no longer
exist. Replace in `rendering.py`:

```python
READING_INSTRUCTIONS = (
    "Read the passage, then answer the ten questions that follow. "
    "Circle your answer where choices are given; write on the line where "
    "they are not. There are 10 marks."
)
WRITING_INSTRUCTIONS = (
    "Circle the letter of the best option for each question. "
    "There are 10 marks."
)
LISTENING_INSTRUCTIONS = (
    "You will hear two recordings. Each recording is played twice. "
    "Circle your answer where choices are given; write on the line where "
    "they are not. There are 10 marks."
)
```

- [ ] **Step 6: Add reading question grouping**

Spec §5.6 replaces the per-question `[subtype]` label with grouped
sub-instructions. Add to `rendering.py`:

```python
#: One short instruction per reading subtype, printed once above its group
#: instead of a bracketed label after all ten stems (Design Revision 2,
#: section 5.6). Without this the removal of the answer line leaves a
#: student unable to tell a True/False item from an MCQ.
READING_GROUP_INSTRUCTIONS = {
    "true_false_ng": "Write TRUE, FALSE or NOT GIVEN on the line.",
    "mcq": "Circle the letter of the correct answer.",
    "completion": "Complete each sentence with a word from the passage.",
    "heading_matching": "Write the letter of the matching heading on the line.",
    "paragraph_matching": "Write the letter of the matching paragraph on the line.",
}


def reading_groups(questions):
    """Reading questions grouped into runs of the same subtype, in order.

    Returns [(subtype, instruction, [questions])]. Consecutive runs are kept
    separate rather than merged, so question numbering stays sequential down
    the page - a student following "questions 1-10" must never have to jump.
    """
    groups = []
    for question in questions:
        if groups and groups[-1][0] == question.subtype:
            groups[-1][2].append(question)
        else:
            groups.append((
                question.subtype,
                READING_GROUP_INSTRUCTIONS.get(question.subtype, ""),
                [question],
            ))
    return groups
```

Add the tests for it:

```python
class ReadingGroupTests(SimpleTestCase):
    class FakeQuestion:
        def __init__(self, subtype, position):
            self.subtype, self.position = subtype, position

    def test_consecutive_same_subtype_questions_group_together(self):
        questions = [self.FakeQuestion("mcq", n) for n in (1, 2, 3)]
        groups = reading_groups(questions)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0][0], "mcq")
        self.assertEqual(len(groups[0][2]), 3)

    def test_a_subtype_change_starts_a_new_group(self):
        questions = [
            self.FakeQuestion("mcq", 1),
            self.FakeQuestion("mcq", 2),
            self.FakeQuestion("completion", 3),
        ]
        groups = reading_groups(questions)
        self.assertEqual([g[0] for g in groups], ["mcq", "completion"])

    def test_a_repeated_subtype_does_not_merge_across_a_gap(self):
        """Runs stay separate so question numbers never jump. A student
        told to answer questions 1-10 in order must not be sent back up
        the page to finish an earlier group."""
        questions = [
            self.FakeQuestion("mcq", 1),
            self.FakeQuestion("completion", 2),
            self.FakeQuestion("mcq", 3),
        ]
        groups = reading_groups(questions)
        self.assertEqual([g[0] for g in groups], ["mcq", "completion", "mcq"])

    def test_every_subtype_has_an_instruction(self):
        from diagnostics.models import ReadingSubtype
        for subtype in ReadingSubtype.values:
            self.assertIn(subtype, READING_GROUP_INSTRUCTIONS)
```

- [ ] **Step 7: Run the full suite**

Run: `.venv\Scripts\python.exe manage.py test diagnostics -v 2`
Expected: PASS.

---

### Task 7: Apply the layout to the .docx

**Files:**
- Modify: `diagnostics/export.py`
- Test: `diagnostics/tests/test_rendering.py`

- [ ] **Step 1: Write the failing test**

```python
def test_student_docx_has_no_answer_lines_for_circleable_questions(self):
    """Answer: ____ is removed everywhere (Design Revision 2, 5.3);
    students circle instead."""
    document = student_docx(self.paper)
    text = "\n".join(p.text for p in document.paragraphs)
    self.assertNotIn("Answer:", text)

def test_student_docx_bolds_question_stems(self):
    document = student_docx(self.paper)
    stems = [p for p in document.paragraphs if p.text.startswith("1.")]
    self.assertTrue(stems, "no numbered question found")
    self.assertTrue(any(run.bold for run in stems[0].runs))

def test_gap_fill_stem_is_not_given_a_second_blank(self):
    question = ListeningQuestion.objects.filter(
        clip=self.paper.listening_clip_2
    ).first()
    question.stem = "Caspar's mother dances across a ______ in the circus."
    question.options = []
    question.save()
    document = student_docx(self.paper)
    text = "\n".join(p.text for p in document.paragraphs)
    self.assertNotIn("______ in the circus. " + INLINE_BLANK, text)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_rendering -v 2`
Expected: FAIL — `Answer:` still appears.

- [ ] **Step 3: Add a shared stem/option writer**

Add to `diagnostics/export.py` and use it from all three section writers, so
the layout rules live in exactly one place:

```python
def _write_question(document, number, question):
    """One question: bold numbered stem, options in shared-line tables,
    and an inline blank only where there is nothing to circle."""
    from diagnostics.rendering import (
        INLINE_BLANK, needs_inline_blank, option_rows,
    )

    stem = f"{number}. {question.stem}"
    if needs_inline_blank(question.stem, question.options):
        stem = f"{stem}  {INLINE_BLANK}"
    paragraph = document.add_paragraph()
    run = paragraph.add_run(stem)
    run.bold = True

    rows = option_rows(question.options or [])
    if not rows:
        return

    table = document.add_table(rows=len(rows), cols=len(rows[0]))
    table.style = "Table Grid"
    _remove_table_borders(table)
    for row_index, line in enumerate(rows):
        for cell_index, (letter, option) in enumerate(line):
            table.rows[row_index].cells[cell_index].text = f"{letter}) {option}"


def _remove_table_borders(table):
    """python-docx has no borderless table style, so the borders are
    cleared on the table's XML directly. Without this the option grid
    prints as a visible grid of boxes rather than aligned columns."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "none")
        element.set(qn("w:sz"), "0")
        borders.append(element)
    table._tbl.tblPr.append(borders)
```

Rewrite `_write_listening`, `_write_reading` and `_write_writing` to call
`_write_question` and to drop every `Answer: ...` paragraph. In
`_write_reading`, iterate `reading_groups(...)` and print each group's
instruction once in italic, replacing the per-question
`[{question.get_subtype_display()}]` suffix.

Note the last row of `option_rows` can be shorter than the first for a
5-option question; guard the table width with
`cols=max(len(line) for line in rows)` and leave trailing cells empty.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_rendering -v 2`
Expected: PASS.

- [ ] **Step 5: Render a real paper and count pages**

```bash
.venv/Scripts/python.exe manage.py render_paper --grade 9 --variant A
```

Open the resulting `.docx` and count pages. **The 5→3 target is measured here,
not assumed.** If it is not met, report the actual count rather than quietly
accepting it — spec §5.7.

---

### Task 8: Match the web preview to the print layout

**Files:**
- Modify: `templates/diagnostics/paper_detail.html`
- Modify: `static/css/paper.css`
- Modify: `diagnostics/views.py`

- [ ] **Step 1: Feed the template the shared helpers**

In `views.py`, `_annotate_for_display` currently attaches
`question.lettered`. Replace that with `question.option_rows` (from
`rendering.option_rows`) and `question.inline_blank` (a bool from
`needs_inline_blank`) for listening, reading and writing questions alike, and
pass `reading_groups(...)` into the context.

- [ ] **Step 2: Update the template**

In `templates/diagnostics/paper_detail.html`:
- Wrap every `<p class="qprompt">{{ question.stem }}</p>` in `<strong>`, and
  append `<span class="blank"></span>` when `question.inline_blank` is true.
- Replace each `{% for letter, option in question.lettered %}` loop with a
  nested loop over `question.option_rows`, emitting one `<div class="qrow">`
  per line.
- Remove the `style="grid-template-columns:1fr"` override on the listening
  section's `.qopts`.
- Replace the reading question loop with a loop over `reading_groups`,
  printing each group's instruction once.

- [ ] **Step 3: Add the CSS**

In `static/css/paper.css`, extend the existing `.qopts` rule rather than
forking it — that file is the single source of truth for this design system:

```css
.qopts .qrow { display: flex; gap: 18px; }
.qopts .qrow > .qopt { flex: 1; }
.blank { display: inline-block; min-width: 90px;
         border-bottom: 1px solid var(--ink-3); margin-left: 6px; }
```

- [ ] **Step 4: Verify in the browser**

Start the server, open a paper, and confirm: stems are bold, 4-option
questions show two per line, listening 3-option questions show three on one
line, no "Answer:" text appears, and gap-fill stems show exactly one blank.

---

## Phase 4 — Delivery

### Task 9: Record which file was downloaded

**Files:**
- Modify: `diagnostics/models/tracking.py`
- Test: `diagnostics/tests/test_models_tracking.py`

- [ ] **Step 1: Write the failing test**

```python
def test_export_format_accepts_each_download_kind(self):
    for value in ("student", "answer_key", "examiner", "audio_1", "audio_2"):
        event = GenerationEvent(user=self.user, paper=self.paper,
                                export_format=value)
        event.full_clean()

def test_export_format_rejects_an_unknown_kind(self):
    event = GenerationEvent(user=self.user, paper=self.paper,
                            export_format="pdf")
    with self.assertRaises(ValidationError):
        event.full_clean()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_models_tracking -v 2`
Expected: FAIL — no choices are defined, so `"pdf"` validates fine.

- [ ] **Step 3: Add the choices**

In `diagnostics/models/tracking.py`:

```python
class ExportFormat(models.TextChoices):
    STUDENT = "student", "Test paper"
    ANSWER_KEY = "answer_key", "Answer key"
    EXAMINER = "examiner", "Speaking pack"
    AUDIO_1 = "audio_1", "Audio, recording 1"
    AUDIO_2 = "audio_2", "Audio, recording 2"
```

and on `GenerationEvent`:

```python
    export_format = models.CharField(
        max_length=16, choices=ExportFormat.choices, default=ExportFormat.STUDENT,
    )
```

The two existing rows hold the historical value `"zip"`. Leave them — they
record something that genuinely happened, and no migration should rewrite
history.

- [ ] **Step 4: Migrate and test**

Run: `.venv\Scripts\python.exe manage.py makemigrations diagnostics`
Then: `.venv\Scripts\python.exe manage.py migrate`
Then: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_models_tracking -v 2`
Expected: PASS.

---

### Task 10: Five separate downloads, ZIP removed

**Files:**
- Modify: `diagnostics/export.py`, `diagnostics/views.py`, `diagnostics/urls.py`
- Modify: `templates/diagnostics/paper_detail.html`
- Test: `diagnostics/tests/test_downloads.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `diagnostics/tests/test_downloads.py`:

```python
"""Each file downloads on its own. The ZIP pack is gone.

Management's stated reason: a zip is awkward for teachers. Photos are NOT
downloadable separately - they exist only embedded inside the test document
(Design Revision 2, section 7).
"""

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class DownloadTests(TestCase):
    def test_each_document_downloads_separately(self):
        for kind, suffix in (
            ("student", "Student.docx"),
            ("answer_key", "AnswerKey.docx"),
            ("examiner", "Examiner.docx"),
        ):
            response = self.client.get(
                reverse("diagnostics:paper_file",
                        args=[self.paper.grade, self.paper.variant, kind])
            )
            self.assertEqual(response.status_code, 200, kind)
            self.assertEqual(response["Content-Type"], DOCX)
            self.assertIn(suffix, response["Content-Disposition"])

    def test_each_recording_downloads_separately(self):
        for kind in ("audio_1", "audio_2"):
            response = self.client.get(
                reverse("diagnostics:paper_file",
                        args=[self.paper.grade, self.paper.variant, kind])
            )
            self.assertEqual(response.status_code, 200, kind)

    def test_every_download_is_recorded(self):
        for kind in ("student", "answer_key", "examiner", "audio_1", "audio_2"):
            self.client.get(reverse(
                "diagnostics:paper_file",
                args=[self.paper.grade, self.paper.variant, kind]))
        self.assertEqual(
            set(GenerationEvent.objects.values_list("export_format", flat=True)),
            {"student", "answer_key", "examiner", "audio_1", "audio_2"},
        )

    def test_unknown_file_kind_is_404(self):
        response = self.client.get(
            reverse("diagnostics:paper_file",
                    args=[self.paper.grade, self.paper.variant, "photos"]))
        self.assertEqual(response.status_code, 404)

    def test_downloads_refused_when_generation_is_closed(self):
        window = GenerationWindow.load()
        window.is_open = False
        window.save()
        for kind in ("student", "answer_key", "examiner", "audio_1", "audio_2"):
            response = self.client.get(reverse(
                "diagnostics:paper_file",
                args=[self.paper.grade, self.paper.variant, kind]))
            self.assertEqual(response.status_code, 404, kind)
```

This test class writes no files, but it reads `FileField.path` for audio. Seed
the audio via a temp `MEDIA_ROOT` override on the class, per the constraints
section.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_downloads -v 2`
Expected: FAIL — `diagnostics:paper_file` is not a registered URL.

- [ ] **Step 3: Delete the ZIP builder**

Remove `build_pack`, `README_TEMPLATE` and `_readme_text` from
`diagnostics/export.py`, plus the now-unused `io` and `zipfile` imports.
`README.txt` existed to explain the contents of a bundle that no longer
exists. Update the module docstring, which describes the ZIP in detail.

- [ ] **Step 4: Write the single download view**

Replace `paper_download` in `diagnostics/views.py`:

```python
DOCX_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

#: kind -> (builder, filename suffix). Audio is handled separately below
#: because it streams a file already on disk rather than building one.
_DOCUMENTS = {
    "student": (student_docx, "Student.docx"),
    "answer_key": (answer_key_docx, "AnswerKey.docx"),
    "examiner": (examiner_docx, "Examiner.docx"),
}


@login_required
def paper_file(request, grade: int, variant: str, kind: str):
    """Stream one file of a paper and record who took it.

    One view rather than five near-identical ones: every kind shares the
    same visibility check, the same generation-window refusal, and the same
    tracking write, and those are the parts that must not drift.
    """
    paper = _get_visible_paper(request.user, grade, variant)
    if not GenerationWindow.load().is_open:
        raise Http404("Generation is currently closed.")

    if kind in _DOCUMENTS:
        if not docx_available():
            raise Http404("python-docx is not installed on this server.")
        builder, suffix = _DOCUMENTS[kind]
        stream = io.BytesIO()
        builder(paper).save(stream)
        payload, content_type = stream.getvalue(), DOCX_TYPE
        filename = f"{paper}-{suffix}"
    elif kind in ("audio_1", "audio_2"):
        clip = paper.listening_clip_1 if kind == "audio_1" else paper.listening_clip_2
        if not clip.audio_file:
            raise Http404("No recording on file for this clip.")
        try:
            path = clip.audio_file.path
        except (NotImplementedError, ValueError):
            raise Http404("Recording is not available from this storage backend.")
        if not os.path.exists(path):
            raise Http404("Recording file is missing from disk.")
        with open(path, "rb") as handle:
            payload = handle.read()
        content_type = "audio/mpeg"
        filename = f"{paper}-{os.path.basename(clip.audio_file.name)}"
    else:
        raise Http404("Unknown file.")

    GenerationEvent.objects.create(user=request.user, paper=paper, export_format=kind)
    response = HttpResponse(payload, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
```

Add `import io` and import the three builders from `diagnostics.export`.

- [ ] **Step 5: Update the routes**

In `diagnostics/urls.py`, replace the download path:

```python
    path(
        "<int:grade>/<str:variant>/download/<str:kind>/",
        views.paper_file,
        name="paper_file",
    ),
```

- [ ] **Step 6: Update the template**

Replace the single "Download pack" button with five buttons, and replace the
"Pack contents" sidebar list — which describes a ZIP that no longer exists —
with the same five links:

```html
{% if generation_open %}
  {% if docx_available %}
    <a class="btn" href="{% url 'diagnostics:paper_file' paper.grade paper.variant 'student' %}">Download test</a>
    <a class="btn ghost" href="{% url 'diagnostics:paper_file' paper.grade paper.variant 'answer_key' %}">Answer key</a>
    <a class="btn ghost" href="{% url 'diagnostics:paper_file' paper.grade paper.variant 'examiner' %}">Speaking pack</a>
  {% endif %}
  <a class="btn ghost" href="{% url 'diagnostics:paper_file' paper.grade paper.variant 'audio_1' %}">Audio 1</a>
  <a class="btn ghost" href="{% url 'diagnostics:paper_file' paper.grade paper.variant 'audio_2' %}">Audio 2</a>
{% else %}
  <span class="stamp mute">Generation closed &mdash; downloads refused</span>
{% endif %}
```

- [ ] **Step 7: Run the full suite**

Run: `.venv\Scripts\python.exe manage.py test diagnostics -v 2`
Expected: PASS. Existing tests referencing `diagnostics:paper_download` or
`build_pack` must be rewritten against the new view, not deleted.

---

### Task 11: Embed the audio players

**Files:**
- Modify: `templates/diagnostics/paper_detail.html`
- Modify: `diagnostics/views.py`
- Modify: `static/css/paper.css`

- [ ] **Step 1: Expose the audio URL to the template**

In `_annotate_for_display`, alongside the existing `clip["audio_name"]`, add:

```python
        clip["audio_url"] = clip["audio"].url if clip["audio"] else ""
```

- [ ] **Step 2: Add the player**

In the listening section of `paper_detail.html`, immediately after the
`Recording {{ clip.number }}` heading:

```html
{% if clip.audio_url %}
  <audio class="clipaudio" controls preload="none" src="{{ clip.audio_url }}">
    Your browser cannot play audio. Use the Audio download button above.
  </audio>
{% endif %}
```

One player per recording, not per question — a recording is played twice to
the whole room, so a per-question player would misrepresent how the section
is actually run. `preload="none"` keeps the page from fetching both MP3s on
every view.

- [ ] **Step 3: Style it**

In `static/css/paper.css`:

```css
.clipaudio { width: 100%; margin: 10px 0 14px; }
```

- [ ] **Step 4: Verify in the browser**

Open a paper and confirm both players appear and play. Check the network tab
shows no MP3 fetched until play is pressed.

---

## Phase 5 — Verification

### Task 12: Full verification pass

- [ ] **Step 1: Run the whole suite**

Run: `.venv\Scripts\python.exe manage.py test diagnostics -v 2`
Expected: all pass, and the count is **at or above** the 106 baseline from
Phase 0.

- [ ] **Step 2: Run the project suite, not just this app**

Run: `.venv\Scripts\python.exe manage.py test -v 2`
Expected: all pass. The `assembly`/`bank` apps share `paper.css`; a CSS change
must not break their pages.

- [ ] **Step 3: Rebuild and verify the papers**

```bash
.venv/Scripts/python.exe manage.py build_papers --resample
```
```bash
.venv/Scripts/python.exe manage.py check_papers
```
Expected: 48 papers built, all passing.

- [ ] **Step 4: Confirm every management complaint is answered**

Run the photo-distribution check from Task 5 Step 6 again — expected
`Counter({5: 48})`.

Then walk the list explicitly and record the result of each:

| Complaint | Check |
|---|---|
| 16 variants per grade | `Paper.objects.count() == 48`, 16 per grade |
| Audio embedded in the site | Both players visible and playing on a paper page |
| Audio question distribution | Every paper has 1 picture + 1 rotating clip; types even across a grade |
| Photos unequally distributed | Every paper has exactly 5 photo questions |
| ZIP too complex | Five separate downloads; no ZIP route remains |

- [ ] **Step 5: Render and read one paper per grade**

```bash
.venv/Scripts/python.exe manage.py render_paper --grade 9 --variant A
.venv/Scripts/python.exe manage.py render_paper --grade 10 --variant H
.venv/Scripts/python.exe manage.py render_paper --grade 11 --variant P
```

Open each and check: page count against the 3-page target, bold stems,
two-per-line options, three-on-one-line for listening MCQs, exactly one blank
on gap-fill stems, group instructions above each reading run, and no "Answer:"
anywhere. **Report the real page count**, including if the target was missed.

- [ ] **Step 6: Update HANDOFF.md**

`HANDOFF.md` is already stale in five documented ways. Rewrite its "Progress",
"What's left" and "Two known gaps" sections to describe reality: 48 papers,
capped reuse, separate downloads, embedded audio, listening stems already
real, and the reading-subtype fix. Note that the zero-sharing rule was
deliberately retired and point to this revision's spec.

---

## Explicitly not covered here

- Task 12's human listening sign-off (`verify_listening_keys --sign-off`).
  Requires a person with ears; an agent cannot do it and must not fabricate it.
- The CEFR conversion table in the workbook's `CEFR Conversion table LRW` tab.
- Any teacher-facing UI beyond the paper preview page.
- Client review of extracted content accuracy for real student use.
