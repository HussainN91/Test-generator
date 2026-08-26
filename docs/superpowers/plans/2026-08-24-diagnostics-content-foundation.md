# Diagnostics Content Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `diagnostics` Django app's data layer and content pipeline, ending with 12 fixed diagnostic papers in the database — uniqueness-verified and renderable to `.docx`.

**Architecture:** A new `diagnostics` app inside `D:\Test generator`, importing nothing from `bank` or `content`. Listening content is *extracted* from client source files (20 MP3s, a `.docx` holding 25 images, a `.md` holding 20 worksheets); reading/writing/speaking content is *authored* as validated JSON. A `Paper` is five foreign keys chosen by a hardcoded allocation table, guarded by an automated within-grade uniqueness test.

**Tech Stack:** Django 5.2, Python 3.14, SQLite, `python-docx`, Django `TestCase`. No new dependencies.

**Source spec:** `docs/superpowers/specs/2026-08-24-diagnostic-test-generator-design.md`

**Covers spec phases 0–3.** Phases 4–6 (teacher UI, export packs, tracking, merge seams) are a separate plan.

---

## Conventions for this plan

- **Working directory** is always `D:\Test generator`.
- **Python** is `.venv\Scripts\python.exe`. Every command below assumes it.
- **This project has no version control** — by the user's explicit decision. There are no commit steps. Each task ends with a **Checkpoint** that runs the suite instead.
- Tests live in a `diagnostics/tests/` package, run with `python manage.py test diagnostics`.
- Source files live in `D:\Diagnostics Gate` and are **read-only**. Never modify them.

## File structure

| File | Responsibility |
|---|---|
| `diagnostics/apps.py` | App config |
| `diagnostics/constants.py` | Static facts about the 20-clip bank: task types, image mapping, paper allocation |
| `diagnostics/models/__init__.py` | Re-exports so `from diagnostics.models import X` works |
| `diagnostics/models/content.py` | `AudioClip`, `ListeningQuestion`, `ReadingPassage`, `ReadingQuestion`, `WritingSet`, `WritingQuestion`, `SpeakingSet`, `SpeakingPrompt` |
| `diagnostics/models/paper.py` | `Paper` + within-grade uniqueness validation |
| `diagnostics/models/tracking.py` | `TeacherGradeAssignment`, `GenerationEvent`, `GenerationWindow` |
| `diagnostics/extraction/docx_images.py` | Pull 25 images out of the `.docx` in **document order** |
| `diagnostics/extraction/worksheets.py` | Split the `.md` into 20 clips with stems |
| `diagnostics/extraction/keys.py` | Tolerant answer-key parser (six source formats) |
| `diagnostics/extraction/audio.py` | Map inconsistent MP3 filenames to clip numbers |
| `diagnostics/authored/schema.py` | Validators for authored reading/writing/speaking JSON |
| `diagnostics/management/commands/*.py` | `extract_listening_assets`, `import_listening`, `verify_listening_keys`, `import_authored`, `build_papers`, `check_papers`, `render_paper` |
| `diagnostics/tests/*.py` | One test module per concern |

`models` and `extraction` are packages rather than flat modules because this app carries 12 models and four distinct parsers; the existing apps' flat `models.py` files hold 3–5 models each and don't face the same pressure.

---

### Task 1: App scaffold and settings

**Files:**
- Create: `diagnostics/__init__.py`, `diagnostics/apps.py`, `diagnostics/models/__init__.py`, `diagnostics/tests/__init__.py`
- Modify: `config/settings.py`
- Test: `diagnostics/tests/test_settings.py`

- [ ] **Step 1: Write the failing test**

Create `diagnostics/tests/test_settings.py`:

```python
"""The app must be installed and its source/media paths configured."""

from django.apps import apps
from django.conf import settings
from django.test import TestCase


class AppInstallationTests(TestCase):
    def test_diagnostics_app_is_installed(self):
        self.assertTrue(apps.is_installed("diagnostics"))

    def test_media_root_is_configured(self):
        self.assertTrue(str(settings.MEDIA_ROOT).endswith("media"))
        self.assertEqual(settings.MEDIA_URL, "media/")

    def test_diagnostics_source_dir_is_configured(self):
        self.assertTrue(hasattr(settings, "DIAGNOSTICS_SOURCE_DIR"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'diagnostics'`

- [ ] **Step 3: Create the app package**

Create `diagnostics/__init__.py` (empty), `diagnostics/models/__init__.py` (empty for now), `diagnostics/tests/__init__.py` (empty).

Create `diagnostics/apps.py`:

```python
from django.apps import AppConfig


class DiagnosticsAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "diagnostics"
    verbose_name = "Diagnostic tests"
```

Create `diagnostics/migrations/__init__.py` (empty).

- [ ] **Step 4: Register in settings**

In `config/settings.py`, add `"diagnostics",` to the end of `INSTALLED_APPS` (after `"assembly",`).

Then add below the `STATIC_ROOT` line:

```python
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Read-only client source material for the diagnostic test bank.
DIAGNOSTICS_SOURCE_DIR = Path(
    os.environ.get("DIAGNOSTICS_SOURCE_DIR", r"D:\Diagnostics Gate")
)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe manage.py test diagnostics -v 2`
Expected: PASS, 3 tests

- [ ] **Step 6: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py check`
Expected: `System check identified no issues`

---

### Task 2: Static constants for the 20-clip bank

**Files:**
- Create: `diagnostics/constants.py`
- Test: `diagnostics/tests/test_constants.py`

These are verified facts about fixed client content, not inferred data. Hardcoding them is correct — heuristic detection over 20 static files would be more code and less reliable.

- [ ] **Step 1: Write the failing test**

Create `diagnostics/tests/test_constants.py`:

```python
"""The bank's shape is fixed and verified; these tests lock it in."""

from collections import Counter

from django.test import TestCase

from diagnostics.constants import (
    CLIP_TASK_TYPES,
    IMAGE_SLOTS,
    PAPER_ALLOCATION,
    PROFILE_X,
    PROFILE_Y,
    TaskType,
)


class ClipTaskTypeTests(TestCase):
    def test_all_twenty_clips_are_typed(self):
        self.assertEqual(sorted(CLIP_TASK_TYPES), list(range(1, 21)))

    def test_bank_is_balanced_five_of_each_type(self):
        counts = Counter(CLIP_TASK_TYPES.values())
        self.assertEqual(
            counts,
            Counter({TaskType.PICTURE: 5, TaskType.MCQ3: 5,
                     TaskType.GAP_FILL: 5, TaskType.TRUE_FALSE: 5}),
        )


class ImageSlotTests(TestCase):
    def test_twenty_five_slots_in_document_order(self):
        self.assertEqual(len(IMAGE_SLOTS), 25)

    def test_slots_group_five_per_picture_clip(self):
        self.assertEqual(IMAGE_SLOTS[0], (1, 1))
        self.assertEqual(IMAGE_SLOTS[4], (1, 5))
        self.assertEqual(IMAGE_SLOTS[5], (5, 1))
        self.assertEqual(IMAGE_SLOTS[24], (15, 5))

    def test_slots_only_reference_picture_clips(self):
        clips = {clip for clip, _ in IMAGE_SLOTS}
        self.assertEqual(clips, {1, 5, 9, 13, 15})


class AllocationTests(TestCase):
    def test_twelve_papers(self):
        self.assertEqual(len(PAPER_ALLOCATION), 12)

    def test_no_repetition_within_a_grade(self):
        for grade in (9, 10, 11):
            clips = []
            for (g, _variant), pair in PAPER_ALLOCATION.items():
                if g == grade:
                    clips.extend(pair)
            self.assertEqual(len(clips), 8)
            self.assertEqual(len(set(clips)), 8, f"grade {grade} repeats a clip")

    def test_every_clip_is_used(self):
        used = {c for pair in PAPER_ALLOCATION.values() for c in pair}
        self.assertEqual(used, set(range(1, 21)))

    def test_exactly_four_clips_are_reused(self):
        used = [c for pair in PAPER_ALLOCATION.values() for c in pair]
        self.assertEqual(len(used) - len(set(used)), 4)

    def test_each_grade_gets_two_of_each_profile(self):
        for grade in (9, 10, 11):
            profiles = []
            for (g, _variant), (a, b) in PAPER_ALLOCATION.items():
                if g != grade:
                    continue
                types = {CLIP_TASK_TYPES[a], CLIP_TASK_TYPES[b]}
                if types == PROFILE_X:
                    profiles.append("X")
                elif types == PROFILE_Y:
                    profiles.append("Y")
                else:
                    self.fail(f"grade {grade} pair {(a, b)} matches no profile")
            self.assertEqual(sorted(profiles), ["X", "X", "Y", "Y"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_constants -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'diagnostics.constants'`

- [ ] **Step 3: Write the implementation**

Create `diagnostics/constants.py`:

```python
"""Verified static facts about the client's 20-clip listening bank.

Everything here was checked against the source files on 2026-08-24. These are
not guesses to be re-derived at runtime — the bank is fixed content.
"""

from django.db import models


class TaskType(models.TextChoices):
    PICTURE = "picture", "Picture MCQ (A/B/C)"
    MCQ3 = "mcq3", "3-option multiple choice"
    GAP_FILL = "gap_fill", "Note/form gap-fill"
    TRUE_FALSE = "true_false", "True/False (YES/NO)"


#: Which task type each of the 20 clips uses. The bank is balanced 5/5/5/5.
CLIP_TASK_TYPES = {
    1: TaskType.PICTURE, 5: TaskType.PICTURE, 9: TaskType.PICTURE,
    13: TaskType.PICTURE, 15: TaskType.PICTURE,

    2: TaskType.MCQ3, 6: TaskType.MCQ3, 10: TaskType.MCQ3,
    14: TaskType.MCQ3, 16: TaskType.MCQ3,

    3: TaskType.GAP_FILL, 7: TaskType.GAP_FILL, 11: TaskType.GAP_FILL,
    18: TaskType.GAP_FILL, 19: TaskType.GAP_FILL,

    4: TaskType.TRUE_FALSE, 8: TaskType.TRUE_FALSE, 12: TaskType.TRUE_FALSE,
    17: TaskType.TRUE_FALSE, 20: TaskType.TRUE_FALSE,
}

#: Task types whose answers are a single letter A/B/C.
LETTER_ANSWER_TYPES = frozenset({TaskType.PICTURE, TaskType.MCQ3, TaskType.TRUE_FALSE})

#: Difficulty-balancing profiles (spec 3.1).
#: X pairs the hardest type with the easiest; Y pairs the two middles.
PROFILE_X = frozenset({TaskType.GAP_FILL, TaskType.TRUE_FALSE})
PROFILE_Y = frozenset({TaskType.PICTURE, TaskType.MCQ3})

#: The 25 images appear in the .docx in document order, five per picture clip,
#: in ascending clip order. Index -> (clip number, question position).
IMAGE_SLOTS = [
    (clip, position)
    for clip in (1, 5, 9, 13, 15)
    for position in (1, 2, 3, 4, 5)
]

#: The fixed 12-paper listening allocation (spec 3.2).
#: Grades 9 and 10 are entirely fresh; grade 11 re-uses exactly four clips,
#: recombined so no whole paper is ever duplicated.
PAPER_ALLOCATION = {
    (9, "A"): (1, 2),
    (9, "B"): (3, 4),
    (9, "C"): (5, 6),
    (9, "D"): (7, 8),

    (10, "A"): (9, 10),
    (10, "B"): (11, 12),
    (10, "C"): (13, 14),
    (10, "D"): (18, 17),

    (11, "A"): (15, 16),
    (11, "B"): (19, 20),
    (11, "C"): (9, 6),
    (11, "D"): (7, 12),
}

#: Papers in canonical order, used to assign authored content sets R01..R12 etc.
PAPER_ORDER = [
    (9, "A"), (9, "B"), (9, "C"), (9, "D"),
    (10, "A"), (10, "B"), (10, "C"), (10, "D"),
    (11, "A"), (11, "B"), (11, "C"), (11, "D"),
]

GRADES = (9, 10, 11)
VARIANTS = ("A", "B", "C", "D")

#: Option letters used by every four-option question type.
OPTION_LETTERS = ["A", "B", "C", "D"]

#: Reading passage length bounds (spec 1.1).
MIN_PASSAGE_WORDS = 150
MAX_PASSAGE_WORDS = 180

#: Required question counts per subtype, per set (spec 3.3).
#: Defined here once; both the models and the authored-content validators
#: import them, so the two can never disagree about the pattern.
READING_SUBTYPE_COUNTS = {"true_false_ng": 5, "mcq": 3, "completion": 2}
WRITING_SUBTYPE_COUNTS = {"grammar": 3, "vocabulary": 2, "jumbled": 3, "fill_blank": 2}
SPEAKING_TASK_ORDER = ["introduction", "experience", "description", "role_play", "opinion"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_constants -v 2`
Expected: PASS, 9 tests

- [ ] **Step 5: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics`
Expected: OK

---

### Task 3: Listening content models

**Files:**
- Create: `diagnostics/models/content.py`
- Modify: `diagnostics/models/__init__.py`
- Test: `diagnostics/tests/test_models_listening.py`

- [ ] **Step 1: Write the failing test**

Create `diagnostics/tests/test_models_listening.py`:

```python
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.test import TestCase

from diagnostics.constants import TaskType
from diagnostics.models import AudioClip, ListeningQuestion


class AudioClipTests(TestCase):
    def test_clip_number_is_unique(self):
        AudioClip.objects.create(number=1, task_type=TaskType.PICTURE)
        with self.assertRaises(IntegrityError):
            AudioClip.objects.create(number=1, task_type=TaskType.MCQ3)

    def test_str_shows_number_and_type(self):
        clip = AudioClip.objects.create(number=3, task_type=TaskType.GAP_FILL)
        self.assertEqual(str(clip), "Clip 3 (Note/form gap-fill)")


class ListeningQuestionTests(TestCase):
    def setUp(self):
        self.clip = AudioClip.objects.create(number=2, task_type=TaskType.MCQ3)

    def test_position_is_unique_within_a_clip(self):
        ListeningQuestion.objects.create(clip=self.clip, position=1, stem="a", answer="A")
        with self.assertRaises(IntegrityError):
            ListeningQuestion.objects.create(clip=self.clip, position=1, stem="b", answer="B")

    def test_position_must_be_one_to_five(self):
        question = ListeningQuestion(clip=self.clip, position=6, stem="x", answer="A")
        with self.assertRaises(ValidationError):
            question.full_clean()

    def test_accepts_alternatives_for_gap_fill(self):
        clip = AudioClip.objects.create(number=3, task_type=TaskType.GAP_FILL)
        question = ListeningQuestion.objects.create(
            clip=clip, position=1, stem="...", answer="twenty",
            acceptable_answers=["20", "twenty"],
        )
        self.assertIn("20", question.acceptable_answers)

    def test_ordering_is_by_clip_then_position(self):
        for position in (3, 1, 2):
            ListeningQuestion.objects.create(
                clip=self.clip, position=position, stem="s", answer="A"
            )
        self.assertEqual(
            [q.position for q in ListeningQuestion.objects.all()], [1, 2, 3]
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_models_listening -v 2`
Expected: FAIL — `ImportError: cannot import name 'AudioClip'`

- [ ] **Step 3: Write the implementation**

Create `diagnostics/models/content.py`:

```python
"""Authored and extracted diagnostic content (spec 4.2, content layer).

Static: written once by the offline pipeline, read-only at runtime.
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from diagnostics.constants import MAX_PASSAGE_WORDS, MIN_PASSAGE_WORDS, TaskType


def _position_validators(maximum):
    return [MinValueValidator(1), MaxValueValidator(maximum)]


class AudioClip(models.Model):
    """One of the client's 20 listening clips."""

    number = models.PositiveSmallIntegerField(unique=True)
    task_type = models.CharField(max_length=16, choices=TaskType.choices)
    intro_text = models.TextField(
        blank=True, help_text='The "You will hear..." framing read before the clip.'
    )
    audio_file = models.FileField(upload_to="diagnostics/audio/", blank=True)

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return f"Clip {self.number} ({TaskType(self.task_type).label})"


class ListeningQuestion(models.Model):
    clip = models.ForeignKey(AudioClip, on_delete=models.CASCADE, related_name="questions")
    position = models.PositiveSmallIntegerField(validators=_position_validators(5))
    stem = models.TextField()
    options = models.JSONField(
        default=list, blank=True,
        help_text="Option texts for mcq3/true_false. Empty for picture and gap-fill.",
    )
    image = models.ImageField(
        upload_to="diagnostics/listening/", blank=True,
        help_text="Picture clips only: the A/B/C option strip for this question.",
    )
    answer = models.CharField(max_length=200)
    acceptable_answers = models.JSONField(
        default=list, blank=True, help_text="Alternative correct answers for gap-fill."
    )

    class Meta:
        ordering = ["clip__number", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["clip", "position"], name="unique_listening_position"
            )
        ]

    def __str__(self):
        return f"Clip {self.clip.number} Q{self.position}"
```

Update `diagnostics/models/__init__.py`:

```python
from diagnostics.models.content import AudioClip, ListeningQuestion

__all__ = ["AudioClip", "ListeningQuestion"]
```

- [ ] **Step 4: Create the migration**

Run: `.venv\Scripts\python.exe manage.py makemigrations diagnostics`
Expected: `Create model AudioClip`, `Create model ListeningQuestion`

`ImageField` requires Pillow. If the command errors with `Cannot use ImageField because Pillow is not installed`, run `.venv\Scripts\python.exe -m pip install Pillow` and add `Pillow>=10.0   # ImageField for listening picture options` to `requirements.txt`, then re-run.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_models_listening -v 2`
Expected: PASS, 5 tests

- [ ] **Step 6: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics`
Expected: OK

---

### Task 4: Reading, writing and speaking models

**Files:**
- Modify: `diagnostics/models/content.py`, `diagnostics/models/__init__.py`
- Test: `diagnostics/tests/test_models_authored.py`

- [ ] **Step 1: Write the failing test**

Create `diagnostics/tests/test_models_authored.py`:

```python
from django.core.exceptions import ValidationError
from django.test import TestCase

from diagnostics.models import (
    ReadingPassage, ReadingQuestion, ReadingSubtype,
    SpeakingPrompt, SpeakingSet, SpeakingTask,
    WritingQuestion, WritingSet, WritingSubtype,
)


class ReadingTests(TestCase):
    def test_word_count_is_derived_on_save(self):
        passage = ReadingPassage.objects.create(
            label="R01", title="T", body="one two three four five"
        )
        self.assertEqual(passage.word_count, 5)

    def test_body_outside_150_to_180_words_is_invalid(self):
        passage = ReadingPassage(label="R02", title="T", body="too short")
        with self.assertRaises(ValidationError):
            passage.full_clean()

    def test_body_within_range_is_valid(self):
        passage = ReadingPassage(label="R03", title="T", body=" ".join(["word"] * 165))
        passage.full_clean()

    def test_subtypes_are_the_version_one_shape(self):
        self.assertEqual(
            [s.value for s in ReadingSubtype],
            ["true_false_ng", "mcq", "completion"],
        )


class WritingTests(TestCase):
    def test_subtypes_match_the_pattern(self):
        self.assertEqual(
            [s.value for s in WritingSubtype],
            ["grammar", "vocabulary", "jumbled", "fill_blank"],
        )

    def test_question_belongs_to_a_set(self):
        writing_set = WritingSet.objects.create(label="W01")
        question = WritingQuestion.objects.create(
            set=writing_set, position=1, subtype=WritingSubtype.GRAMMAR,
            stem="Maria ___ to work by bus.", options=["go", "goes", "going", "gone"],
            answer="B",
        )
        self.assertEqual(question.set.label, "W01")


class SpeakingTests(TestCase):
    def test_five_fixed_task_slots(self):
        self.assertEqual(len(SpeakingTask.choices), 5)

    def test_prompt_defaults_to_two_marks(self):
        speaking_set = SpeakingSet.objects.create(label="S01")
        prompt = SpeakingPrompt.objects.create(
            set=speaking_set, position=1, task=SpeakingTask.INTRODUCTION,
            prompt="What is your name?",
        )
        self.assertEqual(prompt.marks, 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_models_authored -v 2`
Expected: FAIL — `ImportError: cannot import name 'ReadingPassage'`

- [ ] **Step 3: Write the implementation**

Append to `diagnostics/models/content.py`:

```python
class ReadingSubtype(models.TextChoices):
    TRUE_FALSE_NG = "true_false_ng", "TRUE / FALSE / NOT GIVEN"
    MCQ = "mcq", "Four-option multiple choice"
    COMPLETION = "completion", "Sentence completion (max two words)"


class ReadingPassage(models.Model):
    label = models.CharField(max_length=8, unique=True, help_text="R01..R12")
    title = models.CharField(max_length=255)
    body = models.TextField()
    word_count = models.PositiveSmallIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["label"]

    def __str__(self):
        return f"{self.label} — {self.title}"

    def save(self, *args, **kwargs):
        self.word_count = len(self.body.split())
        super().save(*args, **kwargs)

    def clean(self):
        count = len(self.body.split())
        if not MIN_PASSAGE_WORDS <= count <= MAX_PASSAGE_WORDS:
            raise ValidationError(
                {"body": f"Passage must be {MIN_PASSAGE_WORDS}-{MAX_PASSAGE_WORDS} "
                         f"words; this one is {count}."}
            )


class ReadingQuestion(models.Model):
    passage = models.ForeignKey(
        ReadingPassage, on_delete=models.CASCADE, related_name="questions"
    )
    position = models.PositiveSmallIntegerField(validators=_position_validators(10))
    subtype = models.CharField(max_length=16, choices=ReadingSubtype.choices)
    stem = models.TextField()
    options = models.JSONField(default=list, blank=True)
    answer = models.CharField(max_length=200)
    acceptable_answers = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["passage__label", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["passage", "position"], name="unique_reading_position"
            )
        ]

    def __str__(self):
        return f"{self.passage.label} Q{self.position}"


class WritingSubtype(models.TextChoices):
    GRAMMAR = "grammar", "Grammar"
    VOCABULARY = "vocabulary", "Vocabulary"
    JUMBLED = "jumbled", "Jumbled paragraph"
    FILL_BLANK = "fill_blank", "Fill in the blanks"


class WritingSet(models.Model):
    label = models.CharField(max_length=8, unique=True, help_text="W01..W12")

    class Meta:
        ordering = ["label"]

    def __str__(self):
        return self.label


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


class SpeakingTask(models.TextChoices):
    INTRODUCTION = "introduction", "Personal introduction and familiar topic"
    EXPERIENCE = "experience", "Describe an experience or event"
    DESCRIPTION = "description", "Topic description and comparison"
    ROLE_PLAY = "role_play", "Role play / problem solving"
    OPINION = "opinion", "Opinion and discussion"


class SpeakingSet(models.Model):
    label = models.CharField(max_length=8, unique=True, help_text="S01..S12")

    class Meta:
        ordering = ["label"]

    def __str__(self):
        return self.label


class SpeakingPrompt(models.Model):
    set = models.ForeignKey(SpeakingSet, on_delete=models.CASCADE, related_name="prompts")
    position = models.PositiveSmallIntegerField(validators=_position_validators(5))
    task = models.CharField(max_length=16, choices=SpeakingTask.choices)
    prompt = models.TextField()
    bullets = models.JSONField(default=list, blank=True)
    marks = models.PositiveSmallIntegerField(default=2)

    class Meta:
        ordering = ["set__label", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["set", "position"], name="unique_speaking_position"
            )
        ]

    def __str__(self):
        return f"{self.set.label} Q{self.position}"
```

Add the import at the top of `diagnostics/models/content.py`, beside the existing imports:

```python
from django.core.exceptions import ValidationError
```

Replace `diagnostics/models/__init__.py` with:

```python
from diagnostics.models.content import (
    AudioClip, ListeningQuestion,
    ReadingPassage, ReadingQuestion, ReadingSubtype,
    SpeakingPrompt, SpeakingSet, SpeakingTask,
    WritingQuestion, WritingSet, WritingSubtype, WRITING_SUBTYPE_COUNTS,
)

__all__ = [
    "AudioClip", "ListeningQuestion",
    "ReadingPassage", "ReadingQuestion", "ReadingSubtype",
    "SpeakingPrompt", "SpeakingSet", "SpeakingTask",
    "WritingQuestion", "WritingSet", "WritingSubtype", "WRITING_SUBTYPE_COUNTS",
]
```

- [ ] **Step 4: Create the migration**

Run: `.venv\Scripts\python.exe manage.py makemigrations diagnostics`
Expected: creates 6 models

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_models_authored -v 2`
Expected: PASS, 7 tests

- [ ] **Step 6: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics`
Expected: OK

---

### Task 5: Paper model with within-grade uniqueness

This is the rule the client called inviolable. It gets validation *and* a test.

**Files:**
- Create: `diagnostics/models/paper.py`
- Modify: `diagnostics/models/__init__.py`
- Test: `diagnostics/tests/test_models_paper.py`

- [ ] **Step 1: Write the failing test**

Create `diagnostics/tests/test_models_paper.py`:

```python
from django.core.exceptions import ValidationError
from django.test import TestCase

from diagnostics.constants import TaskType
from diagnostics.models import (
    AudioClip, Paper, ReadingPassage, SpeakingSet, WritingSet,
)


def make_paper(grade, variant, clip_a, clip_b, suffix):
    return Paper(
        grade=grade,
        variant=variant,
        listening_clip_1=clip_a,
        listening_clip_2=clip_b,
        reading_passage=ReadingPassage.objects.create(
            label=f"R{suffix}", title="T", body=" ".join(["word"] * 160)
        ),
        writing_set=WritingSet.objects.create(label=f"W{suffix}"),
        speaking_set=SpeakingSet.objects.create(label=f"S{suffix}"),
    )


class PaperUniquenessTests(TestCase):
    def setUp(self):
        self.clips = {
            n: AudioClip.objects.create(number=n, task_type=TaskType.MCQ3)
            for n in range(1, 9)
        }

    def test_valid_paper_saves(self):
        paper = make_paper(9, "A", self.clips[1], self.clips[2], "01")
        paper.full_clean()
        paper.save()
        self.assertEqual(Paper.objects.count(), 1)

    def test_a_paper_cannot_use_the_same_clip_twice(self):
        paper = make_paper(9, "A", self.clips[1], self.clips[1], "01")
        with self.assertRaises(ValidationError) as ctx:
            paper.full_clean()
        self.assertIn("twice", str(ctx.exception))

    def test_clip_reuse_within_a_grade_is_rejected(self):
        make_paper(9, "A", self.clips[1], self.clips[2], "01").save()
        clash = make_paper(9, "B", self.clips[2], self.clips[3], "02")
        with self.assertRaises(ValidationError) as ctx:
            clash.full_clean()
        self.assertIn("Grade 9", str(ctx.exception))

    def test_clip_reuse_across_grades_is_allowed(self):
        make_paper(9, "A", self.clips[1], self.clips[2], "01").save()
        other = make_paper(11, "C", self.clips[2], self.clips[3], "02")
        other.full_clean()
        other.save()
        self.assertEqual(Paper.objects.count(), 2)

    def test_reading_passage_reuse_within_a_grade_is_rejected(self):
        first = make_paper(9, "A", self.clips[1], self.clips[2], "01")
        first.save()
        clash = make_paper(9, "B", self.clips[3], self.clips[4], "02")
        clash.reading_passage = first.reading_passage
        with self.assertRaises(ValidationError) as ctx:
            clash.full_clean()
        self.assertIn("Grade 9", str(ctx.exception))

    def test_str_is_the_paper_code(self):
        paper = make_paper(10, "C", self.clips[1], self.clips[2], "01")
        self.assertEqual(str(paper), "G10-C")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_models_paper -v 2`
Expected: FAIL — `ImportError: cannot import name 'Paper'`

- [ ] **Step 3: Write the implementation**

Create `diagnostics/models/paper.py`:

```python
"""The twelve fixed diagnostic papers (spec 4.2, paper layer).

A paper is five foreign keys. There is no sampling: the allocation is fixed by
`diagnostics.constants.PAPER_ALLOCATION` and asserted here.

`clean()` enforces the one rule the client called inviolable — the four
variants within a grade share nothing. Cross-grade re-use is permitted and
expected (grade 11 borrows four clips).
"""

from django.core.exceptions import ValidationError
from django.db import models

from diagnostics.constants import GRADES, VARIANTS
from diagnostics.models.content import (
    AudioClip, ReadingPassage, SpeakingSet, WritingSet,
)

#: (field name, human label) for every component a paper must not share.
SHARED_COMPONENT_FIELDS = [
    ("listening_clip_1", "listening clip"),
    ("listening_clip_2", "listening clip"),
    ("reading_passage", "reading passage"),
    ("writing_set", "writing set"),
    ("speaking_set", "speaking set"),
]


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
    writing_set = models.ForeignKey(
        WritingSet, on_delete=models.PROTECT, related_name="papers"
    )
    speaking_set = models.ForeignKey(
        SpeakingSet, on_delete=models.PROTECT, related_name="papers"
    )

    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ["grade", "variant"]
        constraints = [
            models.UniqueConstraint(fields=["grade", "variant"], name="unique_grade_variant")
        ]

    def __str__(self):
        return f"G{self.grade}-{self.variant}"

    def components(self):
        """Every component this paper occupies, as (label, object) pairs."""
        return [
            (label, getattr(self, field))
            for field, label in SHARED_COMPONENT_FIELDS
            if getattr(self, f"{field}_id", None) is not None
        ]

    def clean(self):
        if self.listening_clip_1_id and self.listening_clip_1_id == self.listening_clip_2_id:
            raise ValidationError(
                {"listening_clip_2": "A paper cannot use the same clip twice."}
            )

        mine = {(label, obj.pk) for label, obj in self.components()}
        siblings = Paper.objects.filter(grade=self.grade).exclude(pk=self.pk)
        for sibling in siblings:
            theirs = {(label, obj.pk) for label, obj in sibling.components()}
            clash = mine & theirs
            if clash:
                label = sorted(clash)[0][0]
                raise ValidationError(
                    f"Grade {self.grade} variant {sibling.variant} already uses this "
                    f"{label}. The four variants in a grade must share nothing."
                )
```

Append to `diagnostics/models/__init__.py`:

```python
from diagnostics.models.paper import Paper, SHARED_COMPONENT_FIELDS

__all__ += ["Paper", "SHARED_COMPONENT_FIELDS"]
```

- [ ] **Step 4: Create the migration**

Run: `.venv\Scripts\python.exe manage.py makemigrations diagnostics`
Expected: `Create model Paper`

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_models_paper -v 2`
Expected: PASS, 6 tests

- [ ] **Step 6: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics`
Expected: OK

---

### Task 6: Tracking models

**Files:**
- Create: `diagnostics/models/tracking.py`
- Modify: `diagnostics/models/__init__.py`
- Test: `diagnostics/tests/test_models_tracking.py`

- [ ] **Step 1: Write the failing test**

Create `diagnostics/tests/test_models_tracking.py`:

```python
from django.contrib.auth import get_user_model
from django.test import TestCase

from diagnostics.models import GenerationWindow, TeacherGradeAssignment


class GenerationWindowTests(TestCase):
    def test_defaults_to_open(self):
        self.assertTrue(GenerationWindow.load().is_open)

    def test_load_is_a_singleton(self):
        first = GenerationWindow.load()
        first.is_open = False
        first.save()
        self.assertFalse(GenerationWindow.load().is_open)
        self.assertEqual(GenerationWindow.objects.count(), 1)


class TeacherGradeAssignmentTests(TestCase):
    def test_a_teacher_is_assigned_a_grade_once(self):
        user = get_user_model().objects.create_user("teacher", password="x")
        TeacherGradeAssignment.objects.create(user=user, grade=9)
        self.assertEqual(
            list(TeacherGradeAssignment.grades_for(user)), [9]
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_models_tracking -v 2`
Expected: FAIL — `ImportError: cannot import name 'GenerationWindow'`

- [ ] **Step 3: Write the implementation**

Create `diagnostics/models/tracking.py`:

```python
"""Who may generate, who did, and whether generation is open (spec 4.2).

`TeacherGradeAssignment` is what makes "who has *not* generated" answerable:
without a declared expected set, absence cannot be distinguished from
irrelevance. At Expert Council merge time this is replaced by a resolver
backed by that system's roster (spec 7).
"""

from django.conf import settings
from django.db import models

from diagnostics.constants import GRADES
from diagnostics.models.paper import Paper


class GenerationWindow(models.Model):
    """Singleton switch letting admins open or close test generation."""

    is_open = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "generation window"

    def __str__(self):
        return "open" if self.is_open else "closed"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        window, _created = cls.objects.get_or_create(pk=1)
        return window


class TeacherGradeAssignment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="diagnostic_grades",
    )
    grade = models.PositiveSmallIntegerField(choices=[(g, f"Grade {g}") for g in GRADES])

    class Meta:
        ordering = ["user__username", "grade"]
        constraints = [
            models.UniqueConstraint(fields=["user", "grade"], name="unique_teacher_grade")
        ]

    def __str__(self):
        return f"{self.user} — Grade {self.grade}"

    @classmethod
    def grades_for(cls, user):
        return cls.objects.filter(user=user).values_list("grade", flat=True)


class GenerationEvent(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="diagnostic_generations",
    )
    paper = models.ForeignKey(Paper, on_delete=models.PROTECT, related_name="generations")
    generated_at = models.DateTimeField(auto_now_add=True)
    export_format = models.CharField(max_length=16, default="zip")

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self):
        return f"{self.user} generated {self.paper} at {self.generated_at:%Y-%m-%d %H:%M}"
```

Append to `diagnostics/models/__init__.py`:

```python
from diagnostics.models.tracking import (
    GenerationEvent, GenerationWindow, TeacherGradeAssignment,
)

__all__ += ["GenerationEvent", "GenerationWindow", "TeacherGradeAssignment"]
```

- [ ] **Step 4: Create the migration and apply everything**

Run: `.venv\Scripts\python.exe manage.py makemigrations diagnostics`
Then: `.venv\Scripts\python.exe manage.py migrate`
Expected: all `diagnostics` migrations applied

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_models_tracking -v 2`
Expected: PASS, 3 tests

- [ ] **Step 6: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics`
Expected: OK

---

### Task 7: Extract images from the .docx in document order

The `.docx` media filenames do **not** match document order — `image6.jpg` is the first image in the document. Sorting by filename silently attaches the wrong options to picture questions.

**Files:**
- Create: `diagnostics/extraction/__init__.py`, `diagnostics/extraction/docx_images.py`
- Test: `diagnostics/tests/test_extraction_images.py`

- [ ] **Step 1: Write the failing test**

Create `diagnostics/tests/test_extraction_images.py`:

```python
from django.conf import settings
from django.test import TestCase

from diagnostics.extraction.docx_images import extract_images_in_document_order

LISTENING_DOCX = settings.DIAGNOSTICS_SOURCE_DIR / "Listening Question Bank -2026 EC.docx"


class ImageExtractionTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not LISTENING_DOCX.exists():
            raise AssertionError(
                f"Source file missing: {LISTENING_DOCX}. Set DIAGNOSTICS_SOURCE_DIR."
            )
        cls.images = extract_images_in_document_order(LISTENING_DOCX)

    def test_extracts_twenty_five_images(self):
        self.assertEqual(len(self.images), 25)

    def test_images_are_jpeg_bytes(self):
        for name, data in self.images:
            self.assertTrue(data.startswith(b"\xff\xd8"), f"{name} is not a JPEG")

    def test_document_order_differs_from_filename_order(self):
        names = [name for name, _ in self.images]
        self.assertEqual(names[0], "media/image6.jpg")
        self.assertNotEqual(names, sorted(names))

    def test_every_image_is_distinct(self):
        self.assertEqual(len({name for name, _ in self.images}), 25)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_extraction_images -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'diagnostics.extraction'`

- [ ] **Step 3: Write the implementation**

Create `diagnostics/extraction/__init__.py` (empty).

Create `diagnostics/extraction/docx_images.py`:

```python
"""Pull images out of a .docx in the order they appear in the document.

A .docx stores images as `word/media/imageN.jpg` parts, but those part names
are assigned arbitrarily by the authoring tool — `image6.jpg` is the first
image in this bank's document. The only reliable ordering is the sequence of
`r:embed` references inside `word/document.xml`, resolved through the
relationships file.
"""

import re
import zipfile

RELATIONSHIP_RE = re.compile(r'Id="(rId\d+)"[^>]*Target="(media/[^"]+)"')
EMBED_RE = re.compile(r'r:embed="(rId\d+)"')


def extract_images_in_document_order(docx_path):
    """Return [(part_name, image_bytes)] in document order."""
    with zipfile.ZipFile(docx_path) as archive:
        rels_xml = archive.read("word/_rels/document.xml.rels").decode("utf-8")
        relationships = dict(RELATIONSHIP_RE.findall(rels_xml))

        document_xml = archive.read("word/document.xml").decode("utf-8")

        images = []
        for rel_id in EMBED_RE.findall(document_xml):
            target = relationships.get(rel_id)
            if target is None:
                continue
            images.append((target, archive.read(f"word/{target}")))
    return images
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_extraction_images -v 2`
Expected: PASS, 4 tests

- [ ] **Step 5: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics`
Expected: OK

---

### Task 8: Parse the worksheet markdown into 20 clips

**Files:**
- Create: `diagnostics/extraction/worksheets.py`
- Test: `diagnostics/tests/test_extraction_worksheets.py`

- [ ] **Step 1: Write the failing test**

Create `diagnostics/tests/test_extraction_worksheets.py`:

```python
from django.conf import settings
from django.test import TestCase

from diagnostics.extraction.worksheets import split_clips, strip_image_data

LISTENING_MD = settings.DIAGNOSTICS_SOURCE_DIR / "Listening Question Bank -2026 EC.md"


class StripImageDataTests(TestCase):
    def test_removes_the_base64_appendix(self):
        text = "body text\n\n[image1]: <data:image/png;base64,AAAA>\n"
        self.assertEqual(strip_image_data(text).strip(), "body text")

    def test_leaves_text_without_an_appendix_alone(self):
        self.assertEqual(strip_image_data("just body"), "just body")


class SplitClipsTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not LISTENING_MD.exists():
            raise AssertionError(f"Source file missing: {LISTENING_MD}")
        cls.clips = split_clips(LISTENING_MD.read_text(encoding="utf-8"))

    def test_finds_twenty_clips(self):
        self.assertEqual(sorted(self.clips), list(range(1, 21)))

    def test_no_clip_body_contains_base64(self):
        for number, body in self.clips.items():
            self.assertNotIn("base64", body, f"clip {number} still holds image data")

    def test_bodies_are_substantial(self):
        for number, body in self.clips.items():
            self.assertGreater(len(body), 100, f"clip {number} body looks truncated")

    def test_intro_is_captured_where_present(self):
        self.assertIn("interview with a teenager called Simon", self.clips[2])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_extraction_worksheets -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'diagnostics.extraction.worksheets'`

- [ ] **Step 3: Write the implementation**

Create `diagnostics/extraction/worksheets.py`:

```python
"""Split the client's listening worksheet markdown into one body per clip.

The file holds 20 worksheets followed by an appendix of base64 image data.
The appendix is discarded — images come from the .docx instead, because the
markdown's copies are lossy re-renders and clip 1's are cropped so badly they
lose the A/B/C option labels.
"""

import re

CLIP_HEADER_RE = re.compile(r"^\**Audio ?[Cc]lip ?(\d+).*$", re.MULTILINE)
IMAGE_DATA_RE = re.compile(r"^\[image\d+\]: <data:", re.MULTILINE)


def strip_image_data(text):
    """Drop the trailing base64 image appendix."""
    match = IMAGE_DATA_RE.search(text)
    return text[: match.start()] if match else text


def split_clips(text):
    """Return {clip_number: body_text} for all clips found in the markdown."""
    body = strip_image_data(text)
    numbers = [int(n) for n in CLIP_HEADER_RE.findall(body)]
    segments = CLIP_HEADER_RE.split(body)

    # re.split with one capturing group yields:
    #   [preamble, num1, body1, num2, body2, ...]
    bodies = segments[2::2]
    return dict(zip(numbers, bodies))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_extraction_worksheets -v 2`
Expected: PASS, 6 tests

- [ ] **Step 5: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics`
Expected: OK

---

### Task 9: Tolerant answer-key parser

The source keys use at least six formatting conventions. A naive parser silently mis-assigns answers, which would make every affected paper mark students wrongly. This task builds the parser; Task 12 adds the mandatory human check on top of it.

**Files:**
- Create: `diagnostics/extraction/keys.py`
- Test: `diagnostics/tests/test_extraction_keys.py`

- [ ] **Step 1: Write the failing test**

Create `diagnostics/tests/test_extraction_keys.py`:

```python
"""Every real formatting quirk found in the source file gets a test."""

from django.test import TestCase

from diagnostics.extraction.keys import parse_gap_fill_key, parse_letter_key


class LetterKeyTests(TestCase):
    def test_colon_before_the_first_number(self):
        # Clip 1: "**Answers :1** C   **2** B ..."
        blob = "**Answers :1** C   **2** B   **3** A   **4** B   **5** C"
        self.assertEqual(parse_letter_key(blob), ["C", "B", "A", "B", "C"])

    def test_key_on_the_line_after_the_marker(self):
        # Clip 2
        blob = "##### **Answers:**\n\n**1 A   2 C   3 B   4 C   5 B**"
        self.assertEqual(parse_letter_key(blob), ["A", "C", "B", "C", "B"])

    def test_missing_space_between_number_and_letter(self):
        # Clip 20: "3A"
        blob = "### **Answers:1 B  2 B  3A  4 B  5 A**"
        self.assertEqual(parse_letter_key(blob), ["B", "B", "A", "B", "A"])

    def test_uses_the_last_answers_marker_only(self):
        blob = "A stray 1 A in the question text.\n**Answers:1 C 2 C 3 C 4 C 5 C**"
        self.assertEqual(parse_letter_key(blob), ["C", "C", "C", "C", "C"])

    def test_raises_when_five_answers_are_not_found(self):
        with self.assertRaises(ValueError):
            parse_letter_key("**Answers:1 A  2 B**")


class GapFillKeyTests(TestCase):
    def test_simple_numbered_key(self):
        # Clip 3
        blob = r"**Answers : 1.rope   2\. 20/twenty  3\. Tall 4\. band  5\. ice(-)cream**"
        self.assertEqual(
            parse_gap_fill_key(blob),
            ["rope", "20/twenty", "Tall", "band", "ice(-)cream"],
        )

    def test_missing_separator_between_answers(self):
        # Clip 7: "...six/6 months3.(a) receptionist..."
        blob = (r"**Answers: 1.(a) family 2\. six/6 months3.(a) receptionist"
                r"4.(a) bakery / baker's 5\. four**")
        parsed = parse_gap_fill_key(blob)
        self.assertEqual(len(parsed), 5)
        self.assertEqual(parsed[0], "(a) family")
        self.assertEqual(parsed[2], "(a) receptionist")

    def test_answer_that_itself_contains_a_digit(self):
        # Clip 19: answer 4 is "5 / five", which must not be read as marker 5.
        blob = "**Answers:1 hills  2 sunset   3 cushion 4 5 / five   5 CITYENTS**"
        self.assertEqual(
            parse_gap_fill_key(blob),
            ["hills", "sunset", "cushion", "5 / five", "CITYENTS"],
        )

    def test_raises_when_an_answer_is_empty(self):
        with self.assertRaises(ValueError):
            parse_gap_fill_key("**Answers:1 a 2 b 3 4 d 5 e**")


class AlternativesTests(TestCase):
    def test_slash_separated_alternatives_are_split(self):
        from diagnostics.extraction.keys import split_alternatives

        self.assertEqual(split_alternatives("20/twenty"), ["20", "twenty"])
        self.assertEqual(
            split_alternatives("(a) bakery / baker's"), ["(a) bakery", "baker's"]
        )
        self.assertEqual(split_alternatives("hills"), ["hills"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_extraction_keys -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'diagnostics.extraction.keys'`

- [ ] **Step 3: Write the implementation**

Create `diagnostics/extraction/keys.py`:

```python
"""Parse answer keys out of the client's worksheet text.

The source uses at least six conventions, all of them present in the tests:
a colon glued to the first number, the key on the following line, a missing
space between number and letter, a missing separator between two answers,
markdown escapes, and — worst — a gap-fill answer that is itself a digit
("4 5 / five"), which a left-to-right scan would mistake for the next marker.

Nothing here is trusted blindly: `verify_listening_keys` (Task 12) forces a
human to sign off all 100 answers before they can be used.
"""

import re

ANSWERS_MARKER_RE = re.compile(r"Answers?\s*:?", re.IGNORECASE)
LETTER_PAIR_RE = re.compile(r"([1-5])\s*\.?\s*([ABC])\b")
EXPECTED = 5


def _normalise(blob):
    """Strip markdown noise so the numbering is visible."""
    cleaned = blob.replace("\\", "").replace("*", "").replace("#", "")
    return re.sub(r"\s+", " ", cleaned)


def _after_last_marker(blob):
    """Everything after the final 'Answers' marker.

    Using the *last* marker avoids picking up option letters that appear in
    the question text above the key.
    """
    text = _normalise(blob)
    matches = list(ANSWERS_MARKER_RE.finditer(text))
    if not matches:
        raise ValueError("No 'Answers' marker found.")
    return text[matches[-1].end():]


def parse_letter_key(blob):
    """Parse an A/B/C key into five letters. For picture, mcq3 and true_false."""
    tail = _after_last_marker(blob)
    pairs = LETTER_PAIR_RE.findall(tail)

    answers = {}
    for number, letter in pairs:
        answers.setdefault(int(number), letter)

    if sorted(answers) != [1, 2, 3, 4, 5]:
        raise ValueError(f"Expected 5 lettered answers, found {sorted(answers)}: {tail!r}")
    return [answers[n] for n in range(1, EXPECTED + 1)]


def parse_gap_fill_key(blob):
    """Parse a numbered gap-fill key into five answer strings.

    Markers are located left to right, except the final one, which is taken
    from the *last* plausible position so that an answer containing a digit
    (clip 19's "4 5 / five") is not truncated.
    """
    tail = _after_last_marker(blob)

    starts = []
    cursor = 0
    for number in range(1, EXPECTED + 1):
        pattern = re.compile(rf"(?<!\d){number}\s*[.):]?\s*")
        if number < EXPECTED:
            match = pattern.search(tail, cursor)
        else:
            candidates = [m for m in pattern.finditer(tail, cursor)]
            match = candidates[-1] if candidates else None
        if match is None:
            raise ValueError(f"Could not locate marker {number} in {tail!r}")
        starts.append((match.start(), match.end()))
        cursor = match.end()

    answers = []
    for index, (_start, end) in enumerate(starts):
        stop = starts[index + 1][0] if index + 1 < len(starts) else len(tail)
        answers.append(tail[end:stop].strip(" .:,"))

    if any(not answer for answer in answers):
        raise ValueError(f"Empty answer parsed from {tail!r}: {answers}")
    return answers


def split_alternatives(answer):
    """Split 'a / b' or 'a/b' into acceptable alternatives."""
    parts = [part.strip() for part in answer.split("/")]
    return [part for part in parts if part]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_extraction_keys -v 2`
Expected: PASS, 10 tests

- [ ] **Step 5: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics`
Expected: OK

---

### Task 10: Map MP3 filenames to clip numbers

The audio folder mixes `Audio 1.mp3`, `Audio4.mp3` and `Audio10.mp3`.

**Files:**
- Create: `diagnostics/extraction/audio.py`
- Test: `diagnostics/tests/test_extraction_audio.py`

- [ ] **Step 1: Write the failing test**

Create `diagnostics/tests/test_extraction_audio.py`:

```python
from django.conf import settings
from django.test import TestCase

from diagnostics.extraction.audio import clip_number_from_filename, map_audio_files

AUDIO_DIR = settings.DIAGNOSTICS_SOURCE_DIR / "Listening Diagnostic Audio files"


class FilenameTests(TestCase):
    def test_handles_every_naming_style_in_the_folder(self):
        self.assertEqual(clip_number_from_filename("Audio 1.mp3"), 1)
        self.assertEqual(clip_number_from_filename("Audio4.mp3"), 4)
        self.assertEqual(clip_number_from_filename("Audio10.mp3"), 10)
        self.assertEqual(clip_number_from_filename("Audio 20.mp3"), 20)

    def test_returns_none_for_unrelated_files(self):
        self.assertIsNone(clip_number_from_filename("notes.txt"))


class MappingTests(TestCase):
    def test_maps_all_twenty_clips(self):
        if not AUDIO_DIR.exists():
            self.skipTest(f"Audio folder not present: {AUDIO_DIR}")
        mapping = map_audio_files(AUDIO_DIR)
        self.assertEqual(sorted(mapping), list(range(1, 21)))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_extraction_audio -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'diagnostics.extraction.audio'`

- [ ] **Step 3: Write the implementation**

Create `diagnostics/extraction/audio.py`:

```python
"""Resolve the client's inconsistently named MP3s to clip numbers.

The folder contains 'Audio 1.mp3', 'Audio4.mp3' and 'Audio10.mp3' — the space
is present for some numbers and absent for others.
"""

import re

AUDIO_FILENAME_RE = re.compile(r"^Audio\s*(\d+)\.mp3$", re.IGNORECASE)


def clip_number_from_filename(filename):
    """Return the clip number for an MP3 filename, or None if unrelated."""
    match = AUDIO_FILENAME_RE.match(filename)
    return int(match.group(1)) if match else None


def map_audio_files(audio_dir):
    """Return {clip_number: Path} for every MP3 in the folder."""
    mapping = {}
    for path in sorted(audio_dir.iterdir()):
        number = clip_number_from_filename(path.name)
        if number is None:
            continue
        if number in mapping:
            raise ValueError(f"Two files claim clip {number}: {mapping[number]}, {path}")
        mapping[number] = path
    return mapping
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_extraction_audio -v 2`
Expected: PASS, 3 tests

- [ ] **Step 5: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics`
Expected: OK

---

### Task 11: `import_listening` management command

**Files:**
- Create: `diagnostics/management/__init__.py`, `diagnostics/management/commands/__init__.py`, `diagnostics/management/commands/import_listening.py`
- Test: `diagnostics/tests/test_import_listening.py`

- [ ] **Step 1: Write the failing test**

Create `diagnostics/tests/test_import_listening.py`:

```python
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from diagnostics.constants import CLIP_TASK_TYPES
from diagnostics.models import AudioClip, ListeningQuestion

SOURCE = settings.DIAGNOSTICS_SOURCE_DIR


class ImportListeningTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not (SOURCE / "Listening Question Bank -2026 EC.md").exists():
            raise AssertionError(f"Source material missing under {SOURCE}")

    def test_imports_twenty_clips_and_one_hundred_questions(self):
        call_command("import_listening", stdout=StringIO())
        self.assertEqual(AudioClip.objects.count(), 20)
        self.assertEqual(ListeningQuestion.objects.count(), 100)

    def test_task_types_match_the_verified_constants(self):
        call_command("import_listening", stdout=StringIO())
        for clip in AudioClip.objects.all():
            self.assertEqual(clip.task_type, CLIP_TASK_TYPES[clip.number])

    def test_letter_clips_have_letter_answers(self):
        call_command("import_listening", stdout=StringIO())
        for clip in AudioClip.objects.filter(number__in=[1, 2, 4]):
            for question in clip.questions.all():
                self.assertIn(question.answer, {"A", "B", "C"})

    def test_picture_clips_have_images_attached(self):
        call_command("import_listening", stdout=StringIO())
        for number in (1, 5, 9, 13, 15):
            clip = AudioClip.objects.get(number=number)
            for question in clip.questions.all():
                self.assertTrue(question.image, f"clip {number} Q{question.position}")

    def test_running_twice_is_idempotent(self):
        call_command("import_listening", stdout=StringIO())
        call_command("import_listening", stdout=StringIO())
        self.assertEqual(AudioClip.objects.count(), 20)
        self.assertEqual(ListeningQuestion.objects.count(), 100)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_import_listening -v 2`
Expected: FAIL — `CommandError: Unknown command: 'import_listening'`

- [ ] **Step 3: Write the implementation**

Create `diagnostics/management/__init__.py` and `diagnostics/management/commands/__init__.py` (both empty).

Create `diagnostics/management/commands/import_listening.py`:

```python
"""Import the client's 20 listening clips into the database.

Sources, all read-only, all under settings.DIAGNOSTICS_SOURCE_DIR:
  - the .md   -> worksheet text and answer keys
  - the .docx -> the 25 picture-option images, in document order
  - the audio folder -> 20 MP3s

Idempotent: re-running replaces clip content in place.
"""

from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from diagnostics.constants import (
    CLIP_TASK_TYPES, IMAGE_SLOTS, LETTER_ANSWER_TYPES, TaskType,
)
from diagnostics.extraction.audio import map_audio_files
from diagnostics.extraction.docx_images import extract_images_in_document_order
from diagnostics.extraction.keys import (
    parse_gap_fill_key, parse_letter_key, split_alternatives,
)
from diagnostics.extraction.worksheets import split_clips
from diagnostics.models import AudioClip, ListeningQuestion

MD_NAME = "Listening Question Bank -2026 EC.md"
DOCX_NAME = "Listening Question Bank -2026 EC.docx"
AUDIO_DIR_NAME = "Listening Diagnostic Audio files"


class Command(BaseCommand):
    help = "Import the 20 diagnostic listening clips, questions, keys and images."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source", default=None,
            help="Override settings.DIAGNOSTICS_SOURCE_DIR.",
        )

    def handle(self, *args, **options):
        source = options["source"]
        source_dir = (
            settings.DIAGNOSTICS_SOURCE_DIR if source is None else Path(source)
        )

        markdown_path = source_dir / MD_NAME
        docx_path = source_dir / DOCX_NAME
        audio_dir = source_dir / AUDIO_DIR_NAME

        for path in (markdown_path, docx_path):
            if not path.exists():
                raise CommandError(f"Missing source file: {path}")

        bodies = split_clips(markdown_path.read_text(encoding="utf-8"))
        if sorted(bodies) != list(range(1, 21)):
            raise CommandError(f"Expected clips 1-20, parsed {sorted(bodies)}")

        images = extract_images_in_document_order(docx_path)
        if len(images) != len(IMAGE_SLOTS):
            raise CommandError(
                f"Expected {len(IMAGE_SLOTS)} images, found {len(images)}"
            )
        images_by_slot = dict(zip(IMAGE_SLOTS, images))

        audio = map_audio_files(audio_dir) if audio_dir.exists() else {}
        if not audio:
            self.stdout.write(self.style.WARNING(f"No audio found under {audio_dir}"))

        with transaction.atomic():
            for number in range(1, 21):
                self._import_clip(
                    number, bodies[number], images_by_slot, audio.get(number)
                )

        self.stdout.write(self.style.SUCCESS(
            f"Imported {AudioClip.objects.count()} clips, "
            f"{ListeningQuestion.objects.count()} questions."
        ))

    def _import_clip(self, number, body, images_by_slot, audio_path):
        task_type = CLIP_TASK_TYPES[number]

        clip, _created = AudioClip.objects.update_or_create(
            number=number,
            defaults={"task_type": task_type, "intro_text": self._intro(body)},
        )

        if audio_path is not None and not clip.audio_file:
            clip.audio_file.save(
                f"clip-{number:02d}.mp3",
                ContentFile(audio_path.read_bytes()),
                save=True,
            )

        if task_type in LETTER_ANSWER_TYPES:
            answers = parse_letter_key(body)
            alternatives = [[] for _ in answers]
        else:
            answers = parse_gap_fill_key(body)
            alternatives = [split_alternatives(a) for a in answers]

        clip.questions.all().delete()
        for position, (answer, alts) in enumerate(zip(answers, alternatives), start=1):
            question = ListeningQuestion.objects.create(
                clip=clip,
                position=position,
                stem=f"Clip {number}, question {position}",
                answer=answer,
                acceptable_answers=alts,
            )
            slot = images_by_slot.get((number, position))
            if slot is not None:
                part_name, data = slot
                suffix = part_name.rsplit(".", 1)[-1]
                question.image.save(
                    f"clip-{number:02d}-q{position}.{suffix}",
                    ContentFile(data),
                    save=True,
                )

    @staticmethod
    def _intro(body):
        for line in body.splitlines():
            stripped = line.strip().lstrip("*# ").strip()
            if stripped.startswith("You will hear"):
                return stripped.rstrip("*").strip()
        return ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_import_listening -v 2`
Expected: PASS, 5 tests

- [ ] **Step 5: Import into the real database**

Run: `.venv\Scripts\python.exe manage.py import_listening`
Expected: `Imported 20 clips, 100 questions.`

- [ ] **Step 6: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics`
Expected: OK

---

### Task 12: Mandatory human verification of all 100 listening answers

The parser is tolerant, not infallible, and there are no transcripts — a teacher cannot catch a wrong key by reading. This command forces a person to look at all 100 answers and record that they did.

**Files:**
- Create: `diagnostics/management/commands/verify_listening_keys.py`
- Modify: `diagnostics/models/content.py`, `diagnostics/models/__init__.py`
- Test: `diagnostics/tests/test_verify_keys.py`

- [ ] **Step 1: Write the failing test**

Create `diagnostics/tests/test_verify_keys.py`:

```python
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diagnostics.constants import TaskType
from diagnostics.models import AudioClip, KeyVerification, ListeningQuestion


class VerifyListeningKeysTests(TestCase):
    def setUp(self):
        clip = AudioClip.objects.create(number=1, task_type=TaskType.PICTURE)
        for position in range(1, 6):
            ListeningQuestion.objects.create(
                clip=clip, position=position, stem="s", answer="A"
            )

    def test_report_lists_every_question(self):
        out = StringIO()
        call_command("verify_listening_keys", stdout=out)
        report = out.getvalue()
        for position in range(1, 6):
            self.assertIn(f"Clip  1 Q{position}", report)

    def test_report_alone_does_not_sign_off(self):
        call_command("verify_listening_keys", stdout=StringIO())
        self.assertFalse(KeyVerification.is_signed_off())

    def test_sign_off_records_who_and_when(self):
        call_command("verify_listening_keys", "--sign-off", "Munish", stdout=StringIO())
        self.assertTrue(KeyVerification.is_signed_off())
        self.assertEqual(KeyVerification.load().verified_by, "Munish")

    def test_sign_off_is_invalidated_when_an_answer_changes(self):
        call_command("verify_listening_keys", "--sign-off", "Munish", stdout=StringIO())
        question = ListeningQuestion.objects.first()
        question.answer = "C"
        question.save()
        self.assertFalse(KeyVerification.is_signed_off())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_verify_keys -v 2`
Expected: FAIL — `ImportError: cannot import name 'KeyVerification'`

- [ ] **Step 3: Add the model**

Add `import hashlib` to the top of `diagnostics/models/content.py`, then append:

```python
class KeyVerification(models.Model):
    """Records that a human checked all 100 listening answers (spec 9).

    The fingerprint is a hash of every answer. If any answer changes after
    sign-off, the fingerprint stops matching and the sign-off lapses — so a
    re-import silently invalidates stale approval instead of inheriting it.
    """

    verified_by = models.CharField(max_length=120)
    verified_at = models.DateTimeField(auto_now=True)
    fingerprint = models.CharField(max_length=64)

    class Meta:
        verbose_name = "listening key verification"

    def __str__(self):
        return f"verified by {self.verified_by} at {self.verified_at:%Y-%m-%d}"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @staticmethod
    def current_fingerprint():
        rows = ListeningQuestion.objects.order_by(
            "clip__number", "position"
        ).values_list("clip__number", "position", "answer")
        digest = hashlib.sha256()
        for clip_number, position, answer in rows:
            digest.update(f"{clip_number}:{position}:{answer}\n".encode("utf-8"))
        return digest.hexdigest()

    @classmethod
    def load(cls):
        return cls.objects.filter(pk=1).first()

    @classmethod
    def is_signed_off(cls):
        record = cls.load()
        return bool(record) and record.fingerprint == cls.current_fingerprint()
```

Add `KeyVerification` to the import list and `__all__` in `diagnostics/models/__init__.py`.

- [ ] **Step 4: Write the command**

Create `diagnostics/management/commands/verify_listening_keys.py`:

```python
"""Print every listening answer for human checking, and record sign-off."""

from django.core.management.base import BaseCommand, CommandError

from diagnostics.constants import TaskType
from diagnostics.models import KeyVerification, ListeningQuestion


class Command(BaseCommand):
    help = "Show all listening answers for verification; --sign-off records approval."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sign-off", metavar="NAME", default=None,
            help="Record that NAME has checked every answer above.",
        )

    def handle(self, *args, **options):
        questions = ListeningQuestion.objects.select_related("clip").order_by(
            "clip__number", "position"
        )
        if not questions:
            raise CommandError("No listening questions imported yet.")

        current_clip = None
        for question in questions:
            if question.clip_id != current_clip:
                current_clip = question.clip_id
                label = TaskType(question.clip.task_type).label
                self.stdout.write("")
                self.stdout.write(self.style.MIGRATE_HEADING(
                    f"Clip {question.clip.number:>2} — {label}"
                ))
            alternatives = (
                f"   (also accept: {', '.join(question.acceptable_answers)})"
                if len(question.acceptable_answers) > 1 else ""
            )
            self.stdout.write(
                f"  Clip {question.clip.number:>2} Q{question.position}  "
                f"{question.answer}{alternatives}"
            )

        self.stdout.write("")
        self.stdout.write(f"Total: {questions.count()} answers.")

        name = options["sign_off"]
        if name:
            KeyVerification.objects.update_or_create(
                pk=1,
                defaults={
                    "verified_by": name,
                    "fingerprint": KeyVerification.current_fingerprint(),
                },
            )
            self.stdout.write(self.style.SUCCESS(f"Signed off by {name}."))
        elif KeyVerification.is_signed_off():
            record = KeyVerification.load()
            self.stdout.write(self.style.SUCCESS(
                f"Already signed off by {record.verified_by}."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "NOT signed off. Check every answer above against its audio, "
                "then re-run with --sign-off \"Your Name\"."
            ))
```

- [ ] **Step 5: Create the migration and run the tests**

Run: `.venv\Scripts\python.exe manage.py makemigrations diagnostics`
Then: `.venv\Scripts\python.exe manage.py migrate`
Then: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_verify_keys -v 2`
Expected: PASS, 4 tests

- [ ] **Step 6: Human checkpoint — this one is not automatable**

Run: `.venv\Scripts\python.exe manage.py verify_listening_keys`

Play each clip from `D:\Diagnostics Gate\Listening Diagnostic Audio files` and confirm every printed answer. **Do not sign off on behalf of the user** — report the printed table and ask them to verify, then run the sign-off command with their name.

---

### Task 13: Authored content schema and validators

Content for reading, writing and speaking is authored as JSON and validated before import. These validators are the tests for Task 15's content.

**Files:**
- Create: `diagnostics/authored/__init__.py`, `diagnostics/authored/schema.py`
- Test: `diagnostics/tests/test_authored_schema.py`

- [ ] **Step 1: Write the failing test**

Create `diagnostics/tests/test_authored_schema.py`:

```python
from django.test import TestCase

from diagnostics.authored.schema import (
    ContentError, validate_reading, validate_speaking, validate_writing,
)


def reading_payload(**overrides):
    payload = {
        "label": "R01",
        "title": "The School Garden",
        "body": " ".join(["word"] * 165),
        "questions": (
            [{"position": n, "subtype": "true_false_ng", "stem": f"s{n}",
              "options": ["TRUE", "FALSE", "NOT GIVEN"], "answer": "TRUE"}
             for n in range(1, 6)]
            + [{"position": n, "subtype": "mcq", "stem": f"s{n}",
                "options": ["a", "b", "c", "d"], "answer": "B"}
               for n in range(6, 9)]
            + [{"position": n, "subtype": "completion", "stem": f"s{n}",
                "options": [], "answer": "height"}
               for n in range(9, 11)]
        ),
    }
    payload.update(overrides)
    return payload


def writing_payload(**overrides):
    subtypes = ["grammar"] * 3 + ["vocabulary"] * 2 + ["jumbled"] * 3 + ["fill_blank"] * 2
    payload = {
        "label": "W01",
        "questions": [
            {"position": n, "subtype": subtype, "stem": f"s{n}",
             "options": ["a", "b", "c", "d"], "answer": "A"}
            for n, subtype in enumerate(subtypes, start=1)
        ],
    }
    payload.update(overrides)
    return payload


def speaking_payload(**overrides):
    tasks = ["introduction", "experience", "description", "role_play", "opinion"]
    payload = {
        "label": "S01",
        "prompts": [
            {"position": n, "task": task, "prompt": f"p{n}", "bullets": []}
            for n, task in enumerate(tasks, start=1)
        ],
    }
    payload.update(overrides)
    return payload


class ReadingValidationTests(TestCase):
    def test_valid_payload_passes(self):
        validate_reading(reading_payload())

    def test_short_passage_is_rejected(self):
        with self.assertRaisesMessage(ContentError, "150-180 words"):
            validate_reading(reading_payload(body="too short"))

    def test_wrong_question_count_is_rejected(self):
        payload = reading_payload()
        payload["questions"] = payload["questions"][:9]
        with self.assertRaisesMessage(ContentError, "exactly 10"):
            validate_reading(payload)

    def test_wrong_subtype_distribution_is_rejected(self):
        payload = reading_payload()
        payload["questions"][0]["subtype"] = "mcq"
        with self.assertRaisesMessage(ContentError, "true_false_ng"):
            validate_reading(payload)

    def test_mcq_answer_must_be_a_listed_option_letter(self):
        payload = reading_payload()
        payload["questions"][5]["answer"] = "E"
        with self.assertRaisesMessage(ContentError, "option letter"):
            validate_reading(payload)

    def test_completion_answer_is_at_most_two_words(self):
        payload = reading_payload()
        payload["questions"][8]["answer"] = "far too many words"
        with self.assertRaisesMessage(ContentError, "two words"):
            validate_reading(payload)


class WritingValidationTests(TestCase):
    def test_valid_payload_passes(self):
        validate_writing(writing_payload())

    def test_subtype_counts_must_match_the_pattern(self):
        payload = writing_payload()
        payload["questions"][0]["subtype"] = "vocabulary"
        with self.assertRaisesMessage(ContentError, "grammar"):
            validate_writing(payload)

    def test_every_question_needs_four_options(self):
        payload = writing_payload()
        payload["questions"][0]["options"] = ["a", "b"]
        with self.assertRaisesMessage(ContentError, "four options"):
            validate_writing(payload)


class SpeakingValidationTests(TestCase):
    def test_valid_payload_passes(self):
        validate_speaking(speaking_payload())

    def test_all_five_tasks_must_be_present_in_order(self):
        payload = speaking_payload()
        payload["prompts"][2]["task"] = "opinion"
        with self.assertRaisesMessage(ContentError, "five fixed tasks"):
            validate_speaking(payload)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_authored_schema -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'diagnostics.authored'`

- [ ] **Step 3: Write the implementation**

Create `diagnostics/authored/__init__.py` (empty).

Create `diagnostics/authored/schema.py`:

```python
"""Validation for authored reading, writing and speaking content (spec 3.3).

Authored content is the bulk of the diagnostic and the part no parser can
check for us, so the shape is enforced mechanically: word counts, question
counts, subtype distribution, and answer well-formedness. Quality remains a
human review gate; these rules only stop malformed content reaching the bank.
"""

from collections import Counter

from diagnostics.constants import (
    MAX_PASSAGE_WORDS, MIN_PASSAGE_WORDS, OPTION_LETTERS,
    READING_SUBTYPE_COUNTS, SPEAKING_TASK_ORDER, WRITING_SUBTYPE_COUNTS,
)

TRUE_FALSE_ANSWERS = {"TRUE", "FALSE", "NOT GIVEN"}


class ContentError(ValueError):
    """Authored content does not match the required pattern."""


def _require_positions(items, expected, label, key="position"):
    positions = [item[key] for item in items]
    if positions != list(range(1, expected + 1)):
        raise ContentError(
            f"{label}: expected exactly {expected} items numbered 1-{expected}, "
            f"got positions {positions}."
        )


def _require_subtype_counts(items, expected, label):
    counts = Counter(item["subtype"] for item in items)
    for subtype, wanted in expected.items():
        if counts.get(subtype, 0) != wanted:
            raise ContentError(
                f"{label}: expected {wanted} '{subtype}' questions, "
                f"got {counts.get(subtype, 0)}."
            )


def validate_reading(payload):
    label = payload.get("label", "<unlabelled>")
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
        position, subtype, answer = (
            question["position"], question["subtype"], question["answer"],
        )
        if subtype == "true_false_ng":
            if answer not in TRUE_FALSE_ANSWERS:
                raise ContentError(
                    f"{label} Q{position}: answer must be one of {sorted(TRUE_FALSE_ANSWERS)}."
                )
        elif subtype == "mcq":
            if len(question["options"]) != 4:
                raise ContentError(f"{label} Q{position}: mcq needs four options.")
            if answer not in OPTION_LETTERS:
                raise ContentError(
                    f"{label} Q{position}: answer must be an option letter A-D."
                )
        elif subtype == "completion":
            if len(answer.split()) > 2:
                raise ContentError(
                    f"{label} Q{position}: completion answers are at most two words."
                )
    return payload


def validate_writing(payload):
    label = payload.get("label", "<unlabelled>")
    questions = payload["questions"]
    _require_positions(questions, 10, label)
    _require_subtype_counts(questions, WRITING_SUBTYPE_COUNTS, label)

    for question in questions:
        position = question["position"]
        if len(question["options"]) != 4:
            raise ContentError(f"{label} Q{position}: every question needs four options.")
        if question["answer"] not in OPTION_LETTERS:
            raise ContentError(
                f"{label} Q{position}: answer must be an option letter A-D."
            )
    return payload


def validate_speaking(payload):
    label = payload.get("label", "<unlabelled>")
    prompts = payload["prompts"]
    _require_positions(prompts, 5, label)

    tasks = [prompt["task"] for prompt in prompts]
    if tasks != SPEAKING_TASK_ORDER:
        raise ContentError(
            f"{label}: prompts must be the five fixed tasks in order "
            f"{SPEAKING_TASK_ORDER}; got {tasks}."
        )
    for prompt in prompts:
        if not prompt["prompt"].strip():
            raise ContentError(f"{label} Q{prompt['position']}: prompt is empty.")
    return payload
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_authored_schema -v 2`
Expected: PASS, 12 tests

- [ ] **Step 5: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics`
Expected: OK

---

### Task 14: `import_authored` management command

**Files:**
- Create: `diagnostics/management/commands/import_authored.py`
- Test: `diagnostics/tests/test_import_authored.py`

- [ ] **Step 1: Write the failing test**

Create `diagnostics/tests/test_import_authored.py`:

```python
import json
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from diagnostics.models import ReadingPassage, SpeakingSet, WritingSet
from diagnostics.tests.test_authored_schema import (
    reading_payload, speaking_payload, writing_payload,
)


class ImportAuthoredTests(TestCase):
    def _write(self, tmp_path, name, payload):
        path = tmp_path / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def setUp(self):
        import tempfile
        from pathlib import Path

        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "reading").mkdir()
        (self.tmp / "writing").mkdir()
        (self.tmp / "speaking").mkdir()

    def test_imports_a_valid_reading_set(self):
        self._write(self.tmp / "reading", "R01.json", reading_payload())
        call_command("import_authored", "--dir", str(self.tmp), stdout=StringIO())
        passage = ReadingPassage.objects.get(label="R01")
        self.assertEqual(passage.questions.count(), 10)
        self.assertEqual(passage.word_count, 165)

    def test_imports_writing_and_speaking(self):
        self._write(self.tmp / "writing", "W01.json", writing_payload())
        self._write(self.tmp / "speaking", "S01.json", speaking_payload())
        call_command("import_authored", "--dir", str(self.tmp), stdout=StringIO())
        self.assertEqual(WritingSet.objects.get(label="W01").questions.count(), 10)
        self.assertEqual(SpeakingSet.objects.get(label="S01").prompts.count(), 5)

    def test_invalid_content_aborts_the_whole_import(self):
        self._write(self.tmp / "reading", "R01.json", reading_payload())
        self._write(
            self.tmp / "reading", "R02.json", reading_payload(label="R02", body="short")
        )
        with self.assertRaises(CommandError):
            call_command("import_authored", "--dir", str(self.tmp), stdout=StringIO())
        self.assertEqual(ReadingPassage.objects.count(), 0)

    def test_reimport_replaces_questions_without_duplicating(self):
        self._write(self.tmp / "reading", "R01.json", reading_payload())
        call_command("import_authored", "--dir", str(self.tmp), stdout=StringIO())
        call_command("import_authored", "--dir", str(self.tmp), stdout=StringIO())
        self.assertEqual(ReadingPassage.objects.count(), 1)
        self.assertEqual(ReadingPassage.objects.get(label="R01").questions.count(), 10)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_import_authored -v 2`
Expected: FAIL — `CommandError: Unknown command: 'import_authored'`

- [ ] **Step 3: Write the implementation**

Create `diagnostics/management/commands/import_authored.py`:

```python
"""Import authored reading, writing and speaking JSON into the bank.

Every file is validated before anything is written, and the whole import runs
in one transaction — a single malformed set aborts the run rather than leaving
the bank half-populated.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from diagnostics.authored.schema import (
    ContentError, validate_reading, validate_speaking, validate_writing,
)
from diagnostics.models import (
    ReadingPassage, ReadingQuestion, SpeakingPrompt, SpeakingSet,
    WritingQuestion, WritingSet,
)

DEFAULT_DIR = Path("diagnostics/authored/content")


class Command(BaseCommand):
    help = "Import authored reading/writing/speaking JSON sets."

    def add_arguments(self, parser):
        parser.add_argument("--dir", default=str(DEFAULT_DIR))

    def handle(self, *args, **options):
        root = Path(options["dir"])
        if not root.exists():
            raise CommandError(f"Content directory not found: {root}")

        payloads = {
            "reading": self._load(root / "reading", validate_reading),
            "writing": self._load(root / "writing", validate_writing),
            "speaking": self._load(root / "speaking", validate_speaking),
        }

        with transaction.atomic():
            for payload in payloads["reading"]:
                self._save_reading(payload)
            for payload in payloads["writing"]:
                self._save_writing(payload)
            for payload in payloads["speaking"]:
                self._save_speaking(payload)

        self.stdout.write(self.style.SUCCESS(
            f"Imported {len(payloads['reading'])} reading, "
            f"{len(payloads['writing'])} writing, "
            f"{len(payloads['speaking'])} speaking sets."
        ))

    def _load(self, directory, validator):
        if not directory.exists():
            return []
        payloads = []
        for path in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                raise CommandError(f"{path}: invalid JSON — {error}") from error
            try:
                validator(payload)
            except (ContentError, KeyError) as error:
                raise CommandError(f"{path}: {error}") from error
            payloads.append(payload)
        return payloads

    def _save_reading(self, payload):
        passage, _ = ReadingPassage.objects.update_or_create(
            label=payload["label"],
            defaults={"title": payload["title"], "body": payload["body"]},
        )
        passage.questions.all().delete()
        for question in payload["questions"]:
            ReadingQuestion.objects.create(
                passage=passage,
                position=question["position"],
                subtype=question["subtype"],
                stem=question["stem"],
                options=question.get("options", []),
                answer=question["answer"],
                acceptable_answers=question.get("acceptable_answers", []),
            )

    def _save_writing(self, payload):
        writing_set, _ = WritingSet.objects.update_or_create(label=payload["label"])
        writing_set.questions.all().delete()
        for question in payload["questions"]:
            WritingQuestion.objects.create(
                set=writing_set,
                position=question["position"],
                subtype=question["subtype"],
                stem=question["stem"],
                options=question["options"],
                answer=question["answer"],
            )

    def _save_speaking(self, payload):
        speaking_set, _ = SpeakingSet.objects.update_or_create(label=payload["label"])
        speaking_set.prompts.all().delete()
        for prompt in payload["prompts"]:
            SpeakingPrompt.objects.create(
                set=speaking_set,
                position=prompt["position"],
                task=prompt["task"],
                prompt=prompt["prompt"],
                bullets=prompt.get("bullets", []),
                marks=prompt.get("marks", 2),
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_import_authored -v 2`
Expected: PASS, 4 tests

- [ ] **Step 5: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics`
Expected: OK

---

### Task 15: Author the 33 content sets

This is the long pole of the whole project — 11 reading passages, 11 writing sets, 11 speaking sets, plus the three transcribed from `Diagnostic_Test_Version_1.docx`. It is content work gated on the user's judgement, not code; the validators from Task 13 are its automated check, and the user is its quality gate.

**Files:**
- Create: `diagnostics/authored/content/reading/R01.json` … `R12.json`
- Create: `diagnostics/authored/content/writing/W01.json` … `W12.json`
- Create: `diagnostics/authored/content/speaking/S01.json` … `S12.json`
- Test: `diagnostics/tests/test_content_completeness.py`

- [ ] **Step 1: Write the failing test**

Create `diagnostics/tests/test_content_completeness.py`:

```python
"""The bank is only complete when all 12 sets of each kind validate."""

import json
from pathlib import Path

from django.test import TestCase

from diagnostics.authored.schema import (
    validate_reading, validate_speaking, validate_writing,
)

CONTENT = Path("diagnostics/authored/content")
KINDS = [
    ("reading", "R", validate_reading),
    ("writing", "W", validate_writing),
    ("speaking", "S", validate_speaking),
]


class ContentCompletenessTests(TestCase):
    def test_twelve_sets_of_each_kind_exist_and_validate(self):
        for folder, prefix, validator in KINDS:
            with self.subTest(kind=folder):
                paths = sorted((CONTENT / folder).glob("*.json"))
                labels = [path.stem for path in paths]
                self.assertEqual(
                    labels, [f"{prefix}{n:02d}" for n in range(1, 13)],
                    f"{folder}: expected {prefix}01..{prefix}12",
                )
                for path in paths:
                    validator(json.loads(path.read_text(encoding="utf-8")))

    def test_reading_passages_are_all_distinct(self):
        bodies = [
            json.loads(path.read_text(encoding="utf-8"))["body"]
            for path in sorted((CONTENT / "reading").glob("*.json"))
        ]
        self.assertEqual(len(bodies), len(set(bodies)), "duplicate reading passage")

    def test_writing_stems_are_all_distinct(self):
        stems = []
        for path in sorted((CONTENT / "writing").glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            stems.extend(question["stem"] for question in payload["questions"])
        self.assertEqual(len(stems), len(set(stems)), "duplicate writing question")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_content_completeness -v 2`
Expected: FAIL — the content directories are empty

- [ ] **Step 3: Transcribe Version 1 into R01, W01, S01**

Read `D:\Diagnostics Gate\Diagnostic_Test_Version_1.docx` and transcribe its three sections into the JSON shapes validated by Task 13:

- `reading/R01.json` — the "The School Garden" passage, its 5 TRUE/FALSE/NOT GIVEN questions, 3 MCQs, and 2 completion items.
- `writing/W01.json` — the 3 grammar, 2 vocabulary, 3 jumbled and 2 fill-blank questions.
- `speaking/S01.json` — the 5 prompts with their bullet lists.

The exact shape for each kind — every later set copies these structures:

```json
{
  "label": "R01",
  "title": "The School Garden",
  "body": "Many schools around the world are creating small gardens ... (150-180 words)",
  "questions": [
    {"position": 1, "subtype": "true_false_ng",
     "stem": "School gardens must be very large to be useful.",
     "options": ["TRUE", "FALSE", "NOT GIVEN"], "answer": "FALSE"},
    {"position": 6, "subtype": "mcq",
     "stem": "What is one purpose of a school garden?",
     "options": ["To replace science classrooms",
                 "To give students practical learning opportunities",
                 "To provide teachers with additional holidays",
                 "To make schools larger"],
     "answer": "B"},
    {"position": 9, "subtype": "completion",
     "stem": "Students can measure the __________ of plants.",
     "options": [], "answer": "height", "acceptable_answers": ["height"]}
  ]
}
```

```json
{
  "label": "W01",
  "questions": [
    {"position": 1, "subtype": "grammar",
     "stem": "Maria ___ to work by bus every day.",
     "options": ["go", "goes", "going", "gone"], "answer": "B"},
    {"position": 4, "subtype": "vocabulary",
     "stem": "The teacher encouraged the students to participate.",
     "options": ["stopped", "motivated", "ignored", "punished"], "answer": "B"},
    {"position": 6, "subtype": "jumbled",
     "stem": "A. Finally, she submitted the application online.\nB. First, she collected all the required documents.\nC. Then, she completed the application form.\nD. After checking everything, she uploaded the documents.",
     "options": ["B-C-D-A", "C-B-A-D", "B-D-C-A", "D-B-C-A"], "answer": "A"},
    {"position": 9, "subtype": "fill_blank",
     "stem": "If it rains tomorrow, we ___ at home.",
     "options": ["stay", "stayed", "will stay", "staying"], "answer": "C"}
  ]
}
```

```json
{
  "label": "S01",
  "prompts": [
    {"position": 1, "task": "introduction",
     "prompt": "Speak for 30-45 seconds. What is your name? Which grade are you in? Where do you live? What do you enjoy doing?",
     "bullets": [], "marks": 2},
    {"position": 2, "task": "experience",
     "prompt": "Describe a memorable day at school.",
     "bullets": ["when it happened", "what happened",
                 "who was with you", "why you remember it"], "marks": 2}
  ]
}
```

Each example shows only representative positions; a real file carries all 10 questions (or all 5 prompts), numbered 1-10 (or 1-5) with no gaps.

Verify: `.venv\Scripts\python.exe manage.py import_authored --dir diagnostics/authored/content`
Expected: `Imported 1 reading, 1 writing, 1 speaking sets.`

**Note — the Version 1 passage does not meet the client's own pattern.** "The School Garden" is **221 words**; the CSV specifies 150–180, so it will fail the validator by a wide margin. Trimming to 180 means cutting at least 41 words (19%), and every one of the 10 questions depends on facts in the passage — including question 5, whose answer is NOT GIVEN precisely *because* the passage omits something.

Do not trim it unilaterally. Produce a trimmed candidate, verify all 10 answers still hold against the shortened text (especially the NOT GIVEN item, which silently breaks if a trim removes the wrong sentence), and put both versions to the user for approval before importing.

- [ ] **Step 4: Author R02–R12 in batches of four**

For each batch, write four passages of 150–180 words at CEFR B1 on neutral, age-appropriate topics, each with 5 TRUE/FALSE/NOT GIVEN + 3 four-option MCQ + 2 two-word completion questions.

Every NOT GIVEN item must be genuinely absent from the passage rather than contradicted — that is the distinction the item type tests, and getting it wrong is the most common authoring failure.

After each batch run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_content_completeness -v 2`
Then present the batch to the user for approval before starting the next.

- [ ] **Step 5: Author W02–W12 in batches of four**

Each set: 3 grammar + 2 vocabulary + 3 jumbled + 2 fill-blank, all four-option, single key.

Jumbled items follow the Version 1 shape: four sentences labelled A–D, and four candidate orderings as the options. Exactly one ordering must be defensible — check that no second ordering also reads coherently, since that would make the item unmarkable.

Same validate-then-review loop as Step 4.

- [ ] **Step 6: Author S02–S12 in batches of four**

Each set: the five fixed tasks in order, 2 marks each, with bullet guidance on tasks 2 and 4. No images.

Same validate-then-review loop.

- [ ] **Step 7: Import everything and verify**

Run: `.venv\Scripts\python.exe manage.py import_authored --dir diagnostics/authored/content`
Expected: `Imported 12 reading, 12 writing, 12 speaking sets.`

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_content_completeness -v 2`
Expected: PASS, 3 tests

- [ ] **Step 8: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics`
Expected: OK

---

### Task 16: `build_papers` and `check_papers`

**Files:**
- Create: `diagnostics/management/commands/build_papers.py`, `diagnostics/management/commands/check_papers.py`
- Test: `diagnostics/tests/test_build_papers.py`

- [ ] **Step 1: Write the failing test**

Create `diagnostics/tests/test_build_papers.py`:

```python
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from diagnostics.constants import CLIP_TASK_TYPES, PAPER_ALLOCATION, TaskType
from diagnostics.models import (
    AudioClip, Paper, ReadingPassage, SpeakingSet, WritingSet,
)


def seed_content():
    for number in range(1, 21):
        AudioClip.objects.create(number=number, task_type=CLIP_TASK_TYPES[number])
    for n in range(1, 13):
        ReadingPassage.objects.create(
            label=f"R{n:02d}", title=f"T{n}", body=" ".join(["word"] * 160)
        )
        WritingSet.objects.create(label=f"W{n:02d}")
        SpeakingSet.objects.create(label=f"S{n:02d}")


class BuildPapersTests(TestCase):
    def setUp(self):
        seed_content()

    def test_builds_twelve_papers(self):
        call_command("build_papers", stdout=StringIO())
        self.assertEqual(Paper.objects.count(), 12)

    def test_clips_match_the_allocation_table(self):
        call_command("build_papers", stdout=StringIO())
        for (grade, variant), (first, second) in PAPER_ALLOCATION.items():
            paper = Paper.objects.get(grade=grade, variant=variant)
            self.assertEqual(paper.listening_clip_1.number, first)
            self.assertEqual(paper.listening_clip_2.number, second)

    def test_authored_sets_are_assigned_one_per_paper(self):
        call_command("build_papers", stdout=StringIO())
        labels = [p.reading_passage.label for p in Paper.objects.all()]
        self.assertEqual(len(set(labels)), 12)

    def test_missing_content_aborts_before_writing_anything(self):
        ReadingPassage.objects.all().delete()
        with self.assertRaises(CommandError):
            call_command("build_papers", stdout=StringIO())
        self.assertEqual(Paper.objects.count(), 0)

    def test_rebuild_is_idempotent(self):
        call_command("build_papers", stdout=StringIO())
        call_command("build_papers", stdout=StringIO())
        self.assertEqual(Paper.objects.count(), 12)


class CheckPapersTests(TestCase):
    def setUp(self):
        seed_content()
        call_command("build_papers", stdout=StringIO())

    def test_passes_on_a_correctly_built_bank(self):
        out = StringIO()
        call_command("check_papers", stdout=out)
        self.assertIn("All 12 papers pass", out.getvalue())

    def test_fails_loudly_when_a_grade_repeats_a_component(self):
        paper = Paper.objects.get(grade=9, variant="B")
        sibling = Paper.objects.get(grade=9, variant="A")
        Paper.objects.filter(pk=paper.pk).update(
            reading_passage=sibling.reading_passage
        )
        with self.assertRaises(CommandError) as ctx:
            call_command("check_papers", stdout=StringIO())
        self.assertIn("Grade 9", str(ctx.exception))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_build_papers -v 2`
Expected: FAIL — `CommandError: Unknown command: 'build_papers'`

- [ ] **Step 3: Write `build_papers`**

Create `diagnostics/management/commands/build_papers.py`:

```python
"""Assemble the twelve fixed diagnostic papers (spec 3.2).

Listening clips come from the verified allocation table. Authored sets are
handed out one per paper in canonical order, so R01..R12 map to
G9-A..G11-D. There is no sampling and no randomness anywhere.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from diagnostics.constants import PAPER_ALLOCATION, PAPER_ORDER
from diagnostics.models import (
    AudioClip, Paper, ReadingPassage, SpeakingSet, WritingSet,
)


class Command(BaseCommand):
    help = "Build the 12 fixed diagnostic papers from the allocation table."

    def handle(self, *args, **options):
        clips = {clip.number: clip for clip in AudioClip.objects.all()}
        missing_clips = set(range(1, 21)) - set(clips)
        if missing_clips:
            raise CommandError(
                f"Missing listening clips {sorted(missing_clips)}. "
                f"Run import_listening first."
            )

        readings = self._ordered(ReadingPassage, "R")
        writings = self._ordered(WritingSet, "W")
        speakings = self._ordered(SpeakingSet, "S")

        with transaction.atomic():
            for index, (grade, variant) in enumerate(PAPER_ORDER):
                first, second = PAPER_ALLOCATION[(grade, variant)]
                Paper.objects.update_or_create(
                    grade=grade,
                    variant=variant,
                    defaults={
                        "listening_clip_1": clips[first],
                        "listening_clip_2": clips[second],
                        "reading_passage": readings[index],
                        "writing_set": writings[index],
                        "speaking_set": speakings[index],
                        "is_published": True,
                    },
                )

        self.stdout.write(self.style.SUCCESS(f"Built {Paper.objects.count()} papers."))

    def _ordered(self, model, prefix):
        expected = [f"{prefix}{n:02d}" for n in range(1, 13)]
        found = {obj.label: obj for obj in model.objects.filter(label__in=expected)}
        missing = [label for label in expected if label not in found]
        if missing:
            raise CommandError(
                f"Missing {model.__name__} sets {missing}. Run import_authored first."
            )
        return [found[label] for label in expected]
```

- [ ] **Step 4: Write `check_papers`**

Create `diagnostics/management/commands/check_papers.py`:

```python
"""Assert the inviolable rule: no repetition within a grade (spec 4.3).

Deliberately independent of Paper.clean() — this recomputes the answer from
what is actually stored, so a paper written by a bulk update that skipped
validation is still caught.
"""

from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError

from diagnostics.constants import GRADES, VARIANTS
from diagnostics.models import Paper, SHARED_COMPONENT_FIELDS


class Command(BaseCommand):
    help = "Verify that the four variants in each grade share no content."

    def handle(self, *args, **options):
        papers = list(Paper.objects.select_related(*[f for f, _ in SHARED_COMPONENT_FIELDS]))
        expected = len(GRADES) * len(VARIANTS)
        if len(papers) != expected:
            raise CommandError(f"Expected {expected} papers, found {len(papers)}.")

        problems = []
        for grade in GRADES:
            owners = defaultdict(list)
            for paper in (p for p in papers if p.grade == grade):
                for label, component in paper.components():
                    owners[(label, component.pk)].append(paper.variant)

            for (label, _pk), variants in sorted(owners.items()):
                if len(variants) > 1:
                    problems.append(
                        f"Grade {grade}: variants {', '.join(sorted(variants))} "
                        f"share a {label}."
                    )

        if problems:
            raise CommandError("Uniqueness violated:\n  " + "\n  ".join(problems))

        self.stdout.write(self.style.SUCCESS(
            f"All {len(papers)} papers pass the within-grade uniqueness check."
        ))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_build_papers -v 2`
Expected: PASS, 7 tests

- [ ] **Step 6: Build against the real database**

Run: `.venv\Scripts\python.exe manage.py build_papers`
Expected: `Built 12 papers.`

Run: `.venv\Scripts\python.exe manage.py check_papers`
Expected: `All 12 papers pass the within-grade uniqueness check.`

- [ ] **Step 7: Checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics`
Expected: OK

---

### Task 17: `render_paper` — a complete paper you can look at

Proves the whole chain end to end and gives the user something concrete to review.

**Files:**
- Create: `diagnostics/rendering.py`, `diagnostics/management/commands/render_paper.py`
- Test: `diagnostics/tests/test_rendering.py`

- [ ] **Step 1: Write the failing test**

Create `diagnostics/tests/test_rendering.py`:

```python
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diagnostics.models import Paper
from diagnostics.rendering import paper_sections
from diagnostics.tests.test_build_papers import seed_content


class PaperSectionsTests(TestCase):
    def setUp(self):
        seed_content()
        call_command("build_papers", stdout=StringIO())
        self.paper = Paper.objects.get(grade=9, variant="A")

    def test_four_sections_of_ten_marks_each(self):
        sections = paper_sections(self.paper)
        self.assertEqual([s["title"] for s in sections],
                         ["Listening", "Reading", "Writing", "Speaking"])
        self.assertEqual([s["marks"] for s in sections], [10, 10, 10, 10])

    def test_total_is_forty_marks(self):
        self.assertEqual(sum(s["marks"] for s in paper_sections(self.paper)), 40)

    def test_listening_section_names_both_clips(self):
        listening = paper_sections(self.paper)[0]
        self.assertEqual(len(listening["clips"]), 2)


class RenderPaperCommandTests(TestCase):
    def setUp(self):
        seed_content()
        call_command("build_papers", stdout=StringIO())

    def test_writes_a_docx_and_a_key(self):
        import tempfile
        from pathlib import Path

        out_dir = Path(tempfile.mkdtemp())
        call_command(
            "render_paper", "--grade", "9", "--variant", "A",
            "--out", str(out_dir), stdout=StringIO(),
        )
        self.assertTrue((out_dir / "G9-A-Student.docx").exists())
        self.assertTrue((out_dir / "G9-A-AnswerKey.docx").exists())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_rendering -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'diagnostics.rendering'`

- [ ] **Step 3: Write the section builder**

Create `diagnostics/rendering.py`:

```python
"""Turn a Paper into printable structures (spec 6).

One place decides what a paper *contains*; the docx writer and the later HTML
view both consume this, so the two can never drift apart.
"""

SECTION_MARKS = 10


def paper_sections(paper):
    """Return the four sections of a paper, in order."""
    return [
        {
            "title": "Listening",
            "marks": SECTION_MARKS,
            "instructions": "You will hear each recording twice. Answer all questions.",
            "clips": [
                {
                    "number": clip.number,
                    "intro": clip.intro_text,
                    "audio": clip.audio_file.name if clip.audio_file else "",
                    "questions": list(clip.questions.all()),
                }
                for clip in (paper.listening_clip_1, paper.listening_clip_2)
            ],
        },
        {
            "title": "Reading",
            "marks": SECTION_MARKS,
            "instructions": "Read the passage and answer all questions.",
            "passage": paper.reading_passage,
            "questions": list(paper.reading_passage.questions.all()),
        },
        {
            "title": "Writing",
            "marks": SECTION_MARKS,
            "instructions": "Choose the correct option for each question.",
            "questions": list(paper.writing_set.questions.all()),
        },
        {
            "title": "Speaking",
            "marks": SECTION_MARKS,
            "instructions": "Answer the examiner's questions. Two marks per task.",
            "prompts": list(paper.speaking_set.prompts.all()),
        },
    ]


def answer_key(paper):
    """Return [(section title, [(label, answer)])] for the marking sheet."""
    listening = []
    for clip in (paper.listening_clip_1, paper.listening_clip_2):
        for question in clip.questions.all():
            alternatives = (
                f" (also: {', '.join(question.acceptable_answers)})"
                if len(question.acceptable_answers) > 1 else ""
            )
            listening.append(
                (f"Clip {clip.number} Q{question.position}",
                 f"{question.answer}{alternatives}")
            )

    reading = [
        (f"Q{q.position}", q.answer) for q in paper.reading_passage.questions.all()
    ]
    writing = [
        (f"Q{q.position}", q.answer) for q in paper.writing_set.questions.all()
    ]
    speaking = [
        (f"Q{p.position}", f"{p.marks} marks — examiner judgement")
        for p in paper.speaking_set.prompts.all()
    ]
    return [
        ("Listening", listening),
        ("Reading", reading),
        ("Writing", writing),
        ("Speaking", speaking),
    ]
```

- [ ] **Step 4: Write the command**

Create `diagnostics/management/commands/render_paper.py`:

```python
"""Render one paper to .docx — student copy plus answer key."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from diagnostics.models import Paper
from diagnostics.rendering import answer_key, paper_sections


class Command(BaseCommand):
    help = "Render a paper to .docx (student copy and answer key)."

    def add_arguments(self, parser):
        parser.add_argument("--grade", type=int, required=True)
        parser.add_argument("--variant", required=True)
        parser.add_argument("--out", default=".")

    def handle(self, *args, **options):
        try:
            from docx import Document
            from docx.shared import Inches
        except ImportError as error:
            raise CommandError(
                "python-docx is required: pip install python-docx"
            ) from error

        try:
            paper = Paper.objects.get(grade=options["grade"], variant=options["variant"])
        except Paper.DoesNotExist as error:
            raise CommandError(
                f"No paper for grade {options['grade']} variant {options['variant']}."
            ) from error

        out_dir = Path(options["out"])
        out_dir.mkdir(parents=True, exist_ok=True)

        student_path = out_dir / f"{paper}-Student.docx"
        key_path = out_dir / f"{paper}-AnswerKey.docx"

        self._write_student(Document(), Inches, paper).save(student_path)
        self._write_key(Document(), paper).save(key_path)

        self.stdout.write(self.style.SUCCESS(f"Wrote {student_path} and {key_path}"))

    def _write_student(self, document, Inches, paper):
        document.add_heading(f"English Diagnostic Test — Grade {paper.grade}, Variant {paper.variant}", level=1)
        document.add_paragraph("CEFR B1 | 40 marks | 40 minutes")

        for section in paper_sections(paper):
            document.add_heading(f"{section['title']} ({section['marks']} marks)", level=2)
            document.add_paragraph(section["instructions"])

            if section["title"] == "Listening":
                for clip in section["clips"]:
                    document.add_paragraph(f"Recording {clip['number']}", style="Intense Quote")
                    if clip["intro"]:
                        document.add_paragraph(clip["intro"])
                    for question in clip["questions"]:
                        document.add_paragraph(f"{question.position}. {question.stem}")
                        if question.image:
                            document.add_picture(question.image.path, width=Inches(6))
                        for option in question.options:
                            document.add_paragraph(str(option), style="List Bullet")
            elif section["title"] == "Reading":
                document.add_heading(section["passage"].title, level=3)
                document.add_paragraph(section["passage"].body)
                for question in section["questions"]:
                    document.add_paragraph(f"{question.position}. {question.stem}")
                    for option in question.options:
                        document.add_paragraph(str(option), style="List Bullet")
            elif section["title"] == "Writing":
                for question in section["questions"]:
                    document.add_paragraph(f"{question.position}. {question.stem}")
                    for letter, option in zip("ABCD", question.options):
                        document.add_paragraph(f"{letter}) {option}", style="List Bullet")
            else:
                for prompt in section["prompts"]:
                    document.add_paragraph(
                        f"{prompt.position}. {prompt.prompt} ({prompt.marks} marks)"
                    )
                    for bullet in prompt.bullets:
                        document.add_paragraph(str(bullet), style="List Bullet")
        return document

    def _write_key(self, document, paper):
        document.add_heading(f"Answer Key — {paper}", level=1)
        for title, rows in answer_key(paper):
            document.add_heading(title, level=2)
            for label, value in rows:
                document.add_paragraph(f"{label}: {value}")
        return document
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe manage.py test diagnostics.tests.test_rendering -v 2`
Expected: PASS, 5 tests

- [ ] **Step 6: Render a real paper and show the user**

Run: `.venv\Scripts\python.exe manage.py render_paper --grade 9 --variant A --out exports`
Expected: `Wrote exports\G9-A-Student.docx and exports\G9-A-AnswerKey.docx`

Send both files to the user for review. This is the first time they see a complete assembled paper — expect formatting feedback.

- [ ] **Step 7: Final checkpoint**

Run: `.venv\Scripts\python.exe manage.py test diagnostics -v 2`
Expected: OK — all tests across every module

Run: `.venv\Scripts\python.exe manage.py check_papers`
Expected: `All 12 papers pass the within-grade uniqueness check.`

---

## Done when

- 20 clips, 100 listening questions and 25 images are in the database
- All 100 listening answers have been checked by a human and signed off
- 12 reading passages, 12 writing sets and 12 speaking sets validate and import
- 12 papers exist, and `check_papers` passes
- Any paper renders to a student `.docx` plus an answer key
- `python manage.py test diagnostics` is green

Phases 4–6 — teacher UI, ZIP packs, generation tracking, admin coverage report and merge seams — follow in a separate plan.
