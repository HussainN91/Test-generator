# Exam Groups and Listening Question Sets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the two variants sitting in the same room at the same time share one audio recording while answering different questions about it, and prove it holds for all 24 groups.

**Architecture:** Introduce a derived "group" concept (2 per class, 8 per grade) alongside the existing derived class concept in `navigation.py`; insert a `ListeningQuestionSet` layer between `AudioClip` and `ListeningQuestion` so one recording can carry two distinct 5-question sets; make `allocation.py` draw the clip pair once per group and the set number per variant; harden `sampling.py` and `verification.py` against the group boundary.

**Tech Stack:** Django 5 / SQLite, `python manage.py test` (unittest), no third-party additions.

---

## Scope note: this plan folds in the spec

**No separate spec pass is being run.** The design came out of a chat discussion, not the brainstorming skill's write-up step, so Part 0 below carries the spec-level detail — the group model, the arithmetic, the invariants and the accepted limitation — in enough depth that the plan stands on its own. If you want a formally reviewed spec before code, stop here and lift Part 0 into `docs/` as a Design Revision 3 document first; nothing in Parts 1-8 depends on that happening.

---

## Part 0: Design contract

### 0.1 The group

The exam is administered as: **4 classes per grade, each class splits into 2 groups, each group sits at one time in one room.** A group is 2 variants. That is 8 groups per grade, 24 groups in total.

The code models classes (`diagnostics/navigation.py`, `CLASSES_PER_GRADE = 4`) but has never modelled groups. Groups are **derived, not stored**, exactly like classes: a variant's group is a fact about where its letter sits in `VARIANTS`. Class 1 is `A B C D`; its groups are `A B` and `C D`.

### 0.2 What must be true within a group

| # | Invariant | Status today |
|---|---|---|
| G1 | Both variants use the **same two audio clips** (one recording plays in the room) | **0 of 24 hold** — 24/24 mismatch |
| G2 | The two variants' **listening questions differ** | impossible today — one question set per clip |
| G3 | No **shared speaking prompt** | 14 of 24 hold — 10 leak |
| G4 | No **shared reading passage** | 24 of 24 hold (by luck, not by rule) |

Re-verified directly against `db.sqlite3` on 2026-08-31, not assumed:

```
groups audio MISMATCH: 24  MATCH: 0
groups with SHARED speaking prompt: 10 of 24
groups sharing READING passage: 0 of 24
```

G1 is the core defect: `allocation.py` gives every paper its own independent clip pair, so as built each room would need two different recordings playing at once.

G3's cause is `diagnostics/constants.py:61` — `REUSE_CAPS` is scoped **per grade**, so nothing stops two same-room papers drawing the same prompt. G4 holds only because the passage index happens not to collide on adjacent variants; a test must pin it.

### 0.3 The sequencing trap

**Pairing the audio per group without first giving each clip a second question set makes the two variants in a group byte-identical listening papers — worse than today.** G2 must land with or before G1.

This is why Part 4 (content) gates Part 5 (allocation). Do not reorder them.

### 0.4 Arithmetic

Once audio is shared **per group** rather than per variant, a grade needs 8 clip pairs, not 16.

- **Rotating (text) clips:** 15 in the bank, 8 groups per grade. Each group takes one, so 8 distinct clips and no reuse within a grade at all. Each clip a group uses is counted **twice** by `Paper.shared_components()` (once per paper), so `REUSE_CAPS["rotating_clip"] = 2` is exactly consumed by a single group. The cap value does not change; its meaning does — it now means "one group", enforced by the new invariant that a rotating clip's uses within a grade all fall inside one group.
- **Picture clips:** 5 in the bank, 8 groups per grade. `8 groups x 2 papers = 16 uses` across 5 clips at cap 4, so 3 of the 5 clips serve 2 groups each and 2 serve 1 group. `REUSE_CAPS["picture_clip"] = 4` is unchanged and still exactly right.
- **Question sets:** every clip needs 2 sets of 5. Rotating clips: `15 x 5 = 75` new text questions to author. Picture clips: items 6 and 7 of each recording were recorded but never turned into questions — 10 new items, already composited.

### 0.5 The picture-clip residual — accepted, bounded, not solved

Each picture recording contains **seven** items. Two sets of five drawn from seven overlap by three (`5 + 5 - 7 = 3`). So for a picture clip, the two variants in a group share 3 of their 5 picture questions. Additionally, 3 of the 5 picture clips serve 2 groups each per grade, so those two groups see the same two sets.

**This is accepted by design, not a bug to fix.** There is no more recorded picture audio; solving it would mean commissioning new recordings. The two groups sharing a clip sit at **different times**, so the exposure is the same as what the bank already tolerates across classes today. The within-group 3/5 overlap is a genuine narrowing versus a fully distinct set, and it is bounded: the rotating clip in the same paper is fully distinct, so a group's two variants always differ on at least 5 of their 10 listening questions, and on 7 of 10 in the worst picture case.

Part 8 requires this to be written up in `README.md` so it is a documented limitation rather than folklore.

### 0.6 Content authored but not yet wired in

- **All 20 clip transcripts** in `media/diagnostics/audio/transcripts-full.md` (40.5 KB, confirmed present). The checked-in `Transcripts.docx` holds only clips 1-10; **clips 11-20 exist only in this markdown file**. Treat it as irreplaceable — do not let a task overwrite it.
- **All 10 new picture-clip images** at `media/diagnostics/listening/clip-{01,05,09,13,15}-q{6,7}.jpg` (confirmed: 35 jpgs present = 25 existing + 10 new), same 1080x330 3-panel A/B/C geometry. Raw pre-composite crops in `media/diagnostics/listening/raw-crops/`.
- **Answer key for the 10 new picture items:**

  | Clip | Q6 | Q7 |
  |---|---|---|
  | 1 | **B** (burger bar) | **C** (sailing) |
  | 5 | **B** (2 cases + bag) | **C** (cliff-top group) |
  | 9 | **A** (plain tie) | **C** (1:55) |
  | 13 | **A** (toothpaste) | **A** (hat) |
  | 15 | **A** (dishwasher) | **A** (cloudy) |

- **NOT yet authored:** the 75 new text questions (5 x 15 rotating clips). Transcripts are ready. See Part 4B.
- **Constraint on all new authored content: B1 CEFR ceiling.** No vocabulary or structure above B1.

### 0.7 Four stem bugs found while reading transcripts

Confirmed verbatim in the live DB:

| Clip | Q | Current stem | Fix |
|---|---|---|---|
| 1 | 4 | `What will the girl take with her on holiday?` | girl to boy, her to him (transcript: the **boy** is packing) |
| 6 | 5 | `What does the festival programme offer at lckworth?` | `lckworth` to `Ickworth` |
| 13 | 3 | `Why will drives have problems this morning?` | `drives` to `drivers` |
| 5 | 4 | `Which pictures shows what happened?` | `pictures` to `picture` |

These are wrong regardless of this redesign and ship first, in Part 1.

### 0.8 Two consequences to plan around

1. **`KeyVerification` sign-off will lapse.** `current_fingerprint()` (`diagnostics/models/content.py:220`) hashes every `(clip number, position, answer)`. Adding 85 questions changes the hash, so `is_signed_off()` goes false and a human must re-verify. This is correct behaviour — do not work around it. The fingerprint must also gain the set number, or set 1 Q3 and set 2 Q3 collide in the digest.
   *Note: the Part 1 stem fixes do NOT lapse the sign-off — the fingerprint covers answers, not stems.*
2. **All 48 papers get new listening content.** Anything already printed or downloaded is superseded. Part 8 covers the re-issue.

### 0.9 One correction to the brief

The brief assumed keeping `Paper.listening_clip_1/2` as read-only properties means `rendering.py` and `export.py` need no changes. **`export.py` needs none** (it consumes the plain dicts from `paper_sections`), but **`rendering.py` does**: `_clip_section()` at `diagnostics/rendering.py:142` reads `clip.questions`, and after the migration `AudioClip` no longer has a `questions` relation — questions hang off the set. `_clip_section` must take the set. This is a small change (Part 3, Task 3.7) and it keeps the `paper_sections` output shape identical, so `export.py`, `views.py:_annotate_for_display` and both templates stay untouched.

### 0.10 File structure

| File | Change | Responsibility after |
|---|---|---|
| `diagnostics/navigation.py` | modify | class **and** group derivation from `VARIANTS` |
| `diagnostics/constants.py` | modify | adds `STEM_CORRECTIONS`; `REUSE_CAPS` values unchanged |
| `diagnostics/models/content.py` | modify | adds `ListeningQuestionSet`; `ListeningQuestion` re-parented; fingerprint set-aware |
| `diagnostics/models/paper.py` | modify | `listening_set_1/2` FKs plus `listening_clip_1/2` compat properties |
| `diagnostics/models/__init__.py` | modify | export `ListeningQuestionSet` |
| `diagnostics/allocation.py` | modify | group-aware allocation, returns an `Allocation` record |
| `diagnostics/sampling.py` | modify | hard group-partner exclusion for speaking |
| `diagnostics/verification.py` | modify | adds `find_group_violations()` |
| `diagnostics/rendering.py` | modify | `_clip_section` takes a set |
| `diagnostics/admin.py` | modify | set inline under clip, question inline under set |
| `diagnostics/management/commands/build_papers.py` | modify | writes set FKs |
| `diagnostics/management/commands/check_papers.py` | modify | runs group checks |
| `diagnostics/management/commands/import_listening.py` | modify | writes into set 1, applies stem corrections |
| `diagnostics/management/commands/load_listening_set_2.py` | **create** | loads set 2 from the authored JSON |
| `diagnostics/authored/listening_sets.py` | **create** | validates the set-2 payload |
| `diagnostics/authored/listening_set_2.json` | **create** | the 85 authored set-2 questions |
| `diagnostics/migrations/0013...0016` | **create** | four ordered migrations, see Part 3 |
| `diagnostics/tests/test_navigation.py` | modify | group tests |
| `diagnostics/tests/test_models_listening.py` | modify | set model tests |
| `diagnostics/tests/test_allocation.py` | modify | group allocation tests |
| `diagnostics/tests/test_sampling.py` | modify | group exclusion tests |
| `diagnostics/tests/test_verification_groups.py` | **create** | the four G-invariant tests |
| `diagnostics/tests/test_load_listening_set_2.py` | **create** | loader tests |

### 0.11 Execution order and the gate

```
Part 1  stem fixes            -+ independent, ship anytime
Part 2  navigation groups     -+ pure, no DB
Part 3  schema migration      -+ all papers stay on set 1, behaviour unchanged
Part 4  content load          -+ 4A picture (ready now) - 4B text (needs authoring)
        ====== HARD GATE: every clip must have 2 full sets before Part 5 ======
Part 5  allocation groups      <- flips G1 on
Part 6  sampling exclusion     <- fixes G3
Part 7  verification checks    <- proves G1-G4
Part 8  rebuild, re-issue, docs
```

**Parts 1-4 are all shippable to main on their own and change nothing a student sees.** Part 5 is the flip. The 75-question authoring workstream (Part 4B) runs in parallel with Parts 1-3 and only has to land before Part 5.

**Baseline:** 836 tests passing on `main` (last full run). Every Part below ends green. Run the suite with:

```bash
python manage.py test
```

---

## Part 1: Fix the four stem bugs

Independent of everything else. Ships on its own.

The stems live in the DB but originate from `import_listening`, which re-derives them from the client's source `.md` on every run. A DB-only fix would be silently undone by the next import, so the correction map lives in `constants.py`, is applied by the importer, **and** is replayed once over the existing rows by a data migration.

### Task 1.1: Add the correction map

**Files:**
- Modify: `diagnostics/constants.py` (append at end of file)
- Test: `diagnostics/tests/test_constants.py`

- [ ] **Step 1: Write the failing test**

Append to `diagnostics/tests/test_constants.py`:

```python
class StemCorrectionTests(SimpleTestCase):
    """The client's source .md has four typos we correct on import. Keyed by
    (clip number, position) so a correction can never be applied to the wrong
    question if the source is re-split."""

    def test_all_four_corrections_are_present(self):
        from diagnostics.constants import STEM_CORRECTIONS
        self.assertEqual(
            sorted(STEM_CORRECTIONS), [(1, 4), (5, 4), (6, 5), (13, 3)]
        )

    def test_each_correction_names_the_wrong_text_and_the_right_text(self):
        from diagnostics.constants import STEM_CORRECTIONS
        for slot, (wrong, right) in STEM_CORRECTIONS.items():
            self.assertNotEqual(wrong, right, slot)
            self.assertTrue(wrong.strip(), slot)
            self.assertTrue(right.strip(), slot)

    def test_the_boy_packing_typo_is_corrected(self):
        from diagnostics.constants import STEM_CORRECTIONS
        wrong, right = STEM_CORRECTIONS[(1, 4)]
        self.assertEqual(wrong, "What will the girl take with her on holiday?")
        self.assertEqual(right, "What will the boy take with him on holiday?")
```

If `SimpleTestCase` is not already imported at the top of that file, add `from django.test import SimpleTestCase`.

- [ ] **Step 2: Run the test to verify it fails**

```bash
python manage.py test diagnostics.tests.test_constants.StemCorrectionTests -v 2
```

Expected: FAIL — `ImportError: cannot import name 'STEM_CORRECTIONS'`.

- [ ] **Step 3: Add the map**

Append to `diagnostics/constants.py`:

```python
#: Four typos in the client's source .md, found while reading the full
#: transcripts on 2026-08-31. Keyed by (clip number, question position) so a
#: correction cannot land on the wrong question if the source is re-split;
#: the "wrong" half is asserted before replacement so a corrected source file
#: silently stops applying the fix instead of clobbering new text.
#:
#: Clip 1 Q4 is a content error, not a typo: the transcript has the *boy*
#: packing for the holiday. The other three are spelling/agreement slips.
STEM_CORRECTIONS = {
    (1, 4): (
        "What will the girl take with her on holiday?",
        "What will the boy take with him on holiday?",
    ),
    (5, 4): (
        "Which pictures shows what happened?",
        "Which picture shows what happened?",
    ),
    (6, 5): (
        "What does the festival programme offer at lckworth?",
        "What does the festival programme offer at Ickworth?",
    ),
    (13, 3): (
        "Why will drives have problems this morning?",
        "Why will drivers have problems this morning?",
    ),
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python manage.py test diagnostics.tests.test_constants -v 2
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add diagnostics/constants.py diagnostics/tests/test_constants.py
git commit -m "Record the four listening stem corrections found in the transcripts"
```

### Task 1.2: Apply corrections on import

**Files:**
- Modify: `diagnostics/management/commands/import_listening.py:115-124`
- Test: `diagnostics/tests/test_import_listening.py`

- [ ] **Step 1: Write the failing test**

Append to the existing import test class in `diagnostics/tests/test_import_listening.py` (it already builds a full import; reuse its fixture setup):

```python
    def test_known_source_typos_are_corrected_on_import(self):
        from diagnostics.constants import STEM_CORRECTIONS
        for (number, position), (wrong, right) in STEM_CORRECTIONS.items():
            question = ListeningQuestion.objects.get(
                clip__number=number, position=position
            )
            self.assertEqual(question.stem, right, f"clip {number} Q{position}")
            self.assertNotEqual(question.stem, wrong)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python manage.py test diagnostics.tests.test_import_listening -v 2
```

Expected: FAIL — the stems still hold the source typos.

- [ ] **Step 3: Apply the map in the importer**

In `diagnostics/management/commands/import_listening.py`, extend the constants import:

```python
from diagnostics.constants import (
    CLIP_TASK_TYPES, IMAGE_SLOTS, LETTER_ANSWER_TYPES, STEM_CORRECTIONS, TaskType,
)
```

Add this module-level helper just above `class Command`:

```python
def correct_stem(clip_number, position, stem):
    """Replace a known source typo, but only if the typo is still there.

    Asserting the wrong text before replacing means a fixed source .md stops
    triggering the correction rather than overwriting whatever replaced it.
    """
    correction = STEM_CORRECTIONS.get((clip_number, position))
    if correction is None:
        return stem
    wrong, right = correction
    return right if stem.strip() == wrong else stem
```

Then in `_import_clip`, change the `ListeningQuestion.objects.create(...)` call so the stem passes through it:

```python
            question = ListeningQuestion.objects.create(
                clip=clip,
                position=position,
                stem=correct_stem(number, position, item["stem"]),
                options=item["options"],
                answer=answer,
                acceptable_answers=alts,
            )
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python manage.py test diagnostics.tests.test_import_listening -v 2
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add diagnostics/management/commands/import_listening.py diagnostics/tests/test_import_listening.py
git commit -m "Correct the four known source stem typos during listening import"
```

### Task 1.3: Repair the rows already in the database

**Files:**
- Create: `diagnostics/migrations/0013_correct_listening_stems.py`

- [ ] **Step 1: Write the migration**

```python
"""Replay the four stem corrections over rows imported before the importer
learned about them. Idempotent and reversible: each row is matched on the
exact wrong text, so a row already carrying the right text is left alone."""

from django.db import migrations

from diagnostics.constants import STEM_CORRECTIONS


def _swap(apps, forwards):
    ListeningQuestion = apps.get_model("diagnostics", "ListeningQuestion")
    for (number, position), (wrong, right) in STEM_CORRECTIONS.items():
        source, target = (wrong, right) if forwards else (right, wrong)
        ListeningQuestion.objects.filter(
            clip__number=number, position=position, stem=source
        ).update(stem=target)


def apply_corrections(apps, schema_editor):
    _swap(apps, forwards=True)


def undo_corrections(apps, schema_editor):
    _swap(apps, forwards=False)


class Migration(migrations.Migration):

    dependencies = [("diagnostics", "0012_alter_generationevent_export_format")]

    operations = [
        migrations.RunPython(apply_corrections, undo_corrections),
    ]
```

- [ ] **Step 2: Run it**

```bash
python manage.py migrate diagnostics
```

Expected: `Applying diagnostics.0013_correct_listening_stems... OK`

- [ ] **Step 3: Verify the four rows changed**

```bash
python manage.py shell -c "from diagnostics.models import ListeningQuestion; print([ListeningQuestion.objects.get(clip__number=n, position=p).stem for n, p in [(1,4),(5,4),(6,5),(13,3)]])"
```

Expected: all four corrected — `boy ... him`, `Which picture shows`, `at Ickworth`, `Why will drivers`.

- [ ] **Step 4: Confirm the key sign-off did NOT lapse**

The fingerprint covers answers, not stems, so this migration must leave it intact.

```bash
python manage.py shell -c "from diagnostics.models import KeyVerification; print('signed off:', KeyVerification.is_signed_off())"
```

Expected: unchanged from before the migration. If it flipped to `False`, something touched an answer — stop and investigate.

- [ ] **Step 5: Run the full suite**

```bash
python manage.py test
```

Expected: 836+ tests, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add diagnostics/migrations/0013_correct_listening_stems.py
git commit -m "Repair the four stem typos in already-imported listening questions"
```

---
## Part 2: The group model in navigation.py

Pure Python, no database, no behaviour change. Groups are derived from `VARIANTS` the same way classes are, so the two can never drift apart.

### Task 2.1: Group constants and derivation

**Files:**
- Modify: `diagnostics/navigation.py`
- Test: `diagnostics/tests/test_navigation.py`

- [ ] **Step 1: Write the failing tests**

Append to `diagnostics/tests/test_navigation.py`:

```python
from diagnostics.navigation import (
    GROUPS_PER_CLASS,
    GROUPS_PER_GRADE,
    GROUP_NUMBERS,
    VARIANTS_PER_GROUP,
    group_for_variant,
    group_span,
    groups_for_class,
    variants_for_group,
)


class GroupShapeTests(TestCase):
    """A group is one sitting: one room, one time, one recording. Two groups
    make a class, so eight groups make a grade."""

    def test_two_groups_per_class_of_two_papers_each(self):
        self.assertEqual(GROUPS_PER_CLASS, 2)
        self.assertEqual(VARIANTS_PER_GROUP, 2)

    def test_eight_groups_per_grade(self):
        self.assertEqual(GROUPS_PER_GRADE, 8)
        self.assertEqual(GROUP_NUMBERS, (1, 2, 3, 4, 5, 6, 7, 8))

    def test_every_group_is_the_same_size(self):
        for number in GROUP_NUMBERS:
            self.assertEqual(len(variants_for_group(number)), VARIANTS_PER_GROUP)

    def test_groups_partition_the_variants_with_none_left_over(self):
        seen = [v for n in GROUP_NUMBERS for v in variants_for_group(n)]
        self.assertEqual(seen, list(VARIANTS))


class GroupSequencingTests(TestCase):
    def test_group_one_is_the_first_two_letters(self):
        self.assertEqual(variants_for_group(1), ("A", "B"))

    def test_each_group_takes_the_next_two(self):
        self.assertEqual(variants_for_group(2), ("C", "D"))
        self.assertEqual(variants_for_group(3), ("E", "F"))
        self.assertEqual(variants_for_group(8), ("O", "P"))

    def test_span_labels_the_pair(self):
        self.assertEqual(group_span(1), "A-B")
        self.assertEqual(group_span(8), "O-P")


class GroupClassNestingTests(TestCase):
    """A group never straddles two classes - the split is 4 into 2+2."""

    def test_each_class_holds_exactly_two_groups(self):
        for number in CLASS_NUMBERS:
            self.assertEqual(len(groups_for_class(number)), GROUPS_PER_CLASS)

    def test_class_one_holds_groups_one_and_two(self):
        self.assertEqual(groups_for_class(1), (1, 2))
        self.assertEqual(groups_for_class(4), (7, 8))

    def test_a_group_variants_all_belong_to_one_class(self):
        for number in GROUP_NUMBERS:
            classes = {class_for_variant(v) for v in variants_for_group(number)}
            self.assertEqual(len(classes), 1, f"group {number} straddles {classes}")


class GroupReverseLookupTests(TestCase):
    def test_variant_maps_back_to_its_own_group(self):
        for number in GROUP_NUMBERS:
            for letter in variants_for_group(number):
                self.assertEqual(group_for_variant(letter), number)

    def test_unknown_variant_is_rejected(self):
        with self.assertRaises(ValueError):
            group_for_variant("Z")

    def test_group_outside_the_range_is_rejected(self):
        for number in (0, 9, -1):
            with self.assertRaises(ValueError):
                variants_for_group(number)

    def test_class_outside_the_range_is_rejected(self):
        for number in (0, 5, -1):
            with self.assertRaises(ValueError):
                groups_for_class(number)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python manage.py test diagnostics.tests.test_navigation -v 2
```

Expected: FAIL — `ImportError: cannot import name 'GROUPS_PER_CLASS'`.

- [ ] **Step 3: Add the group derivation**

Append to `diagnostics/navigation.py` (below `variants_for_class`/`class_for_variant`, above `display_name_for`):

```python
#: Groups per class. Each class sits the diagnostic in two sittings, and a
#: sitting is one room at one time playing one recording - which is why the
#: group, not the class and not the variant, is the unit the audio is
#: allocated to. Fixed by the school's timetable, like CLASSES_PER_GRADE.
GROUPS_PER_CLASS = 2

if VARIANTS_PER_CLASS % GROUPS_PER_CLASS:
    raise ValueError(
        f"{VARIANTS_PER_CLASS} variants per class do not divide evenly into "
        f"{GROUPS_PER_CLASS} groups; a group that straddles two classes would "
        f"put papers from different class packs in the same room."
    )

#: Derived, so the constants cannot disagree.
VARIANTS_PER_GROUP = VARIANTS_PER_CLASS // GROUPS_PER_CLASS
GROUPS_PER_GRADE = CLASSES_PER_GRADE * GROUPS_PER_CLASS

#: 1-based and numbered straight through the grade (1-8), not restarted per
#: class. A group number is the natural key for "which sitting", and the
#: allocator indexes clip pools by it, so a globally unique number keeps that
#: arithmetic to one modulo instead of a class/group pair.
GROUP_NUMBERS = tuple(range(1, GROUPS_PER_GRADE + 1))


def variants_for_group(number: int) -> tuple[str, ...]:
    """The variant letters sitting together in group `number` (1-based).

    Raises ValueError outside GROUP_NUMBERS rather than returning an empty
    tuple, for the same reason variants_for_class does: a request for group 9
    is a bad input, not a sitting that happens to have no papers.
    """
    if number not in GROUP_NUMBERS:
        raise ValueError(
            f"Group {number} does not exist; grades run 1-{GROUPS_PER_GRADE}."
        )
    start = (number - 1) * VARIANTS_PER_GROUP
    return VARIANTS[start:start + VARIANTS_PER_GROUP]


def group_for_variant(variant: str) -> int:
    """Which group a variant letter sits in (1-based)."""
    try:
        position = VARIANTS.index(variant)
    except ValueError:
        raise ValueError(f"{variant!r} is not one of the {len(VARIANTS)} variants.") from None
    return position // VARIANTS_PER_GROUP + 1


def groups_for_class(number: int) -> tuple[int, ...]:
    """The group numbers belonging to class `number` (1-based).

    Derived from the class's own variants rather than from arithmetic on the
    class number, so the nesting stays correct if either split changes.
    """
    letters = variants_for_class(number)
    seen = []
    for letter in letters:
        group = group_for_variant(letter)
        if group not in seen:
            seen.append(group)
    return tuple(seen)


def group_span(number: int) -> str:
    """A short label for the sitting, e.g. "A-B", to match variant_span."""
    letters = variants_for_group(number)
    return f"{letters[0]}-{letters[-1]}"


def partner_variant(variant: str) -> str:
    """The other variant sitting in the same room at the same time.

    Only meaningful while VARIANTS_PER_GROUP is 2; raises if a future widening
    breaks that assumption rather than silently returning one of several
    partners. Callers that must handle any group size should use
    variants_for_group(group_for_variant(v)) instead.
    """
    if VARIANTS_PER_GROUP != 2:
        raise ValueError(
            f"partner_variant assumes 2 variants per group, not {VARIANTS_PER_GROUP}."
        )
    first, second = variants_for_group(group_for_variant(variant))
    return second if variant == first else first
```

- [ ] **Step 4: Add the partner test**

Append to `diagnostics/tests/test_navigation.py`:

```python
class PartnerVariantTests(TestCase):
    def test_partner_is_the_other_variant_in_the_group(self):
        from diagnostics.navigation import partner_variant
        self.assertEqual(partner_variant("A"), "B")
        self.assertEqual(partner_variant("B"), "A")
        self.assertEqual(partner_variant("P"), "O")

    def test_partner_is_symmetric_for_every_variant(self):
        from diagnostics.navigation import partner_variant
        for letter in VARIANTS:
            self.assertEqual(partner_variant(partner_variant(letter)), letter)

    def test_a_variant_is_never_its_own_partner(self):
        from diagnostics.navigation import partner_variant
        for letter in VARIANTS:
            self.assertNotEqual(partner_variant(letter), letter)
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python manage.py test diagnostics.tests.test_navigation -v 2
```

Expected: PASS, all group tests green.

- [ ] **Step 6: Run the full suite**

```bash
python manage.py test
```

Expected: 836+ tests, 0 failures. Nothing else imports these names yet.

- [ ] **Step 7: Commit**

```bash
git add diagnostics/navigation.py diagnostics/tests/test_navigation.py
git commit -m "Derive exam groups from VARIANTS alongside class packs"
```

---

## Part 3: The ListeningQuestionSet schema

Four migrations, in order. **Every paper stays on set 1 throughout**, so nothing a student sees changes in this Part — it only creates the capability.

Migration ordering matters because `unique(clip, position)` must be gone before a second set can exist, and `Paper.listening_set_1/2` must be backfilled before `listening_clip_1/2` can be dropped.

```
0014  add ListeningQuestionSet; add nullable ListeningQuestion.question_set
0015  data: one set (number=1) per clip; point every question at it
0016  make question_set non-null; drop ListeningQuestion.clip; swap constraints
0017  add nullable Paper.listening_set_1/2; backfill; make non-null; drop listening_clip_1/2
```

### Task 3.1: The model

**Files:**
- Modify: `diagnostics/models/content.py:20-70`
- Modify: `diagnostics/models/__init__.py`
- Test: `diagnostics/tests/test_models_listening.py`

- [ ] **Step 1: Write the failing tests**

Append to `diagnostics/tests/test_models_listening.py`:

```python
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError

from diagnostics.models import AudioClip, ListeningQuestion, ListeningQuestionSet


class ListeningQuestionSetTests(TestCase):
    def setUp(self):
        self.clip = AudioClip.objects.create(number=1, task_type="picture")

    def test_a_clip_can_carry_two_sets(self):
        first = ListeningQuestionSet.objects.create(clip=self.clip, number=1)
        second = ListeningQuestionSet.objects.create(clip=self.clip, number=2)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(self.clip.question_sets.count(), 2)

    def test_the_same_set_number_cannot_repeat_on_one_clip(self):
        ListeningQuestionSet.objects.create(clip=self.clip, number=1)
        with self.assertRaises(IntegrityError):
            ListeningQuestionSet.objects.create(clip=self.clip, number=1)

    def test_set_number_is_bounded_to_the_two_sets_that_exist(self):
        question_set = ListeningQuestionSet(clip=self.clip, number=3)
        with self.assertRaises(ValidationError):
            question_set.full_clean()

    def test_str_names_the_clip_and_the_set(self):
        question_set = ListeningQuestionSet.objects.create(clip=self.clip, number=2)
        self.assertEqual(str(question_set), "Clip 1 set 2")


class ListeningQuestionParentTests(TestCase):
    """Questions hang off the set, not the clip, so the same recording can
    carry two different papers' questions."""

    def setUp(self):
        self.clip = AudioClip.objects.create(number=1, task_type="picture")
        self.set_one = ListeningQuestionSet.objects.create(clip=self.clip, number=1)
        self.set_two = ListeningQuestionSet.objects.create(clip=self.clip, number=2)

    def test_position_repeats_across_sets_on_the_same_clip(self):
        ListeningQuestion.objects.create(
            question_set=self.set_one, position=1, stem="a", answer="A"
        )
        ListeningQuestion.objects.create(
            question_set=self.set_two, position=1, stem="b", answer="B"
        )
        self.assertEqual(ListeningQuestion.objects.filter(position=1).count(), 2)

    def test_position_still_cannot_repeat_within_one_set(self):
        ListeningQuestion.objects.create(
            question_set=self.set_one, position=1, stem="a", answer="A"
        )
        with self.assertRaises(IntegrityError):
            ListeningQuestion.objects.create(
                question_set=self.set_one, position=1, stem="b", answer="B"
            )

    def test_question_reaches_its_clip_through_the_set(self):
        question = ListeningQuestion.objects.create(
            question_set=self.set_two, position=1, stem="a", answer="A"
        )
        self.assertEqual(question.clip, self.clip)

    def test_str_names_clip_set_and_position(self):
        question = ListeningQuestion.objects.create(
            question_set=self.set_two, position=3, stem="a", answer="A"
        )
        self.assertEqual(str(question), "Clip 1 set 2 Q3")

    def test_deleting_a_set_takes_its_questions(self):
        ListeningQuestion.objects.create(
            question_set=self.set_two, position=1, stem="a", answer="A"
        )
        self.set_two.delete()
        self.assertEqual(ListeningQuestion.objects.count(), 0)
```

Existing tests in this file create questions with `clip=self.clip`; update every such call to `question_set=<a set>`. The existing `ListeningQuestionTests` class should get a `setUp` that also creates `ListeningQuestionSet.objects.create(clip=self.clip, number=1)`.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python manage.py test diagnostics.tests.test_models_listening -v 2
```

Expected: FAIL — `ImportError: cannot import name 'ListeningQuestionSet'`.

- [ ] **Step 3: Add the model and re-parent the question**

In `diagnostics/models/content.py`, add `SETS_PER_CLIP` to the constants import line at the top:

```python
from diagnostics.constants import (
    MAX_PASSAGE_WORDS, MIN_PASSAGE_WORDS, SETS_PER_CLIP, TaskType,
)
```

Add to `diagnostics/constants.py` (below `PICTURE_CLIPS`):

```python
#: Question sets per clip. Two variants sit in one room hearing one
#: recording, so one recording must carry two different question papers -
#: which is exactly two sets, no more. Picture clips can only just support
#: this (seven recorded items against 5 + 5 slots, so 3 items appear in both
#: sets); a third set is arithmetically impossible without new audio.
SETS_PER_CLIP = 2
```

Insert `ListeningQuestionSet` into `diagnostics/models/content.py`, between `AudioClip` and `ListeningQuestion`:

```python
class ListeningQuestionSet(models.Model):
    """One paper's worth of questions about one recording.

    The layer this model adds is what lets the two variants sitting in the
    same room hear the same audio and answer different questions. Before it,
    ListeningQuestion hung off AudioClip directly under unique(clip,
    position), so a clip had exactly one set of five questions and pairing
    the audio per group would have produced two byte-identical papers.

    Two sets per clip, no more (SETS_PER_CLIP). The rotating clips get two
    fully distinct sets; the five picture clips only have seven recorded
    items between their two sets, so three items are shared - an accepted,
    documented limitation, not something a third set could fix.
    """

    clip = models.ForeignKey(
        AudioClip, on_delete=models.CASCADE, related_name="question_sets"
    )
    number = models.PositiveSmallIntegerField(
        validators=_position_validators(SETS_PER_CLIP),
        help_text="1 or 2. Which of the recording's two question papers this is.",
    )

    class Meta:
        ordering = ["clip__number", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["clip", "number"], name="unique_listening_set_number"
            )
        ]

    def __str__(self):
        return f"Clip {self.clip.number} set {self.number}"
```

Replace the `clip` field, `Meta` and `__str__` on `ListeningQuestion`:

```python
class ListeningQuestion(models.Model):
    question_set = models.ForeignKey(
        ListeningQuestionSet, on_delete=models.CASCADE, related_name="questions"
    )
    position = models.PositiveSmallIntegerField(validators=_position_validators(5))
```

(the `stem`, `options`, `image`, `answer`, `acceptable_answers` fields are unchanged)

```python
    class Meta:
        ordering = ["question_set__clip__number", "question_set__number", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["question_set", "position"], name="unique_listening_position"
            )
        ]

    def __str__(self):
        return f"{self.question_set} Q{self.position}"

    @property
    def clip(self):
        """The recording this question is about.

        Kept as a read-only property because the extraction and verification
        code reads `question.clip.number` in a dozen places and none of it
        cares which set the question came from.
        """
        return self.question_set.clip
```

Update `KeyVerification.current_fingerprint` in the same file:

```python
    @staticmethod
    def current_fingerprint():
        """Hash every answer in the bank, set number included.

        The set number is part of the key: without it, clip 3 set 1 Q2 and
        clip 3 set 2 Q2 hash into the same slot and a swapped pair of answers
        between the two sets would leave the fingerprint unchanged.

        Adding the second sets necessarily changes this digest, so an
        existing sign-off lapses and must be re-done by a human. That is the
        intended behaviour, not a bug to route around.
        """
        rows = ListeningQuestion.objects.order_by(
            "question_set__clip__number", "question_set__number", "position"
        ).values_list(
            "question_set__clip__number", "question_set__number", "position", "answer"
        )
        digest = hashlib.sha256()
        for clip_number, set_number, position, answer in rows:
            digest.update(f"{clip_number}:{set_number}:{position}:{answer}\n".encode("utf-8"))
        return digest.hexdigest()
```

Export the new model from `diagnostics/models/__init__.py`:

```python
from diagnostics.models.content import (
    AudioClip, KeyVerification, ListeningQuestion, ListeningQuestionSet,
    ReadingPassage, ReadingQuestion, ReadingSubtype,
    SpeakingPrompt, SpeakingRubric, SpeakingTask,
    WritingQuestion, WritingSubtype,
)

__all__ = [
    "AudioClip", "KeyVerification", "ListeningQuestion", "ListeningQuestionSet",
    "ReadingPassage", "ReadingQuestion", "ReadingSubtype",
    "SpeakingPrompt", "SpeakingRubric", "SpeakingTask",
    "WritingQuestion", "WritingSubtype",
]
```

- [ ] **Step 4: Commit the model only (migrations come next)**

Do not run the suite yet — it cannot pass until the migrations exist.

```bash
git add diagnostics/models/content.py diagnostics/models/__init__.py diagnostics/constants.py diagnostics/tests/test_models_listening.py
git commit -m "Add ListeningQuestionSet between AudioClip and ListeningQuestion"
```

### Task 3.2: Migration 0014 — create the set, add a nullable link

**Files:**
- Create: `diagnostics/migrations/0014_listeningquestionset.py`

- [ ] **Step 1: Write the migration by hand**

Autogeneration will try to drop `clip` and add a non-null `question_set` in one step, which cannot work on populated data. Write it explicitly:

```python
"""Step 1 of 4: create ListeningQuestionSet and a nullable link to it.

Split into four migrations because the existing rows have to be carried
across: the clip -> question_set re-parenting cannot be done in one operation
without either losing every question or failing the NOT NULL check.
"""

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("diagnostics", "0013_correct_listening_stems")]

    operations = [
        migrations.CreateModel(
            name="ListeningQuestionSet",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("number", models.PositiveSmallIntegerField(
                    help_text="1 or 2. Which of the recording's two question papers this is.",
                    validators=[
                        django.core.validators.MinValueValidator(1),
                        django.core.validators.MaxValueValidator(2),
                    ],
                )),
                ("clip", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="question_sets",
                    to="diagnostics.audioclip",
                )),
            ],
            options={"ordering": ["clip__number", "number"]},
        ),
        migrations.AddConstraint(
            model_name="listeningquestionset",
            constraint=models.UniqueConstraint(
                fields=("clip", "number"), name="unique_listening_set_number"
            ),
        ),
        migrations.AddField(
            model_name="listeningquestion",
            name="question_set",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="questions",
                to="diagnostics.listeningquestionset",
            ),
        ),
    ]
```

- [ ] **Step 2: Run it**

```bash
python manage.py migrate diagnostics 0014
```

Expected: `Applying diagnostics.0014_listeningquestionset... OK`

- [ ] **Step 3: Commit**

```bash
git add diagnostics/migrations/0014_listeningquestionset.py
git commit -m "Create the ListeningQuestionSet table and a nullable question link"
```

### Task 3.3: Migration 0015 — backfill set 1

**Files:**
- Create: `diagnostics/migrations/0015_backfill_listening_set_one.py`

- [ ] **Step 1: Write the data migration**

```python
"""Step 2 of 4: give every clip a set 1 and move its questions onto it.

Reversible so the whole four-migration stack can be unwound on a dev box:
reversing puts each question's clip_id back and deletes the sets.
"""

from django.db import migrations


def create_first_sets(apps, schema_editor):
    AudioClip = apps.get_model("diagnostics", "AudioClip")
    ListeningQuestionSet = apps.get_model("diagnostics", "ListeningQuestionSet")
    ListeningQuestion = apps.get_model("diagnostics", "ListeningQuestion")

    for clip in AudioClip.objects.all():
        question_set, _ = ListeningQuestionSet.objects.get_or_create(
            clip=clip, number=1
        )
        ListeningQuestion.objects.filter(clip=clip).update(question_set=question_set)

    orphans = ListeningQuestion.objects.filter(question_set__isnull=True).count()
    if orphans:
        raise RuntimeError(
            f"{orphans} listening questions have no clip and cannot be assigned "
            f"to a set; refusing to continue and leave them unreachable."
        )


def undo_first_sets(apps, schema_editor):
    ListeningQuestionSet = apps.get_model("diagnostics", "ListeningQuestionSet")
    ListeningQuestion = apps.get_model("diagnostics", "ListeningQuestion")

    for question in ListeningQuestion.objects.select_related("question_set"):
        question.clip_id = question.question_set.clip_id
        question.save(update_fields=["clip_id"])
    ListeningQuestionSet.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [("diagnostics", "0014_listeningquestionset")]

    operations = [migrations.RunPython(create_first_sets, undo_first_sets)]
```

- [ ] **Step 2: Run it**

```bash
python manage.py migrate diagnostics 0015
```

Expected: `Applying diagnostics.0015_backfill_listening_set_one... OK`

- [ ] **Step 3: Verify the backfill covered everything**

```bash
python manage.py shell -c "from diagnostics.models import *; print('sets', ListeningQuestionSet.objects.count(), 'orphans', ListeningQuestion.objects.filter(question_set__isnull=True).count())"
```

Expected: `sets 20 orphans 0`

- [ ] **Step 4: Commit**

```bash
git add diagnostics/migrations/0015_backfill_listening_set_one.py
git commit -m "Backfill one question set per clip and re-parent every question"
```

### Task 3.4: Migration 0016 — make it permanent

**Files:**
- Create: `diagnostics/migrations/0016_listeningquestion_drop_clip.py`

- [ ] **Step 1: Write the migration**

The old `unique(clip, position)` constraint must be removed **before** the column it references is dropped.

```python
"""Step 3 of 4: make question_set required and retire the direct clip link.

Order matters: the old unique(clip, position) constraint has to go before its
column does, and question_set can only become NOT NULL once 0015 has filled
every row.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("diagnostics", "0015_backfill_listening_set_one")]

    operations = [
        migrations.RemoveConstraint(
            model_name="listeningquestion",
            name="unique_listening_position",
        ),
        migrations.RemoveField(model_name="listeningquestion", name="clip"),
        migrations.AlterField(
            model_name="listeningquestion",
            name="question_set",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="questions",
                to="diagnostics.listeningquestionset",
            ),
        ),
        migrations.AlterModelOptions(
            name="listeningquestion",
            options={"ordering": ["question_set__clip__number",
                                  "question_set__number", "position"]},
        ),
        migrations.AddConstraint(
            model_name="listeningquestion",
            constraint=models.UniqueConstraint(
                fields=("question_set", "position"), name="unique_listening_position"
            ),
        ),
    ]
```

- [ ] **Step 2: Run it**

```bash
python manage.py migrate diagnostics 0016
```

Expected: `Applying diagnostics.0016_listeningquestion_drop_clip... OK`

- [ ] **Step 3: Confirm Django sees no further model drift**

```bash
python manage.py makemigrations diagnostics --check --dry-run
```

Expected: `No changes detected`. If it wants a migration, the hand-written ones do not match the models — fix the migration, not the model.

- [ ] **Step 4: Commit**

```bash
git add diagnostics/migrations/0016_listeningquestion_drop_clip.py
git commit -m "Require question_set and drop the direct clip link on listening questions"
```

### Task 3.5: Migration 0017 — papers point at sets

**Files:**
- Modify: `diagnostics/models/paper.py:41-47`
- Create: `diagnostics/migrations/0017_paper_listening_sets.py`
- Test: `diagnostics/tests/test_models_paper.py`

- [ ] **Step 1: Write the failing test**

Append to `diagnostics/tests/test_models_paper.py`:

```python
class PaperListeningSetTests(TestCase):
    """A paper points at two question sets. The old listening_clip_1/2 names
    survive as read-only properties, because a dozen call sites, two admin
    columns and the audio download view all only ever want the recording."""

    def setUp(self):
        self.picture = AudioClip.objects.create(number=1, task_type="picture")
        self.rotating = AudioClip.objects.create(number=2, task_type="mcq3")
        self.set_one = ListeningQuestionSet.objects.create(clip=self.picture, number=1)
        self.set_two = ListeningQuestionSet.objects.create(clip=self.rotating, number=2)
        self.passage = ReadingPassage.objects.create(
            label="R01", title="t", body=" ".join(["word"] * 200)
        )
        self.paper = Paper.objects.create(
            grade=9, variant="A",
            listening_set_1=self.set_one,
            listening_set_2=self.set_two,
            reading_passage=self.passage,
        )

    def test_listening_clip_properties_reach_through_the_set(self):
        self.assertEqual(self.paper.listening_clip_1, self.picture)
        self.assertEqual(self.paper.listening_clip_2, self.rotating)

    def test_shared_components_still_counts_the_clips_not_the_sets(self):
        keys = dict(self.paper.shared_components())
        self.assertIn("picture_clip", keys)
        self.assertIn("rotating_clip", keys)
        self.assertEqual(keys["picture_clip"], self.picture.pk)

    def test_two_sets_of_the_same_clip_is_rejected(self):
        other_set = ListeningQuestionSet.objects.create(clip=self.picture, number=2)
        self.paper.listening_set_2 = other_set
        with self.assertRaises(ValidationError):
            self.paper.clean()
```

Existing tests in this file construct papers with `listening_clip_1=`/`listening_clip_2=`; update every such call to build sets and pass `listening_set_1=`/`listening_set_2=`. Do the same in `diagnostics/tests/test_downloads.py:57`.

- [ ] **Step 2: Run to verify it fails**

```bash
python manage.py test diagnostics.tests.test_models_paper -v 2
```

Expected: FAIL — `Paper() got unexpected keyword arguments: 'listening_set_1'`.

- [ ] **Step 3: Change the model**

In `diagnostics/models/paper.py`, replace the two clip fields:

```python
    listening_set_1 = models.ForeignKey(
        ListeningQuestionSet, on_delete=models.PROTECT, related_name="papers_as_first"
    )
    listening_set_2 = models.ForeignKey(
        ListeningQuestionSet, on_delete=models.PROTECT, related_name="papers_as_second"
    )
```

Update the import at the top of the file:

```python
from diagnostics.models.content import (
    ListeningQuestionSet, ReadingPassage, SpeakingPrompt, WritingQuestion,
)
```

(`AudioClip` is no longer referenced by this module — drop it from the import.)

Add the compatibility properties immediately after `__str__`:

```python
    @property
    def listening_clip_1(self):
        """The first recording. Read-only: a paper chooses a question set,
        and the recording follows from it. Kept under the old name so the
        audio download view, the admin columns and the reuse-cap accounting
        do not all have to learn about sets to ask "which recording?"."""
        return self.listening_set_1.clip

    @property
    def listening_clip_2(self):
        return self.listening_set_2.clip
```

Update `clean()`'s first check to compare recordings, not sets — two different sets of the *same* recording would still mean one paper hearing one clip twice:

```python
    def clean(self):
        if self.listening_set_1_id and self.listening_set_2_id:
            if self.listening_set_1.clip_id == self.listening_set_2.clip_id:
                raise ValidationError(
                    {"listening_set_2": "A paper cannot use the same recording twice, "
                                        "even under a different question set."}
                )
```

`shared_components()` needs no change: it iterates `(self.listening_clip_1, self.listening_clip_2)`, which now resolves through the properties and still yields `AudioClip` objects.

- [ ] **Step 4: Write the migration**

```python
"""Step 4 of 4: point papers at question sets instead of recordings.

Nullable first, backfilled to each paper's existing clip at set 1, then made
required - the same carry-the-data-across shape as 0014-0016. Every paper
lands on set 1, so this migration changes no student-visible content; the
allocator starts issuing set 2 in a later phase.
"""

import django.db.models.deletion
from django.db import migrations, models


def point_papers_at_set_one(apps, schema_editor):
    Paper = apps.get_model("diagnostics", "Paper")
    ListeningQuestionSet = apps.get_model("diagnostics", "ListeningQuestionSet")

    first_sets = {
        question_set.clip_id: question_set.pk
        for question_set in ListeningQuestionSet.objects.filter(number=1)
    }
    for paper in Paper.objects.all():
        try:
            paper.listening_set_1_id = first_sets[paper.listening_clip_1_id]
            paper.listening_set_2_id = first_sets[paper.listening_clip_2_id]
        except KeyError as missing:
            raise RuntimeError(
                f"{paper.grade}-{paper.variant} uses clip id {missing} which has "
                f"no set 1; run migration 0015 first."
            ) from None
        paper.save(update_fields=["listening_set_1_id", "listening_set_2_id"])


def point_papers_back_at_clips(apps, schema_editor):
    Paper = apps.get_model("diagnostics", "Paper")
    for paper in Paper.objects.select_related("listening_set_1", "listening_set_2"):
        paper.listening_clip_1_id = paper.listening_set_1.clip_id
        paper.listening_clip_2_id = paper.listening_set_2.clip_id
        paper.save(update_fields=["listening_clip_1_id", "listening_clip_2_id"])


class Migration(migrations.Migration):

    dependencies = [("diagnostics", "0016_listeningquestion_drop_clip")]

    operations = [
        migrations.AddField(
            model_name="paper",
            name="listening_set_1",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="papers_as_first", to="diagnostics.listeningquestionset",
            ),
        ),
        migrations.AddField(
            model_name="paper",
            name="listening_set_2",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="papers_as_second", to="diagnostics.listeningquestionset",
            ),
        ),
        migrations.RunPython(point_papers_at_set_one, point_papers_back_at_clips),
        migrations.AlterField(
            model_name="paper",
            name="listening_set_1",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="papers_as_first", to="diagnostics.listeningquestionset",
            ),
        ),
        migrations.AlterField(
            model_name="paper",
            name="listening_set_2",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="papers_as_second", to="diagnostics.listeningquestionset",
            ),
        ),
        migrations.RemoveField(model_name="paper", name="listening_clip_1"),
        migrations.RemoveField(model_name="paper", name="listening_clip_2"),
    ]
```

- [ ] **Step 5: Run it**

```bash
python manage.py migrate diagnostics 0017
```

Expected: `Applying diagnostics.0017_paper_listening_sets... OK`

- [ ] **Step 6: Verify no paper lost its content**

```bash
python manage.py shell -c "from diagnostics.models import Paper; ps=Paper.objects.select_related('listening_set_1__clip','listening_set_2__clip'); print(len(ps), sorted({(p.listening_set_1.number, p.listening_set_2.number) for p in ps}))"
```

Expected: `48 [(1, 1)]` — every paper still on set 1 of both its recordings.

- [ ] **Step 7: Commit**

```bash
git add diagnostics/models/paper.py diagnostics/migrations/0017_paper_listening_sets.py diagnostics/tests/test_models_paper.py diagnostics/tests/test_downloads.py
git commit -m "Point papers at listening question sets, keeping clip accessors"
```

### Task 3.6: Update the importer to write into set 1

**Files:**
- Modify: `diagnostics/management/commands/import_listening.py:100-130`
- Test: `diagnostics/tests/test_import_listening.py`

- [ ] **Step 1: Write the failing test**

Append to the import test class:

```python
    def test_import_writes_into_set_one_and_leaves_set_two_alone(self):
        from diagnostics.models import ListeningQuestionSet
        self.assertEqual(ListeningQuestionSet.objects.filter(number=1).count(), 20)
        for question in ListeningQuestion.objects.all():
            self.assertEqual(question.question_set.number, 1)

    def test_reimport_does_not_disturb_an_existing_set_two(self):
        from diagnostics.models import AudioClip, ListeningQuestionSet
        clip = AudioClip.objects.get(number=2)
        set_two = ListeningQuestionSet.objects.create(clip=clip, number=2)
        ListeningQuestion.objects.create(
            question_set=set_two, position=1, stem="second set", answer="A"
        )
        call_command("import_listening", source=str(self.source))
        self.assertTrue(
            ListeningQuestion.objects.filter(
                question_set=set_two, stem="second set"
            ).exists()
        )
```

- [ ] **Step 2: Run to verify it fails**

```bash
python manage.py test diagnostics.tests.test_import_listening -v 2
```

Expected: FAIL — the importer still writes `clip=clip`.

- [ ] **Step 3: Update the importer**

Change the import line:

```python
from diagnostics.models import AudioClip, ListeningQuestion, ListeningQuestionSet
```

In `_import_clip`, after the `AudioClip.objects.update_or_create(...)` block and before the audio save, get or create set 1:

```python
        question_set, _ = ListeningQuestionSet.objects.get_or_create(
            clip=clip, number=1
        )
```

Replace the clear-and-rebuild block so it only touches set 1 — a re-import must never wipe the authored set 2:

```python
        for question in question_set.questions.all():
            if question.image:
                question.image.delete(save=False)
        question_set.questions.all().delete()
```

And the create call:

```python
            question = ListeningQuestion.objects.create(
                question_set=question_set,
                position=position,
                stem=correct_stem(number, position, item["stem"]),
                options=item["options"],
                answer=answer,
                acceptable_answers=alts,
            )
```

Finally, update the summary line at the end of `handle` so it reports sets too:

```python
        self.stdout.write(self.style.SUCCESS(
            f"Imported {AudioClip.objects.count()} clips, "
            f"{ListeningQuestionSet.objects.filter(number=1).count()} first sets, "
            f"{ListeningQuestion.objects.filter(question_set__number=1).count()} questions."
        ))
```

- [ ] **Step 4: Run to verify it passes**

```bash
python manage.py test diagnostics.tests.test_import_listening -v 2
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add diagnostics/management/commands/import_listening.py diagnostics/tests/test_import_listening.py
git commit -m "Import listening content into set 1 without disturbing set 2"
```

### Task 3.7: Update the remaining consumers

**Files:**
- Modify: `diagnostics/rendering.py:139-146,168-172`
- Modify: `diagnostics/admin.py:45-80,165-180`
- Modify: `diagnostics/management/commands/build_papers.py:70-80`
- Modify: `diagnostics/management/commands/verify_listening_keys.py:19`
- Modify: `diagnostics/management/commands/render_paper.py:80,91`
- Modify: `diagnostics/views.py:63,77`
- Test: `diagnostics/tests/test_rendering.py`, `diagnostics/tests/test_export_layout.py`

- [ ] **Step 1: Write the failing test**

Append to `diagnostics/tests/test_rendering.py`:

```python
class ClipSectionFromSetTests(TestCase):
    """paper_sections must keep its exact output shape - export.py, the
    download view and both templates read these dicts by key and none of
    them know sets exist."""

    def test_clip_section_keeps_its_keys(self):
        from diagnostics.rendering import paper_sections
        listening = paper_sections(self.paper)[0]
        self.assertEqual(len(listening["clips"]), 2)
        for clip in listening["clips"]:
            self.assertEqual(
                sorted(clip), ["audio", "intro", "number", "questions"]
            )

    def test_questions_come_from_the_papers_set_not_set_one(self):
        from diagnostics.models import ListeningQuestion, ListeningQuestionSet
        from diagnostics.rendering import paper_sections
        clip = self.paper.listening_set_2.clip
        set_two = ListeningQuestionSet.objects.create(clip=clip, number=2)
        for position in range(1, 6):
            ListeningQuestion.objects.create(
                question_set=set_two, position=position,
                stem=f"second-set stem {position}", answer="A",
            )
        self.paper.listening_set_2 = set_two
        self.paper.save(update_fields=["listening_set_2"])

        second = paper_sections(self.paper)[0]["clips"][1]
        self.assertEqual(
            [q.stem for q in second["questions"]],
            [f"second-set stem {p}" for p in range(1, 6)],
        )
```

Use whatever paper fixture `test_rendering.py` already builds in its `setUp`; if there is none on the class you are appending to, copy the fixture from the nearest existing rendering test.

- [ ] **Step 2: Run to verify it fails**

```bash
python manage.py test diagnostics.tests.test_rendering -v 2
```

Expected: FAIL — `AttributeError: 'AudioClip' object has no attribute 'questions'`.

- [ ] **Step 3: Update rendering**

In `diagnostics/rendering.py`, replace `_clip_section`:

```python
def _clip_section(question_set):
    """One recording's block on the paper.

    Takes the question set rather than the recording: the two variants in a
    group share the recording and differ only in which set they answer, so
    the set is the thing that identifies a paper's listening block. The
    returned keys are unchanged - export.py, views._annotate_for_display and
    both templates read them by name.
    """
    clip = question_set.clip
    return {
        "number": clip.number,
        "intro": clip.intro_text,
        "audio": clip.audio_file,
        "questions": list(question_set.questions.order_by("position")),
    }
```

And in `paper_sections`:

```python
            "clips": [
                _clip_section(paper.listening_set_1),
                _clip_section(paper.listening_set_2),
            ],
```

- [ ] **Step 4: Update the query hints**

In `diagnostics/views.py` lines 63 and 77, and `diagnostics/management/commands/render_paper.py` lines 80 and 91, replace the `select_related` argument lists:

```python
            "listening_set_1__clip", "listening_set_2__clip", "reading_passage"
```

- [ ] **Step 5: Update build_papers**

In `diagnostics/management/commands/build_papers.py`, the `handle` method currently builds a `clips` dict. Replace it with a set lookup — at this stage every paper still takes set 1, so the allocator's output is unchanged:

```python
        from diagnostics.models import ListeningQuestionSet

        sets = {
            (question_set.clip.number, question_set.number): question_set
            for question_set in ListeningQuestionSet.objects.select_related("clip")
        }
        needed_clips = set(CLIP_TASK_TYPES)
        missing = sorted(number for number in needed_clips if (number, 1) not in sets)
        if missing:
            raise CommandError(
                f"Missing listening set 1 for clips {missing}. "
                f"Run import_listening first."
            )
```

and the `update_or_create` defaults:

```python
                            defaults={
                                "listening_set_1": sets[(picture, 1)],
                                "listening_set_2": sets[(rotating, 1)],
                                "reading_passage": passages[passage_label],
                                "is_published": True,
                            },
```

Delete the now-unused `clips = {clip.number: clip for clip in AudioClip.objects.all()}` line and drop `AudioClip` from that module's model import if nothing else uses it.

- [ ] **Step 6: Update verify_listening_keys**

In `diagnostics/management/commands/verify_listening_keys.py` line 19:

```python
        questions = ListeningQuestion.objects.select_related(
            "question_set__clip"
        ).order_by(
            "question_set__clip__number", "question_set__number", "position"
        )
```

Wherever that command prints `question.clip.number`, it keeps working through the new `ListeningQuestion.clip` property.

- [ ] **Step 7: Update the admin**

In `diagnostics/admin.py`, add `ListeningQuestionSet` to the models import, then replace `ListeningQuestionInline` and `AudioClipAdmin`:

```python
class ListeningQuestionSetInline(admin.TabularInline):
    model = ListeningQuestionSet
    extra = 0
    fields = ("number",)
    ordering = ("number",)
    verbose_name = "question set"
    verbose_name_plural = "question sets on this recording"


class ListeningQuestionInline(admin.TabularInline):
    model = ListeningQuestion
    extra = 0
    fields = ("position", "stem", "options", "image", "answer", "acceptable_answers")
    ordering = ("position",)
    verbose_name = "question"
    verbose_name_plural = "questions in this set"


@admin.register(AudioClip)
class AudioClipAdmin(ImportedContentAdmin):
    list_display = ("number", "task_type", "set_count", "question_count", "has_audio")
    list_filter = ("task_type",)
    search_fields = ("number", "intro_text")
    ordering = ("number",)
    inlines = [ListeningQuestionSetInline]

    @admin.display(description="sets")
    def set_count(self, obj):
        return obj.question_sets.count()

    @admin.display(description="questions")
    def question_count(self, obj):
        return ListeningQuestion.objects.filter(question_set__clip=obj).count()

    @admin.display(boolean=True, description="audio file")
    def has_audio(self, obj):
        return bool(obj.audio_file)


@admin.register(ListeningQuestionSet)
class ListeningQuestionSetAdmin(ImportedContentAdmin):
    list_display = ("__str__", "clip", "number", "question_count")
    list_filter = ("number", "clip__task_type")
    ordering = ("clip__number", "number")
    list_select_related = ("clip",)
    inlines = [ListeningQuestionInline]

    @admin.display(description="questions")
    def question_count(self, obj):
        return obj.questions.count()


@admin.register(ListeningQuestion)
class ListeningQuestionAdmin(ImportedContentAdmin):
    list_display = ("__str__", "question_set", "position", "answer", "has_image")
    list_filter = ("question_set__number", "question_set__clip__task_type",
                   "question_set__clip__number")
    search_fields = ("stem", "answer")
    ordering = ("question_set__clip__number", "question_set__number", "position")
    list_select_related = ("question_set__clip",)

    @admin.display(boolean=True, description="image")
    def has_image(self, obj):
        return bool(obj.image)
```

In `PaperAdmin` (around line 168), replace `listening_clip_1`/`listening_clip_2` in `list_display` and `list_filter` with `listening_set_1`/`listening_set_2`, and set:

```python
    list_select_related = ("listening_set_1__clip", "listening_set_2__clip", "reading_passage")
```

Update the matching assertion in `diagnostics/tests/test_admin.py:99`.

- [ ] **Step 8: Fix the export-layout tests**

`diagnostics/tests/test_export_layout.py` lines 122-169 reach through `self.paper.listening_clip_1` and then `clip.questions`. Change those to go through the set:

```python
        question_set = self.paper.listening_set_1
        for question in question_set.questions.all():
```

and likewise at lines 142, 159 and 169 (`question_set.questions.order_by("position")`).

- [ ] **Step 9: Run the full suite**

```bash
python manage.py test
```

Expected: 840+ tests, 0 failures. Every paper is still on set 1, so no rendered output has changed.

- [ ] **Step 10: Verify a real paper still renders identically**

```bash
python manage.py render_paper 9 A --format docx
```

Expected: succeeds, and the listening section shows the same two recordings and ten questions it showed before Part 3.

- [ ] **Step 11: Commit**

```bash
git add diagnostics/rendering.py diagnostics/admin.py diagnostics/views.py diagnostics/management/commands/ diagnostics/tests/
git commit -m "Route rendering, admin and commands through listening question sets"
```

---
## Part 4: Load the second question sets

This Part is what makes Part 5 safe. It has two halves that can land independently:

- **4A — picture clips.** The 10 images and their answers already exist. Ships now.
- **4B — rotating clips.** The 75 text questions are not authored yet. This is the long pole.

**Neither half changes any paper**: the sets are created and populated, but the allocator still hands every paper set 1 until Part 5.

### Task 4.1: The authored-content format and validator

**Files:**
- Create: `diagnostics/authored/listening_sets.py`
- Test: `diagnostics/tests/test_authored_schema.py` (append)

The payload is one JSON file, `diagnostics/authored/listening_set_2.json`, shaped like this:

```json
{
  "clips": [
    {
      "number": 1,
      "task_type": "picture",
      "questions": [
        {
          "position": 1,
          "stem": "Where will the friends meet?",
          "options": [],
          "image": "clip-01-q6.jpg",
          "answer": "B",
          "acceptable_answers": []
        }
      ]
    }
  ]
}
```

Rules, mirroring the existing `authored/schema.py` style:

- exactly 20 clips, numbers 1-20, each with exactly 5 questions at positions 1-5
- `task_type` must equal `CLIP_TASK_TYPES[number]`
- picture clips: `image` required and must name a file that exists under `MEDIA_ROOT/diagnostics/listening/`; `options` must be empty; `answer` in A/B/C
- mcq3 and true_false: `options` non-empty; `answer` in A/B/C; `image` absent
- gap_fill: `options` empty; `image` absent; `answer` a non-empty string

- [ ] **Step 1: Write the failing tests**

Append to `diagnostics/tests/test_authored_schema.py`:

```python
from diagnostics.authored.listening_sets import (
    ContentError, validate_listening_set_payload,
)


def _question(position, **overrides):
    base = {
        "position": position, "stem": f"Stem {position}", "options": ["a", "b", "c"],
        "answer": "A", "acceptable_answers": [],
    }
    base.update(overrides)
    return base


def _clip(number, task_type, **question_overrides):
    return {
        "number": number, "task_type": task_type,
        "questions": [_question(p, **question_overrides) for p in range(1, 6)],
    }


class ListeningSetValidationTests(SimpleTestCase):
    def test_a_clip_must_have_exactly_five_questions(self):
        payload = _clip(2, "mcq3")
        payload["questions"] = payload["questions"][:4]
        with self.assertRaisesMessage(ContentError, "positions"):
            validate_listening_set_payload(payload)

    def test_task_type_must_match_the_bank(self):
        payload = _clip(2, "gap_fill")
        with self.assertRaisesMessage(ContentError, "mcq3"):
            validate_listening_set_payload(payload)

    def test_picture_questions_need_an_image_and_no_options(self):
        payload = _clip(1, "picture", options=[], image=None)
        with self.assertRaisesMessage(ContentError, "image"):
            validate_listening_set_payload(payload)

    def test_picture_questions_reject_options(self):
        payload = _clip(1, "picture", image="clip-01-q6.jpg")
        with self.assertRaisesMessage(ContentError, "options"):
            validate_listening_set_payload(payload)

    def test_letter_answers_must_be_a_b_or_c(self):
        payload = _clip(2, "mcq3", answer="D")
        with self.assertRaisesMessage(ContentError, "A, B or C"):
            validate_listening_set_payload(payload)

    def test_gap_fill_rejects_options(self):
        payload = _clip(3, "gap_fill", answer="museum")
        with self.assertRaisesMessage(ContentError, "options"):
            validate_listening_set_payload(payload)

    def test_gap_fill_needs_a_non_empty_answer(self):
        payload = _clip(3, "gap_fill", options=[], answer="")
        with self.assertRaisesMessage(ContentError, "answer"):
            validate_listening_set_payload(payload)

    def test_a_valid_mcq_clip_passes(self):
        validate_listening_set_payload(_clip(2, "mcq3"))

    def test_a_valid_gap_fill_clip_passes(self):
        validate_listening_set_payload(_clip(3, "gap_fill", options=[], answer="museum"))

    def test_a_valid_picture_clip_passes(self):
        validate_listening_set_payload(
            _clip(1, "picture", options=[], image="clip-01-q6.jpg", answer="B")
        )
```

- [ ] **Step 2: Run to verify they fail**

```bash
python manage.py test diagnostics.tests.test_authored_schema -v 2
```

Expected: FAIL — `ModuleNotFoundError: diagnostics.authored.listening_sets`.

- [ ] **Step 3: Write the validator**

Create `diagnostics/authored/listening_sets.py`:

```python
"""Validation for the authored second question sets.

The first sets are parsed out of the client's .docx by the extraction
pipeline, which can check its own work against the printed answer key. The
second sets are written by hand from the transcripts, with no key to check
against, so the shape is enforced here instead: five questions per clip, the
task type the bank says that clip is, and an answer that is well-formed for
that task type. Quality stays a human review gate; these rules only stop
malformed content reaching the bank.

Image existence is checked by the loader, not here, so this module stays
importable without Django settings configured.
"""

from diagnostics.constants import CLIP_TASK_TYPES, LETTER_ANSWER_TYPES, TaskType

QUESTIONS_PER_SET = 5
LETTER_ANSWERS = {"A", "B", "C"}


class ContentError(ValueError):
    """Authored listening content does not match the required pattern."""


def validate_listening_set_payload(payload):
    """Validate one clip's second question set. Raises ContentError."""
    number = payload.get("number")
    if number not in CLIP_TASK_TYPES:
        raise ContentError(f"Clip {number!r} is not one of the 20 clips in the bank.")

    expected_task = CLIP_TASK_TYPES[number]
    declared = payload.get("task_type")
    if declared != expected_task:
        raise ContentError(
            f"Clip {number}: bank says this recording is {expected_task}, "
            f"payload says {declared!r}."
        )

    questions = payload.get("questions", [])
    positions = [question.get("position") for question in questions]
    if positions != list(range(1, QUESTIONS_PER_SET + 1)):
        raise ContentError(
            f"Clip {number}: expected exactly {QUESTIONS_PER_SET} questions at "
            f"positions 1-{QUESTIONS_PER_SET}, got positions {positions}."
        )

    for question in questions:
        _validate_question(number, expected_task, question)


def _validate_question(number, task, question):
    label = f"Clip {number} Q{question['position']}"

    if not (question.get("stem") or "").strip():
        raise ContentError(f"{label}: stem is empty.")

    options = question.get("options") or []
    image = question.get("image")
    answer = (question.get("answer") or "").strip()

    if task == TaskType.PICTURE:
        if not image:
            raise ContentError(f"{label}: picture questions need an image filename.")
        if options:
            raise ContentError(
                f"{label}: picture questions carry their options in the image, "
                f"so the options list must be empty."
            )
    else:
        if image:
            raise ContentError(f"{label}: only picture questions may carry an image.")

    if task in LETTER_ANSWER_TYPES:
        if answer not in LETTER_ANSWERS:
            raise ContentError(f"{label}: answer must be A, B or C, not {answer!r}.")
        if task != TaskType.PICTURE and not options:
            raise ContentError(f"{label}: {task} questions need an options list.")
    else:
        if options:
            raise ContentError(f"{label}: gap-fill questions must not have options.")
        if not answer:
            raise ContentError(f"{label}: gap-fill questions need an answer.")


def validate_listening_set_file(document):
    """Validate the whole {"clips": [...]} document. Raises ContentError."""
    clips = document.get("clips", [])
    numbers = [clip.get("number") for clip in clips]
    if sorted(numbers) != sorted(CLIP_TASK_TYPES):
        missing = sorted(set(CLIP_TASK_TYPES) - set(numbers))
        extra = sorted(set(numbers) - set(CLIP_TASK_TYPES))
        raise ContentError(
            f"Expected a second set for all {len(CLIP_TASK_TYPES)} clips; "
            f"missing {missing}, unexpected {extra}."
        )
    for clip in clips:
        validate_listening_set_payload(clip)
```

- [ ] **Step 4: Run to verify they pass**

```bash
python manage.py test diagnostics.tests.test_authored_schema -v 2
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add diagnostics/authored/listening_sets.py diagnostics/tests/test_authored_schema.py
git commit -m "Validate the shape of authored second listening question sets"
```

### Task 4.2: The loader command

**Files:**
- Create: `diagnostics/management/commands/load_listening_set_2.py`
- Create: `diagnostics/tests/test_load_listening_set_2.py`

- [ ] **Step 1: Write the failing tests**

Create `diagnostics/tests/test_load_listening_set_2.py`:

```python
"""The loader is the only writer of set 2, so these tests are what stop it
silently half-loading: a clip must come out with five questions or the whole
command must roll back."""

import json
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from diagnostics.models import (
    AudioClip, ListeningQuestion, ListeningQuestionSet,
)


def _clip_payload(number, task_type, **overrides):
    questions = []
    for position in range(1, 6):
        question = {
            "position": position, "stem": f"Clip {number} set 2 Q{position}",
            "options": ["a", "b", "c"], "answer": "A", "acceptable_answers": [],
        }
        question.update(overrides)
        questions.append(question)
    return {"number": number, "task_type": task_type, "questions": questions}


class LoadListeningSetTwoTests(TestCase):
    def setUp(self):
        from diagnostics.constants import CLIP_TASK_TYPES
        for number, task in CLIP_TASK_TYPES.items():
            AudioClip.objects.create(number=number, task_type=task)
            ListeningQuestionSet.objects.create(
                clip=AudioClip.objects.get(number=number), number=1
            )
        self.payload_path = Path(settings.BASE_DIR) / "test-listening-set-2.json"
        self.addCleanup(
            lambda: self.payload_path.exists() and self.payload_path.unlink()
        )

    def _write(self, clips):
        self.payload_path.write_text(json.dumps({"clips": clips}), encoding="utf-8")

    def _full_payload(self):
        from diagnostics.constants import CLIP_TASK_TYPES, PICTURE_CLIPS
        clips = []
        for number, task in CLIP_TASK_TYPES.items():
            if number in PICTURE_CLIPS:
                clips.append(_clip_payload(
                    number, task, options=[],
                    image=f"clip-{number:02d}-q6.jpg", answer="B",
                ))
            elif task == "gap_fill":
                clips.append(_clip_payload(number, task, options=[], answer="museum"))
            else:
                clips.append(_clip_payload(number, task))
        return clips

    def test_loads_a_second_set_for_every_clip(self):
        self._write(self._full_payload())
        call_command("load_listening_set_2", source=str(self.payload_path),
                     skip_images=True)
        self.assertEqual(ListeningQuestionSet.objects.filter(number=2).count(), 20)
        self.assertEqual(
            ListeningQuestion.objects.filter(question_set__number=2).count(), 100
        )

    def test_set_one_is_never_touched(self):
        first = ListeningQuestionSet.objects.get(clip__number=1, number=1)
        ListeningQuestion.objects.create(
            question_set=first, position=1, stem="original", answer="A"
        )
        self._write(self._full_payload())
        call_command("load_listening_set_2", source=str(self.payload_path),
                     skip_images=True)
        self.assertTrue(
            ListeningQuestion.objects.filter(
                question_set=first, stem="original"
            ).exists()
        )

    def test_reloading_replaces_set_two_rather_than_duplicating_it(self):
        self._write(self._full_payload())
        call_command("load_listening_set_2", source=str(self.payload_path),
                     skip_images=True)
        call_command("load_listening_set_2", source=str(self.payload_path),
                     skip_images=True)
        self.assertEqual(
            ListeningQuestion.objects.filter(question_set__number=2).count(), 100
        )

    def test_a_malformed_clip_rolls_the_whole_load_back(self):
        clips = self._full_payload()
        clips[7]["questions"][2]["answer"] = "Z"
        self._write(clips)
        with self.assertRaises(CommandError):
            call_command("load_listening_set_2", source=str(self.payload_path),
                         skip_images=True)
        self.assertEqual(ListeningQuestionSet.objects.filter(number=2).count(), 0)

    def test_a_missing_image_is_refused_before_anything_is_written(self):
        clips = self._full_payload()
        for clip in clips:
            if clip["number"] == 1:
                clip["questions"][0]["image"] = "clip-99-q9.jpg"
        self._write(clips)
        with self.assertRaisesMessage(CommandError, "clip-99-q9.jpg"):
            call_command("load_listening_set_2", source=str(self.payload_path))
        self.assertEqual(ListeningQuestionSet.objects.filter(number=2).count(), 0)

    def test_a_missing_clip_in_the_payload_is_refused(self):
        clips = self._full_payload()[:-1]
        self._write(clips)
        with self.assertRaises(CommandError):
            call_command("load_listening_set_2", source=str(self.payload_path),
                         skip_images=True)
```

- [ ] **Step 2: Run to verify they fail**

```bash
python manage.py test diagnostics.tests.test_load_listening_set_2 -v 2
```

Expected: FAIL — `Unknown command: 'load_listening_set_2'`.

- [ ] **Step 3: Write the command**

Create `diagnostics/management/commands/load_listening_set_2.py`:

```python
"""Load the authored second question set for all 20 clips.

Set 1 comes out of the client's .docx via import_listening. Set 2 is written
by hand from the transcripts (media/diagnostics/audio/transcripts-full.md)
and lives in diagnostics/authored/listening_set_2.json - the picture clips
reuse items 6 and 7, which were recorded but never turned into questions;
the rotating clips get five newly written questions each.

All-or-nothing: the payload is validated in full, every referenced image is
confirmed to exist, and only then is anything written, inside one
transaction. A half-loaded set 2 would let the group allocator issue a paper
with three listening questions on it.

Idempotent: re-running deletes and rebuilds set 2. It never touches set 1.
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from diagnostics.authored.listening_sets import (
    ContentError, validate_listening_set_file,
)
from diagnostics.models import AudioClip, ListeningQuestion, ListeningQuestionSet

DEFAULT_PAYLOAD = (
    Path(settings.BASE_DIR) / "diagnostics" / "authored" / "listening_set_2.json"
)
IMAGE_DIR_NAME = "diagnostics/listening"
SET_NUMBER = 2


class Command(BaseCommand):
    help = "Load the authored second listening question set for all 20 clips."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source", default=None,
            help=f"Override the payload path (default {DEFAULT_PAYLOAD}).",
        )
        parser.add_argument(
            "--skip-images", action="store_true",
            help="Do not attach picture-strip images. Tests only.",
        )

    def handle(self, *args, **options):
        source = Path(options["source"]) if options["source"] else DEFAULT_PAYLOAD
        skip_images = options["skip_images"]

        if not source.exists():
            raise CommandError(f"Missing authored payload: {source}")

        document = json.loads(source.read_text(encoding="utf-8"))
        try:
            validate_listening_set_file(document)
        except ContentError as error:
            raise CommandError(f"Authored content is malformed: {error}") from error

        image_dir = Path(settings.MEDIA_ROOT) / IMAGE_DIR_NAME
        images = {} if skip_images else self._collect_images(document, image_dir)

        clips = {clip.number: clip for clip in AudioClip.objects.all()}
        missing = sorted(
            entry["number"] for entry in document["clips"]
            if entry["number"] not in clips
        )
        if missing:
            raise CommandError(
                f"Clips {missing} are not imported. Run import_listening first."
            )

        with transaction.atomic():
            for entry in document["clips"]:
                self._load_clip(clips[entry["number"]], entry, images, skip_images)

        loaded = ListeningQuestion.objects.filter(
            question_set__number=SET_NUMBER
        ).count()
        self.stdout.write(self.style.SUCCESS(
            f"Loaded set {SET_NUMBER} for "
            f"{ListeningQuestionSet.objects.filter(number=SET_NUMBER).count()} clips "
            f"({loaded} questions)."
        ))
        self.stdout.write(
            "The listening key sign-off has lapsed - the answer bank changed. "
            "Re-run verify_listening_keys once a human has checked the new answers."
        )

    def _collect_images(self, document, image_dir):
        """Read every referenced image up front, so a missing file fails the
        command before a single row is written."""
        images = {}
        for entry in document["clips"]:
            for question in entry["questions"]:
                name = question.get("image")
                if not name:
                    continue
                path = image_dir / name
                if not path.exists():
                    raise CommandError(
                        f"Clip {entry['number']} Q{question['position']} references "
                        f"{name}, which does not exist under {image_dir}."
                    )
                images[name] = path.read_bytes()
        return images

    def _load_clip(self, clip, entry, images, skip_images):
        question_set, _ = ListeningQuestionSet.objects.get_or_create(
            clip=clip, number=SET_NUMBER
        )
        for question in question_set.questions.all():
            if question.image:
                question.image.delete(save=False)
        question_set.questions.all().delete()

        for payload in entry["questions"]:
            question = ListeningQuestion.objects.create(
                question_set=question_set,
                position=payload["position"],
                stem=payload["stem"],
                options=payload.get("options") or [],
                answer=payload["answer"],
                acceptable_answers=payload.get("acceptable_answers") or [],
            )
            name = payload.get("image")
            if name and not skip_images:
                question.image.save(name, ContentFile(images[name]), save=True)
```

- [ ] **Step 4: Run to verify they pass**

```bash
python manage.py test diagnostics.tests.test_load_listening_set_2 -v 2
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add diagnostics/management/commands/load_listening_set_2.py diagnostics/tests/test_load_listening_set_2.py
git commit -m "Add an all-or-nothing loader for the second listening question sets"
```

### Task 4.3 (Part 4A): Author the picture-clip entries

**Files:**
- Create: `diagnostics/authored/listening_set_2.json` (picture clips only, for now)

All ten questions are already composited. Stems come from the `[UNUSED - available for set 2]` items in `media/diagnostics/audio/transcripts-full.md`.

- [ ] **Step 1: Read the ten unused items**

```bash
grep -n "UNUSED" "media/diagnostics/audio/transcripts-full.md"
```

Expected: 10 hits, at clips 1, 5, 9, 13 and 15, items 6 and 7 in each.

- [ ] **Step 2: Write the picture entries**

Create `diagnostics/authored/listening_set_2.json` with the five picture clips. Each set 2 is: the two new items at positions 1-2, then three of the five existing items at positions 3-5 (the forced 3-item overlap from section 0.5). Take the three carried-over items from positions 3, 4 and 5 of set 1, so the two sets differ on their opening items — the ones a student meets while still settling into the recording.

Use these answers exactly (section 0.6):

| Clip | new Q1 (was item 6) | new Q2 (was item 7) |
|---|---|---|
| 1 | image `clip-01-q6.jpg`, answer **B** | image `clip-01-q7.jpg`, answer **C** |
| 5 | image `clip-05-q6.jpg`, answer **B** | image `clip-05-q7.jpg`, answer **C** |
| 9 | image `clip-09-q6.jpg`, answer **A** | image `clip-09-q7.jpg`, answer **C** |
| 13 | image `clip-13-q6.jpg`, answer **A** | image `clip-13-q7.jpg`, answer **A** |
| 15 | image `clip-15-q6.jpg`, answer **A** | image `clip-15-q7.jpg`, answer **A** |

Skeleton for clip 1 (repeat the shape for 5, 9, 13, 15):

```json
{
  "clips": [
    {
      "number": 1,
      "task_type": "picture",
      "questions": [
        {"position": 1, "stem": "Where will the friends meet?",
         "options": [], "image": "clip-01-q6.jpg",
         "answer": "B", "acceptable_answers": []},
        {"position": 2, "stem": "<item 7 stem from the transcript>",
         "options": [], "image": "clip-01-q7.jpg",
         "answer": "C", "acceptable_answers": []},
        {"position": 3, "stem": "Who lives with Josh in his house?",
         "options": [], "image": "clip-01-q3.jpg",
         "answer": "<set 1 Q3 answer>", "acceptable_answers": []},
        {"position": 4, "stem": "What will the boy take with him on holiday?",
         "options": [], "image": "clip-01-q4.jpg",
         "answer": "<set 1 Q4 answer>", "acceptable_answers": []},
        {"position": 5, "stem": "What time will the train to Manchester leave?",
         "options": [], "image": "clip-01-q5.jpg",
         "answer": "<set 1 Q5 answer>", "acceptable_answers": []}
      ]
    }
  ]
}
```

Read the carried-over answers straight out of the DB rather than retyping them:

```bash
python manage.py shell -c "from diagnostics.models import ListeningQuestion as Q; [print(q.question_set.clip.number, q.position, q.answer, q.stem) for q in Q.objects.filter(question_set__number=1, question_set__clip__number__in=[1,5,9,13,15], position__gte=3).order_by('question_set__clip__number','position')]"
```

**Do not run the loader yet** — `validate_listening_set_file` requires all 20 clips, so it will refuse a picture-only payload. That is deliberate: it is what makes the gate real. Part 4A ends with the JSON written and reviewed, not loaded.

- [ ] **Step 3: Check the ten images are all present**

```bash
ls media/diagnostics/listening/clip-{01,05,09,13,15}-q{6,7}.jpg | wc -l
```

Expected: `10`

- [ ] **Step 4: Commit**

```bash
git add diagnostics/authored/listening_set_2.json
git commit -m "Author the picture-clip half of the second listening question sets"
```

### Task 4.4 (Part 4B): Author the 75 rotating-clip questions

**Files:**
- Modify: `diagnostics/authored/listening_set_2.json` (add the 15 rotating clips)

**This is the long pole and the only thing gating Part 5.** It is content work, not code, and can run in parallel with Parts 1-3 by anyone with the transcripts.

Per clip: 5 new questions, positions 1-5, written from `media/diagnostics/audio/transcripts-full.md`, **fully distinct from set 1** — the rotating clips have enough content that no overlap is needed or acceptable.

Requirements for every one of the 75:

- **B1 CEFR ceiling.** No vocabulary or structure above B1. Check against `grade-9-vocabulary-and-grammar-guide.txt` / `grade-10-…` / `grade-11-…` in the repo root when unsure.
- **Answerable from the recording alone**, no outside knowledge.
- **Task type must match** `CLIP_TASK_TYPES`: mcq3 clips (2, 6, 10, 14, 16) need 3 options and an A/B/C answer; gap_fill clips (3, 7, 11, 18, 19) need no options and a text answer plus any `acceptable_answers` alternatives; true_false clips (4, 8, 12, 17, 20) need options and an A/B/C answer, matching how set 1 encodes YES/NO for that clip.
- **Do not reuse a set 1 stem or test the same fact.** Diff each new set against set 1 before committing:

```bash
python manage.py shell -c "from diagnostics.models import ListeningQuestion as Q; [print(q.position, q.stem) for q in Q.objects.filter(question_set__number=1, question_set__clip__number=2).order_by('position')]"
```

- **Transcript quality caveats** (from the header of `transcripts-full.md`): speaker labels degrade in clips 7, 10, 17, 18, 19 and 20; clip 8 has two consecutive "Boy:" turns where the second is the girl; clip 16 carries no label and is the block starting "People always ask me why I only travel the hard way." Attribute from the existing question bank where a label is missing or wrong.

- [ ] **Step 1: Author the 15 clip entries into the JSON**

- [ ] **Step 2: Validate the payload without touching the DB**

```bash
python -c "import json; from diagnostics.authored.listening_sets import validate_listening_set_file; validate_listening_set_file(json.load(open('diagnostics/authored/listening_set_2.json', encoding='utf-8'))); print('payload OK')"
```

Expected: `payload OK`. If it raises, the message names the clip and question.

- [ ] **Step 3: Human review gate**

The validator checks shape, not quality. Before loading, a second person reads all 85 questions against the transcripts for: correct answer, single unambiguous answer, B1 ceiling, and no accidental overlap with set 1. **This is a required gate — do not skip it.** The whole point of set 2 is that two students in one room get genuinely different papers; a wrong key here is invisible until marking.

- [ ] **Step 4: Load it**

```bash
python manage.py load_listening_set_2
```

Expected: `Loaded set 2 for 20 clips (100 questions).` followed by the sign-off-lapsed warning.

- [ ] **Step 5: Verify the gate condition holds**

```bash
python manage.py shell -c "
from diagnostics.models import AudioClip, ListeningQuestion as Q
bad = [c.number for c in AudioClip.objects.all()
       if Q.objects.filter(question_set__clip=c, question_set__number=1).count() != 5
       or Q.objects.filter(question_set__clip=c, question_set__number=2).count() != 5]
print('clips without two full sets:', bad)
"
```

Expected: `clips without two full sets: []`

**This empty list is the gate. Part 5 must not start until it is empty.**

- [ ] **Step 6: Re-verify the listening keys**

```bash
python manage.py verify_listening_keys
```

The sign-off lapsed when the answers changed (section 0.8). Re-run it once a human has checked all 200 answers.

- [ ] **Step 7: Run the full suite**

```bash
python manage.py test
```

Expected: 855+ tests, 0 failures.

- [ ] **Step 8: Commit**

```bash
git add diagnostics/authored/listening_set_2.json
git commit -m "Author the 75 rotating-clip questions for the second listening sets"
```

---

## Part 5: Group-aware allocation

**Gate check before starting:** Task 4.4 Step 5 must print an empty list. If it does not, stop — flipping this on now produces byte-identical listening papers for the two variants in a group, which is worse than the current defect.

### Task 5.1: Allocate the clip pair per group

**Files:**
- Modify: `diagnostics/allocation.py`
- Test: `diagnostics/tests/test_allocation.py`

- [ ] **Step 1: Write the failing tests**

Append to `diagnostics/tests/test_allocation.py`:

```python
from diagnostics.allocation import Allocation, allocate, allocate_group
from diagnostics.navigation import (
    GROUP_NUMBERS, group_for_variant, variants_for_group,
)


class GroupAllocationTests(SimpleTestCase):
    """A group is one room at one time playing one recording, so both its
    variants must draw the same clip pair - and then differ on everything
    else, or the two papers are the same paper."""

    def test_both_variants_in_a_group_get_the_same_clip_pair(self):
        for grade in GRADES:
            for group in GROUP_NUMBERS:
                first, second = variants_for_group(group)
                a, b = allocate(grade, first), allocate(grade, second)
                self.assertEqual(
                    (a.picture_clip, a.rotating_clip),
                    (b.picture_clip, b.rotating_clip),
                    f"G{grade} group {group} ({first}/{second}) would need two "
                    f"recordings in one room",
                )

    def test_the_two_variants_in_a_group_get_different_set_numbers(self):
        for grade in GRADES:
            for group in GROUP_NUMBERS:
                first, second = variants_for_group(group)
                self.assertNotEqual(
                    allocate(grade, first).set_number,
                    allocate(grade, second).set_number,
                )

    def test_set_numbers_are_always_one_or_two(self):
        for grade in GRADES:
            for variant in VARIANTS:
                self.assertIn(allocate(grade, variant).set_number, (1, 2))

    def test_the_two_variants_in_a_group_get_different_passages(self):
        for grade in GRADES:
            for group in GROUP_NUMBERS:
                first, second = variants_for_group(group)
                self.assertNotEqual(
                    allocate(grade, first).passage,
                    allocate(grade, second).passage,
                    f"G{grade} group {group} shares a reading passage",
                )

    def test_a_rotating_clip_never_serves_two_groups_in_one_grade(self):
        """The new invariant. A rotating clip's uses within a grade must all
        fall inside one group: 15 clips against 8 groups leaves room, and a
        clip crossing a group boundary would mean two sittings hearing the
        same recording for no reason."""
        for grade in GRADES:
            owners = {}
            for variant in VARIANTS:
                clip = allocate(grade, variant).rotating_clip
                group = group_for_variant(variant)
                owners.setdefault(clip, set()).add(group)
            for clip, groups in owners.items():
                self.assertEqual(
                    len(groups), 1,
                    f"G{grade}: rotating clip {clip} serves groups {sorted(groups)}",
                )

    def test_a_picture_clip_serves_at_most_two_groups_in_one_grade(self):
        """Five picture clips against eight groups forces sharing: three
        clips take two groups each, two take one. More than two would push
        the clip past REUSE_CAPS["picture_clip"] of 4 paper-uses."""
        for grade in GRADES:
            owners = {}
            for variant in VARIANTS:
                clip = allocate(grade, variant).picture_clip
                owners.setdefault(clip, set()).add(group_for_variant(variant))
            for clip, groups in owners.items():
                self.assertLessEqual(
                    len(groups), 2,
                    f"G{grade}: picture clip {clip} serves groups {sorted(groups)}",
                )

    def test_every_picture_clip_in_the_bank_is_used_each_grade(self):
        for grade in GRADES:
            used = {allocate(grade, v).picture_clip for v in VARIANTS}
            self.assertEqual(used, set(PICTURE_CLIPS), f"grade {grade}")

    def test_allocate_group_and_allocate_agree(self):
        for grade in GRADES:
            for group in GROUP_NUMBERS:
                picture, rotating = allocate_group(grade, group)
                for variant in variants_for_group(group):
                    result = allocate(grade, variant)
                    self.assertEqual(result.picture_clip, picture)
                    self.assertEqual(result.rotating_clip, rotating)

    def test_unknown_group_is_rejected(self):
        with self.assertRaises(ValueError):
            allocate_group(9, 0)
        with self.assertRaises(ValueError):
            allocate_group(9, 9)
```

The existing `AllocationTests` in this file unpack a 3-tuple (`picture, rotating, _passage = allocate(...)`). Update every one to use the named fields: `result = allocate(grade, variant)` then `result.picture_clip` / `result.rotating_clip` / `result.passage`.

- [ ] **Step 2: Run to verify they fail**

```bash
python manage.py test diagnostics.tests.test_allocation -v 2
```

Expected: FAIL — `ImportError: cannot import name 'Allocation'`.

- [ ] **Step 3: Rewrite the allocator**

Replace the body of `diagnostics/allocation.py` below the `_ROTATION` construction (keep the module docstring, extend it, and keep `_ROTATION` and `_passages` exactly as they are):

Add to the module docstring, after the "Cap compliance" paragraph:

```
  Group coherence. A group is two variants sitting in one room at one time
  with one recording playing, so the clip pair is drawn once per group and
  both its variants inherit it. Everything else - the question set number,
  the reading passage, and the sampled writing and speaking - stays
  per-variant, because those are what make the two papers in the room
  different from each other.
```

New imports at the top of the file:

```python
from dataclasses import dataclass

from diagnostics.constants import (
    GRADES, PICTURE_CLIPS, ROTATING_CLIPS_BY_TYPE, VARIANTS,
)
from diagnostics.navigation import (
    GROUPS_PER_GRADE, GROUP_NUMBERS, group_for_variant, variants_for_group,
)
```

Then, replacing the old `allocate`:

```python
@dataclass(frozen=True)
class Allocation:
    """What one paper gets. Named fields rather than a tuple because the
    third element used to be the passage and is now the set number; a
    positional unpack would have kept working and silently swapped them."""

    picture_clip: int
    rotating_clip: int
    set_number: int
    passage: str


def allocate_group(grade, group):
    """Return (picture_clip_number, rotating_clip_number) for one sitting.

    Pure: same arguments, same result, no database and no randomness.

    Both clips are indexed by the group number rather than the variant, which
    is the whole fix - sixteen variants used to draw sixteen independent clip
    pairs, so every one of the 24 rooms needed two recordings playing at once.
    Eight groups per grade need eight pairs, not sixteen.

    The grade offset staggers each grade's starting point so grades do not all
    open on the same clip; three identical-looking grade 9/10/11 group 1s
    would look like a bug to a teacher holding two of them.
    """
    if group not in GROUP_NUMBERS:
        raise ValueError(
            f"Group {group} does not exist; grades run 1-{GROUPS_PER_GRADE}."
        )

    offset = (grade - min(GRADES)) * GROUPS_PER_GRADE
    index = group - 1 + offset

    # 15 rotating clips against 8 groups: consecutive indices never repeat
    # within a grade, which is what keeps a rotating clip inside one group.
    rotating = _ROTATION[index % len(_ROTATION)]
    # 5 picture clips against 8 groups: three clips take two groups each.
    # Unavoidable - see the plan's section 0.5 on the picture residual.
    picture = PICTURE_CLIPS[index % len(PICTURE_CLIPS)]
    return picture, rotating


def allocate(grade, variant):
    """Return the Allocation for one paper.

    Pure: same arguments, same result, no database and no randomness. This
    matters more than elegance here, because build_papers rewrites a paper's
    listening and reading fields on every run via update_or_create; a random
    allocator would reissue different content under the same paper name, so
    "G9-A" would mean two different tests to two teachers.
    """
    try:
        index = VARIANTS.index(variant)
    except ValueError:
        raise ValueError(
            f"Unknown variant {variant!r}; expected one of {''.join(VARIANTS)}."
        ) from None

    group = group_for_variant(variant)
    picture, rotating = allocate_group(grade, group)

    # Which of the recording's two question papers this variant answers. The
    # first variant in the room gets set 1, the second gets set 2 - this is
    # the only thing that stops the two papers in a room being identical now
    # that they share both recordings.
    set_number = variants_for_group(group).index(variant) + 1

    offset = (grade - min(GRADES)) * len(VARIANTS)
    passages = _passages()
    # len(VARIANTS) is 16 but there are only 15 passages, so a plain
    # `index % 15` would send the 16th variant (index 15) right back to
    # passage 0 - the same wrap point where the picture and rotating pools
    # also cycle back. `index // len(passages)` is 0 for every index except
    # the last, where it nudges the wrapped slot one passage forward so that
    # collision never happens. It also keeps the two variants in the last
    # group off the same passage, which the group tests now pin explicitly.
    passage_index = (index + index // len(passages) + offset) % len(passages)

    return Allocation(
        picture_clip=picture,
        rotating_clip=rotating,
        set_number=set_number,
        passage=passages[passage_index],
    )
```

- [ ] **Step 4: Run to verify they pass**

```bash
python manage.py test diagnostics.tests.test_allocation -v 2
```

Expected: PASS, including the reuse-cap tests that were already there. If `test_reuse_caps_are_respected_within_each_grade` fails on `picture_clip`, the group indexing has more than two groups on one clip — recheck `allocate_group`.

- [ ] **Step 5: Commit**

```bash
git add diagnostics/allocation.py diagnostics/tests/test_allocation.py
git commit -m "Allocate the listening clip pair once per exam group"
```

### Task 5.2: Build papers from the group allocation

**Files:**
- Modify: `diagnostics/management/commands/build_papers.py`
- Test: `diagnostics/tests/test_build_papers.py`

- [ ] **Step 1: Write the failing test**

Append to `diagnostics/tests/test_build_papers.py`:

```python
class GroupBuildTests(TestCase):
    def test_built_papers_share_audio_within_every_group(self):
        from diagnostics.navigation import GROUP_NUMBERS, variants_for_group
        from diagnostics.models import Paper
        call_command("build_papers")
        for grade in GRADES:
            for group in GROUP_NUMBERS:
                first, second = variants_for_group(group)
                a = Paper.objects.get(grade=grade, variant=first)
                b = Paper.objects.get(grade=grade, variant=second)
                self.assertEqual(
                    (a.listening_clip_1_id if hasattr(a, "listening_clip_1_id")
                     else a.listening_set_1.clip_id,
                     a.listening_set_2.clip_id),
                    (b.listening_set_1.clip_id, b.listening_set_2.clip_id),
                    f"G{grade} group {group}",
                )

    def test_built_papers_use_different_question_sets_within_every_group(self):
        from diagnostics.navigation import GROUP_NUMBERS, variants_for_group
        from diagnostics.models import Paper
        call_command("build_papers")
        for grade in GRADES:
            for group in GROUP_NUMBERS:
                first, second = variants_for_group(group)
                a = Paper.objects.get(grade=grade, variant=first)
                b = Paper.objects.get(grade=grade, variant=second)
                self.assertNotEqual(
                    (a.listening_set_1_id, a.listening_set_2_id),
                    (b.listening_set_1_id, b.listening_set_2_id),
                    f"G{grade} group {group} would sit identical papers",
                )

    def test_build_refuses_when_a_clip_has_no_second_set(self):
        from diagnostics.models import ListeningQuestionSet
        ListeningQuestionSet.objects.filter(number=2, clip__number=3).delete()
        with self.assertRaisesMessage(CommandError, "second question set"):
            call_command("build_papers")
```

The fixture for this test class must load both sets. Reuse whatever fixture the existing build tests use, then call `load_listening_set_2` with a generated payload, or create the set-2 rows directly with `ListeningQuestionSet.objects.create(clip=clip, number=2)` plus five questions each.

- [ ] **Step 2: Run to verify it fails**

```bash
python manage.py test diagnostics.tests.test_build_papers -v 2
```

Expected: FAIL — papers still land on set 1 for both variants.

- [ ] **Step 3: Update the command**

In `diagnostics/management/commands/build_papers.py`, extend the missing-content check to demand both sets:

```python
        missing_first = sorted(n for n in needed_clips if (n, 1) not in sets)
        if missing_first:
            raise CommandError(
                f"Missing listening set 1 for clips {missing_first}. "
                f"Run import_listening first."
            )
        missing_second = sorted(n for n in needed_clips if (n, 2) not in sets)
        if missing_second:
            raise CommandError(
                f"Clips {missing_second} have no second question set. The two "
                f"variants in a group share one recording, so without a second "
                f"set they would sit identical listening papers. Run "
                f"load_listening_set_2 first."
            )
```

Replace the allocation call and the `defaults` block inside the variant loop:

```python
                        plan = allocate(grade, variant)
                        if plan.passage not in passages:
                            raise CommandError(
                                f"G{grade}-{variant} needs reading passage "
                                f"{plan.passage}, which is not imported. "
                                f"Run import_reading_bank first."
                            )
                        paper, _ = Paper.objects.update_or_create(
                            grade=grade,
                            variant=variant,
                            defaults={
                                "listening_set_1": sets[(plan.picture_clip, plan.set_number)],
                                "listening_set_2": sets[(plan.rotating_clip, plan.set_number)],
                                "reading_passage": passages[plan.passage],
                                "is_published": True,
                            },
                        )
```

Add the group check to the pre-commit verification (Part 7 writes `find_group_violations`; if Part 7 has not landed yet, leave this line out and add it in Task 7.3):

```python
                problems = find_reuse_violations() + find_group_violations()
```

- [ ] **Step 4: Run to verify it passes**

```bash
python manage.py test diagnostics.tests.test_build_papers -v 2
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add diagnostics/management/commands/build_papers.py diagnostics/tests/test_build_papers.py
git commit -m "Build papers from the group allocation, one set number per variant"
```

---
## Part 6: Stop speaking prompts leaking across a group

10 of 24 groups currently share a speaking prompt. The cause is that `_at_cap_in_grade` only excludes prompts that have hit `REUSE_CAPS["speaking_prompt"] = 2` **within the grade** — a prompt used once elsewhere in the grade is still fair game for the room partner.

The fix is a second, harder exclusion: the group partner's prompts are banned outright, at any usage count. Two people sitting side by side must never get the same speaking prompt, regardless of what the grade-wide budget allows.

### Task 6.1: Exclude the group partner's prompts

**Files:**
- Modify: `diagnostics/sampling.py`
- Test: `diagnostics/tests/test_sampling.py`

- [ ] **Step 1: Write the failing tests**

Append to `diagnostics/tests/test_sampling.py`:

```python
from diagnostics.navigation import partner_variant
from diagnostics.sampling import (
    SamplingError, sample_speaking_prompts, used_by_group_partner,
)


class GroupPartnerExclusionTests(TestCase):
    """Two students sitting side by side must never get the same speaking
    prompt. The grade-wide reuse cap does not achieve that on its own: a
    prompt used once elsewhere in the grade is still under the cap of 2 and
    was landing on both papers in a room 10 times out of 24."""

    def setUp(self):
        self.passage = ReadingPassage.objects.create(
            label="R01", title="t", body=" ".join(["word"] * 200)
        )
        for task in SPEAKING_TASK_ORDER:
            for index in range(10):
                SpeakingPrompt.objects.create(task=task, prompt=f"{task} {index}")

    def _paper(self, variant):
        clip_a = AudioClip.objects.create(number=ord(variant), task_type="picture")
        clip_b = AudioClip.objects.create(number=ord(variant) + 100, task_type="mcq3")
        return Paper.objects.create(
            grade=9, variant=variant,
            listening_set_1=ListeningQuestionSet.objects.create(clip=clip_a, number=1),
            listening_set_2=ListeningQuestionSet.objects.create(clip=clip_b, number=1),
            reading_passage=self.passage,
        )

    def test_partner_prompts_are_reported_as_used(self):
        paper_a, paper_b = self._paper("A"), self._paper("B")
        sample_speaking_prompts(paper_a)
        taken = set(paper_a.speaking_prompts.values_list("pk", flat=True))
        self.assertEqual(used_by_group_partner(paper_b), taken)

    def test_the_room_partner_never_draws_the_same_prompt(self):
        paper_a, paper_b = self._paper("A"), self._paper("B")
        sample_speaking_prompts(paper_a)
        sample_speaking_prompts(paper_b)
        a = set(paper_a.speaking_prompts.values_list("pk", flat=True))
        b = set(paper_b.speaking_prompts.values_list("pk", flat=True))
        self.assertEqual(a & b, set())

    def test_exclusion_holds_even_when_the_prompt_is_under_the_grade_cap(self):
        """The prompt is used once in the grade, so the cap of 2 still allows
        it. The group rule must reject it anyway."""
        paper_a, paper_b = self._paper("A"), self._paper("B")
        sample_speaking_prompts(paper_a)
        for _ in range(20):
            sample_speaking_prompts(paper_b)
            a = set(paper_a.speaking_prompts.values_list("pk", flat=True))
            b = set(paper_b.speaking_prompts.values_list("pk", flat=True))
            self.assertEqual(a & b, set())

    def test_a_paper_with_no_partner_yet_excludes_nothing(self):
        paper_a = self._paper("A")
        self.assertEqual(used_by_group_partner(paper_a), set())

    def test_exhausting_a_task_pool_raises_rather_than_repeating(self):
        SpeakingPrompt.objects.filter(task="introduction").delete()
        SpeakingPrompt.objects.create(task="introduction", prompt="the only one")
        paper_a, paper_b = self._paper("A"), self._paper("B")
        sample_speaking_prompts(paper_a)
        with self.assertRaisesMessage(SamplingError, "introduction"):
            sample_speaking_prompts(paper_b)

    def test_partner_lookup_uses_the_navigation_group(self):
        paper_a = self._paper("A")
        self.assertEqual(partner_variant(paper_a.variant), "B")
```

Import whatever this test module already imports plus `AudioClip`, `ListeningQuestionSet`, `Paper`, `ReadingPassage`, `SpeakingPrompt` and `SPEAKING_TASK_ORDER`.

- [ ] **Step 2: Run to verify they fail**

```bash
python manage.py test diagnostics.tests.test_sampling -v 2
```

Expected: FAIL — `ImportError: cannot import name 'used_by_group_partner'`.

- [ ] **Step 3: Add the exclusion**

In `diagnostics/sampling.py`, extend the imports:

```python
from diagnostics.models import (
    Paper, PaperSpeakingPrompt, PaperWritingQuestion, SpeakingPrompt, WritingQuestion,
)
from diagnostics.navigation import partner_variant
```

Add this function beside `_at_cap_in_grade`:

```python
def used_by_group_partner(paper):
    """Speaking prompt ids already taken by the other paper in this room.

    A hard exclusion, not a cap: two students sitting side by side must never
    get the same speaking prompt, whatever the grade-wide budget allows. The
    cap alone was not enough - REUSE_CAPS is scoped per grade, so a prompt
    used once elsewhere in the grade was still under its cap of 2 and landed
    on both papers in a room in 10 of the 24 groups.

    Returns an empty set when the partner paper does not exist yet (the first
    paper in a room to be sampled has nothing to avoid) - so build order does
    not change the rule, only which of the pair moves.
    """
    partner = Paper.objects.filter(
        grade=paper.grade, variant=partner_variant(paper.variant)
    ).first()
    if partner is None:
        return set()
    return set(
        PaperSpeakingPrompt.objects.filter(paper=partner)
        .values_list("prompt_id", flat=True)
    )
```

Change `sample_speaking_prompts` to union the two exclusions and to name the group in its error:

```python
@transaction.atomic
def sample_speaking_prompts(paper):
    """Assign 5 speaking prompts to `paper`, one per fixed task, in task
    order: none at or above the reuse cap within the same grade, and none
    already sitting on the other paper in the same room."""
    used_ids = _at_cap_in_grade(
        PaperSpeakingPrompt, paper, "prompt", REUSE_CAPS["speaking_prompt"]
    ) | used_by_group_partner(paper)

    PaperSpeakingPrompt.objects.filter(paper=paper).delete()
    for position, task in enumerate(SPEAKING_TASK_ORDER, start=1):
        pool = list(
            SpeakingPrompt.objects.filter(task=task)
            .exclude(pk__in=used_ids)
            .values_list("pk", flat=True)
        )
        if not pool:
            raise SamplingError(
                f"Grade {paper.grade} variant {paper.variant}: no '{task}' "
                f"speaking prompts available below the reuse cap of "
                f"{REUSE_CAPS['speaking_prompt']} that are not already on the "
                f"group partner's paper."
            )
        PaperSpeakingPrompt.objects.create(
            paper=paper, prompt_id=random.choice(pool), position=position,
        )
```

Also update the module docstring's closing paragraph to record the new rule:

```
Speaking carries one extra rule the cap cannot express: the other paper in
the same room is excluded outright, at any usage count. Ten of the
twenty-four groups were sharing a prompt under the cap alone.
```

`sample_writing_questions` needs no change — its cap of 1 already gives genuine zero reuse within a grade, so a group partner can never hold the same writing question.

- [ ] **Step 4: Run to verify they pass**

```bash
python manage.py test diagnostics.tests.test_sampling -v 2
```

Expected: PASS.

- [ ] **Step 5: Check the pool arithmetic still holds**

10 prompts per task, cap 2 = 20 slots against 16 needed per grade, and the partner exclusion removes at most 1 more per task. The pool cannot be exhausted, but confirm it empirically rather than trusting the arithmetic:

```bash
python manage.py test diagnostics.tests.test_sampling -v 2
```

If `test_exhausting_a_task_pool_raises_rather_than_repeating` is the only failure, the sampler is silently repeating instead of raising — fix that before continuing.

- [ ] **Step 6: Commit**

```bash
git add diagnostics/sampling.py diagnostics/tests/test_sampling.py
git commit -m "Never give the two papers in one room the same speaking prompt"
```

---

## Part 7: Prove the four invariants

`verification.py` re-derives its answers from what is actually stored rather than calling `Paper.clean()`, precisely because sampled slots are attached after a paper is saved. The group checks follow the same rule: they read the DB, not the allocator.

### Task 7.1: The four group checks

**Files:**
- Modify: `diagnostics/verification.py`
- Create: `diagnostics/tests/test_verification_groups.py`

- [ ] **Step 1: Write the failing tests**

Create `diagnostics/tests/test_verification_groups.py`:

```python
"""The four things that must be true of every one of the 24 sittings.

These read the database, not the allocator - the same independence
find_reuse_violations has, and for the same reason: a paper written by a bulk
update or a .create() that skipped validation still has to be caught.
"""

from django.core.management import CommandError, call_command
from django.test import TestCase

from diagnostics.constants import GRADES
from diagnostics.models import (
    AudioClip, ListeningQuestionSet, Paper, ReadingPassage, SpeakingPrompt,
)
from diagnostics.navigation import GROUP_NUMBERS, variants_for_group
from diagnostics.verification import find_group_violations


class GroupVerificationTests(TestCase):
    def setUp(self):
        self.clip_a = AudioClip.objects.create(number=1, task_type="picture")
        self.clip_b = AudioClip.objects.create(number=2, task_type="mcq3")
        self.clip_c = AudioClip.objects.create(number=3, task_type="gap_fill")
        self.sets = {
            (clip.number, number): ListeningQuestionSet.objects.create(
                clip=clip, number=number
            )
            for clip in (self.clip_a, self.clip_b, self.clip_c)
            for number in (1, 2)
        }
        self.p1 = ReadingPassage.objects.create(
            label="R01", title="one", body=" ".join(["word"] * 200)
        )
        self.p2 = ReadingPassage.objects.create(
            label="R02", title="two", body=" ".join(["word"] * 200)
        )

    def _paper(self, variant, set_1, set_2, passage):
        return Paper.objects.create(
            grade=9, variant=variant,
            listening_set_1=set_1, listening_set_2=set_2, reading_passage=passage,
        )

    def _good_pair(self):
        a = self._paper("A", self.sets[(1, 1)], self.sets[(2, 1)], self.p1)
        b = self._paper("B", self.sets[(1, 2)], self.sets[(2, 2)], self.p2)
        return a, b

    def test_a_correct_group_reports_nothing(self):
        self._good_pair()
        self.assertEqual(find_group_violations(), [])

    def test_mismatched_audio_is_reported(self):
        self._paper("A", self.sets[(1, 1)], self.sets[(2, 1)], self.p1)
        self._paper("B", self.sets[(1, 2)], self.sets[(3, 2)], self.p2)
        problems = find_group_violations()
        self.assertTrue(any("recording" in p for p in problems), problems)

    def test_identical_question_sets_are_reported(self):
        self._paper("A", self.sets[(1, 1)], self.sets[(2, 1)], self.p1)
        self._paper("B", self.sets[(1, 1)], self.sets[(2, 1)], self.p2)
        problems = find_group_violations()
        self.assertTrue(any("question set" in p for p in problems), problems)

    def test_a_shared_speaking_prompt_is_reported(self):
        a, b = self._good_pair()
        prompt = SpeakingPrompt.objects.create(task="opinion", prompt="shared")
        for paper in (a, b):
            paper.speaking_slots.create(prompt=prompt, position=1)
        problems = find_group_violations()
        self.assertTrue(any("speaking prompt" in p for p in problems), problems)

    def test_a_shared_reading_passage_is_reported(self):
        self._paper("A", self.sets[(1, 1)], self.sets[(2, 1)], self.p1)
        self._paper("B", self.sets[(1, 2)], self.sets[(2, 2)], self.p1)
        problems = find_group_violations()
        self.assertTrue(any("reading passage" in p for p in problems), problems)

    def test_a_half_built_group_is_reported_not_skipped(self):
        """One paper missing is a broken sitting, not a passing one."""
        self._paper("A", self.sets[(1, 1)], self.sets[(2, 1)], self.p1)
        problems = find_group_violations()
        self.assertTrue(any("only 1" in p for p in problems), problems)

    def test_every_problem_names_its_grade_and_group(self):
        self._paper("A", self.sets[(1, 1)], self.sets[(2, 1)], self.p1)
        self._paper("B", self.sets[(1, 1)], self.sets[(3, 1)], self.p1)
        for problem in find_group_violations():
            self.assertIn("Grade 9", problem)
            self.assertIn("group 1", problem)


class GroupVerificationOnTheRealBankTests(TestCase):
    """The end-to-end assertion this whole plan exists to make true."""

    fixtures = []  # build the bank in setUp via the import + load commands

    def test_all_twenty_four_groups_pass_after_a_full_build(self):
        call_command("build_papers", "--resample")
        self.assertEqual(find_group_violations(), [])

    def test_check_papers_fails_loudly_on_a_group_violation(self):
        call_command("build_papers", "--resample")
        first = Paper.objects.get(grade=9, variant="A")
        second = Paper.objects.get(grade=9, variant="B")
        second.listening_set_1 = first.listening_set_1
        second.save(update_fields=["listening_set_1"])
        with self.assertRaisesMessage(CommandError, "question set"):
            call_command("check_papers")
```

`GroupVerificationOnTheRealBankTests` needs the full content bank. Give it the same `setUpTestData` the existing `test_build_papers.py` uses to import clips, passages, writing and speaking, then load set 2.

- [ ] **Step 2: Run to verify they fail**

```bash
python manage.py test diagnostics.tests.test_verification_groups -v 2
```

Expected: FAIL — `ImportError: cannot import name 'find_group_violations'`.

- [ ] **Step 3: Write the checks**

Append to `diagnostics/verification.py`, and extend its module docstring with:

```
The group checks below are the same idea applied to the sitting rather than
the grade: a group is two variants in one room at one time, so they must
share both recordings and share nothing else.
```

New imports:

```python
from diagnostics.navigation import GROUP_NUMBERS, variants_for_group
```

The function:

```python
def find_group_violations():
    """Return human-readable problems with the 24 exam sittings; empty is good.

    A group is two variants in one room at one time with one recording
    playing. Four things must hold, and all four are checked from what is
    stored rather than from the allocator, so a paper written by a bulk
    update is caught the same as one built by build_papers:

      G1  both papers use the same two recordings - otherwise the room needs
          two different clips playing at once, which is the defect this whole
          change exists to fix
      G2  the two papers use different question sets - otherwise, now that
          the audio is shared, they are the same listening paper
      G3  no shared speaking prompt - side-by-side students must not be
          asked to speak on the same topic
      G4  no shared reading passage
    """
    problems = []
    papers = Paper.objects.select_related(
        "listening_set_1__clip", "listening_set_2__clip", "reading_passage"
    ).prefetch_related("speaking_prompts")

    by_slot = {(paper.grade, paper.variant): paper for paper in papers}

    for grade in GRADES:
        for group in GROUP_NUMBERS:
            variants = variants_for_group(group)
            present = [by_slot[(grade, v)] for v in variants if (grade, v) in by_slot]
            label = f"Grade {grade} group {group} ({'/'.join(variants)})"

            if len(present) != len(variants):
                problems.append(
                    f"{label}: only {len(present)} of {len(variants)} papers exist; "
                    f"a sitting with a missing paper cannot be administered."
                )
                continue

            first, second = present

            recordings = [
                (p.listening_set_1.clip_id, p.listening_set_2.clip_id) for p in present
            ]
            if recordings[0] != recordings[1]:
                problems.append(
                    f"{label}: the two papers need different recordings "
                    f"(clips {first.listening_set_1.clip.number}/"
                    f"{first.listening_set_2.clip.number} against "
                    f"{second.listening_set_1.clip.number}/"
                    f"{second.listening_set_2.clip.number}); one room cannot play "
                    f"two audio files at once."
                )

            sets = [(p.listening_set_1_id, p.listening_set_2_id) for p in present]
            if sets[0] == sets[1]:
                problems.append(
                    f"{label}: both papers use the same listening question set, "
                    f"so the two students in the room sit an identical "
                    f"listening paper."
                )

            shared_prompts = (
                set(first.speaking_prompts.values_list("pk", flat=True))
                & set(second.speaking_prompts.values_list("pk", flat=True))
            )
            if shared_prompts:
                problems.append(
                    f"{label}: {len(shared_prompts)} speaking prompt(s) appear on "
                    f"both papers in the room."
                )

            if first.reading_passage_id == second.reading_passage_id:
                problems.append(
                    f"{label}: both papers use reading passage "
                    f"{first.reading_passage.label}."
                )

    return problems
```

- [ ] **Step 4: Run to verify they pass**

```bash
python manage.py test diagnostics.tests.test_verification_groups -v 2
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add diagnostics/verification.py diagnostics/tests/test_verification_groups.py
git commit -m "Verify the four group invariants from stored papers"
```

### Task 7.2: Wire the checks into check_papers

**Files:**
- Modify: `diagnostics/management/commands/check_papers.py`

- [ ] **Step 1: Add the call**

```python
"""Verify all 48 papers independently of Paper.clean(): reuse caps, section
completeness, and the four group invariants.

Run this after build_papers, and any time the content banks are re-imported.
"""

from django.core.management.base import BaseCommand, CommandError

from diagnostics.navigation import GROUPS_PER_GRADE
from diagnostics.constants import GRADES
from diagnostics.verification import (
    EXPECTED_PAPER_COUNT, find_completeness_problems, find_group_violations,
    find_reuse_violations,
)

EXPECTED_GROUP_COUNT = len(GRADES) * GROUPS_PER_GRADE


class Command(BaseCommand):
    help = (
        "Verify reuse caps, section completeness, and that every exam sitting "
        "shares its audio and nothing else."
    )

    def handle(self, *args, **options):
        problems = (
            find_completeness_problems()
            + find_reuse_violations()
            + find_group_violations()
        )
        if problems:
            raise CommandError("Verification failed:\n  " + "\n  ".join(problems))

        self.stdout.write(self.style.SUCCESS(
            f"All {EXPECTED_PAPER_COUNT} papers pass: complete sections, no "
            f"component shared beyond its reuse cap within any grade, and all "
            f"{EXPECTED_GROUP_COUNT} sittings share one recording pair while "
            f"sharing no questions, prompt or passage."
        ))
```

- [ ] **Step 2: Run it against the live bank**

```bash
python manage.py check_papers
```

Expected at this point: **FAILS**, listing 24 recording mismatches. The papers in the DB were built by the old allocator; Part 8 rebuilds them. A pass here before the rebuild would mean the check is not actually looking at stored data.

- [ ] **Step 3: Commit**

```bash
git add diagnostics/management/commands/check_papers.py
git commit -m "Run the group invariants as part of check_papers"
```

### Task 7.3: Make build_papers roll back on a group violation

**Files:**
- Modify: `diagnostics/management/commands/build_papers.py`

- [ ] **Step 1: Add the check inside the transaction**

If Task 5.2 Step 3 already added this line, confirm it and skip to Step 2. Otherwise, in the `with transaction.atomic():` block, replace:

```python
                problems = find_reuse_violations()
                if problems:
                    raise CommandError(
                        "Build produced a reuse-cap violation, rolling back:\n  "
                        + "\n  ".join(problems)
                    )
```

with:

```python
                problems = find_reuse_violations() + find_group_violations()
                if problems:
                    raise CommandError(
                        "Build produced an invalid bank, rolling back:\n  "
                        + "\n  ".join(problems)
                    )
```

and extend the import:

```python
from diagnostics.verification import find_group_violations, find_reuse_violations
```

- [ ] **Step 2: Run the full suite**

```bash
python manage.py test
```

Expected: 880+ tests, 0 failures.

- [ ] **Step 3: Commit**

```bash
git add diagnostics/management/commands/build_papers.py
git commit -m "Roll the build back if it produces a broken exam sitting"
```

---

## Part 8: Rebuild, re-issue, document

Every one of the 48 papers gets new listening content when this ships. **Anything already printed or downloaded is superseded.** This Part is as much a communication task as a code task.

### Task 8.1: Rebuild the bank

- [ ] **Step 1: Back up the database first**

The rebuild rewrites listening on all 48 papers and, with `--resample`, redraws speaking. It is reversible only from a backup.

```bash
cp db.sqlite3 "db.sqlite3.pre-groups-$(date +%Y%m%d)"
```

- [ ] **Step 2: Rebuild**

`--resample` is required: the speaking prompts must be redrawn for the group exclusion to take effect on the 10 leaking groups. Without it, papers that already have their full complement are left untouched and the leaks survive.

```bash
python manage.py build_papers --resample
```

Expected: `Built 48 papers (48 sampled, 0 already complete and left unchanged).`

- [ ] **Step 3: Verify**

```bash
python manage.py check_papers
```

Expected: the success line, naming 48 papers and 24 sittings. **This is the finish line for the whole plan.**

- [ ] **Step 4: Re-confirm the audit numbers have flipped**

Run the same shape of query that produced the original audit, so the before/after is measured the same way:

```bash
python manage.py shell -c "
from diagnostics.models import Paper
from diagnostics.constants import GRADES
from diagnostics.navigation import GROUP_NUMBERS, variants_for_group
mismatch = leaks = shared = 0
for grade in GRADES:
    for group in GROUP_NUMBERS:
        a, b = [Paper.objects.get(grade=grade, variant=v) for v in variants_for_group(group)]
        if (a.listening_set_1.clip_id, a.listening_set_2.clip_id) != (b.listening_set_1.clip_id, b.listening_set_2.clip_id): mismatch += 1
        if set(a.speaking_prompts.values_list('pk', flat=True)) & set(b.speaking_prompts.values_list('pk', flat=True)): leaks += 1
        if a.reading_passage_id == b.reading_passage_id: shared += 1
print('audio mismatch:', mismatch, 'of 24')
print('shared speaking prompt:', leaks, 'of 24')
print('shared reading passage:', shared, 'of 24')
"
```

Expected, all three:

```
audio mismatch: 0 of 24
shared speaking prompt: 0 of 24
shared reading passage: 0 of 24
```

- [ ] **Step 5: Re-sign the listening keys**

```bash
python manage.py verify_listening_keys
```

The fingerprint changed when set 2 landed (section 0.8), so the previous sign-off has lapsed. A human must check all 200 answers before re-signing.

- [ ] **Step 6: Spot-check one group's papers by eye**

```bash
python manage.py render_paper 9 A --format docx
python manage.py render_paper 9 B --format docx
```

Open both. They must name the **same two recordings** and carry **different questions**. If clip 1 is a picture clip, expect 3 of its 5 picture questions to appear on both — that is the documented residual (section 0.5), not a bug.

### Task 8.2: Write up the limitation and the re-issue

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a section to README.md**

```markdown
### Exam groups and listening question sets

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
```

- [ ] **Step 2: Note the re-issue**

Add immediately after:

```markdown
**Re-issue, 2026-08-31.** All 48 papers were rebuilt when groups landed. Every
paper's listening section changed, and speaking prompts were redrawn. **Any
paper printed or downloaded before this date is superseded** — re-download from
the class pack screen before administering.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Document exam groups, the picture-clip residual and the re-issue"
```

### Task 8.3: Tell the people holding old papers

- [ ] **Step 1: Confirm who has downloaded**

`GenerationEvent` (`diagnostics/models/tracking.py`) records downloads. List who pulled a paper before the rebuild:

```bash
python manage.py shell -c "from diagnostics.models import GenerationEvent; print(sorted({(e.paper_id, str(e.created_at.date())) for e in GenerationEvent.objects.all()}))"
```

- [ ] **Step 2: Notify them**

Not a code step. Every teacher on that list is holding a superseded paper. **This is not optional** — an un-notified teacher administers a listening test whose recording no longer matches their answer key.

---

## Self-review

**Spec coverage** — every numbered requirement from the brief maps to a task:

| Brief item | Tasks |
|---|---|
| 1. Schema migration, set model, FK moves, compat properties | 3.1-3.5 |
| 2. navigation.py group model | 2.1 |
| 3. allocation.py group-aware, one clip pair per group | 5.1, 5.2 |
| 4. sampling.py hard group-partner exclusion | 6.1 |
| 5. verification.py four group checks | 7.1-7.3 |
| 6. Content loading: 10 images, 75 questions, 4 stem fixes | 1.1-1.3, 4.1-4.4 |
| 7. Picture residual written up as accepted limitation | 0.5, 8.2 |
| 8. Full re-issue of all 48 papers flagged | 0.8, 8.1, 8.3 |

**Three things the brief did not cover, added here:**

- The brief's assumption that `rendering.py` needs no change is wrong — `_clip_section` reads `clip.questions`. Handled in Task 3.7 and called out in section 0.9.
- `KeyVerification.current_fingerprint` must gain the set number, or the two sets collide in the digest; and adding set 2 lapses the existing sign-off. Sections 0.8, Task 3.1, Task 8.1 Step 5.
- `import_listening` re-derives stems from the source `.md` on every run, so a DB-only stem fix would be silently undone. Task 1.2 puts the correction in the importer as well as Task 1.3's migration.

**Type consistency check:** `Allocation` is used with the field names `picture_clip`, `rotating_clip`, `set_number`, `passage` in Tasks 5.1 and 5.2 — consistent. `ListeningQuestionSet` fields are `clip` and `number` throughout. `find_group_violations` has the same name in Tasks 5.2, 7.1, 7.2 and 7.3. `used_by_group_partner` and `partner_variant` are defined in Tasks 6.1 and 2.1 and used only after.

**Open risk, flagged not solved:** Task 5.2's test fixtures need a full two-set content bank, which the existing `test_build_papers.py` fixture does not build. Whoever executes Task 5.2 should extract that fixture into a shared helper rather than copying it into three test modules.

---

## Appendix: verification queries used to build this plan

Run against `db.sqlite3` on 2026-08-31 to confirm the audit rather than assume it. Kept here so the before/after comparison in Task 8.1 Step 4 measures the same thing.

```python
import sqlite3
db = sqlite3.connect("db.sqlite3")
c = db.cursor()
VARIANTS = "ABCDEFGHIJKLMNOP"

rows = c.execute("""SELECT p.grade, p.variant, c1.number, c2.number
FROM diagnostics_paper p
JOIN diagnostics_audioclip c1 ON c1.id = p.listening_clip_1_id
JOIN diagnostics_audioclip c2 ON c2.id = p.listening_clip_2_id""").fetchall()
by = {(g, v): (a, b) for g, v, a, b in rows}
mismatch = sum(
    by[(g, VARIANTS[i])] != by[(g, VARIANTS[i + 1])]
    for g in (9, 10, 11) for i in range(0, 16, 2)
)
print("groups audio MISMATCH:", mismatch)
```

Result: `24` of 24 mismatch, `10` of 24 leak a speaking prompt, `0` of 24 share a reading passage. All four stem bugs confirmed verbatim in the DB. 35 jpgs present under `media/diagnostics/listening/` (25 original + 10 new). `media/diagnostics/audio/transcripts-full.md` present, 40.5 KB, all 20 clips.

*Note: after Part 3 these queries must join through `listening_set_1__clip` instead — the raw-SQL form above only works on the pre-migration schema, which is why Task 8.1 Step 4 uses the ORM version.*
