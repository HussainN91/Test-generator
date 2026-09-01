# Listening Question Bank Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A staff-only page listing every listening question set, titled with the grades and groups that actually sit it, with the transcript alongside, so the bank can be checked in one pass.

**Architecture:** Import the clip transcripts into a new `AudioClip.transcript` field. Put the grade/group derivation in a new pure module `diagnostics/listening_bank.py` so it is testable without HTTP. A thin staff-gated view arranges what that module returns into one template. Nothing writes to `Paper`, allocation, or question content.

**Tech Stack:** Django 5 / SQLite, `python manage.py test` (unittest), no third-party additions.

**Spec:** [`docs/superpowers/specs/2026-09-01-listening-question-bank-design.md`](../specs/2026-09-01-listening-question-bank-design.md)

**Baseline:** 923 tests passing on `main`. Every task below ends green. Run with:

```bash
python manage.py test
```

**Note on the interpreter:** Django is not on the default PATH on the development
machine. Use `D:/Test generator/.venv/Scripts/python.exe` in place of `python`
for every command below if `python manage.py` fails with `ModuleNotFoundError`.

---

## Part 0: What you need to know before starting

### 0.1 Question sets are not per grade

This is the whole reason the page is not trivial. Listening questions hang off a
`ListeningQuestionSet`, which hangs off an `AudioClip`. Grades and groups are an
*allocation* concept: `diagnostics/allocation.py` gives a clip pair to a group,
and the same clip goes to several groups across several grades.

So one question set belongs to many grade/group pairs at once:

```
clip 1, set 1  ->  Grade 9 groups 1, 6 · Grade 10 groups 3, 8 · Grade 11 group 5
```

Verified against the built bank: of the 40 sets in use, 12 serve one (grade,
group) pair, 18 serve two, 2 serve four and 8 serve five. **None is exclusive to
a single grade.**

### 0.2 Derive usage from Paper rows, not from the allocator

`diagnostics/verification.py` re-derives its answers from what is stored rather
than calling `Paper.clean()`, so a paper written by a bulk update is still
described correctly. This page follows the same rule: read `Paper.listening_set_1`
and `Paper.listening_set_2`, do not call `allocate()`. If the stored papers ever
disagree with the allocator, the page must show what is stored.

### 0.3 The relevant models

- `AudioClip` — `number`, `task_type`, `intro_text`, `audio_file` (`diagnostics/models/content.py:21`)
- `ListeningQuestionSet` — `clip` FK, `number` (1 or 2) (`:38`)
- `ListeningQuestion` — `question_set` FK, `position`, `stem`, `options` (JSON list), `image`, `answer`, `acceptable_answers` (`:73`)
- `Paper` — `grade`, `variant`, `listening_set_1` FK, `listening_set_2` FK

`ListeningQuestion.clip` is a read-only property reaching through the set.

### 0.4 Navigation helpers

`diagnostics/navigation.py` provides `group_for_variant(letter) -> int` (1-based)
and `GROUP_NUMBERS`. Variants A and B are group 1, C and D group 2, and so on.

### 0.5 Existing render helpers to reuse

- `diagnostics.rendering.option_rows(options)` — returns a list of lines, each a
  list of `(letter, option)` pairs.
- `diagnostics.rendering.needs_inline_blank(stem, options)` — bool.

Reusing them keeps this page agreeing with how the same question prints on a paper.

### 0.6 Transcript source file

`media/diagnostics/audio/transcripts-full.md`, 40 KB, gitignored. Structure:

```markdown
# Listening clip transcripts — all 20 clips

...preamble...

---

## Clip 1  [picture]

**1. Which dish did Mark cook in the competition?**
Interviewer: So you've won...

**2. Where is the girl's book now?**
Girl: Excuse me...

---

## Clip 2  [mcq3]

Interviewer: Hello everyone...
```

A clip's body runs from its `## Clip N` heading to the next `## ` or end of file.
Store it verbatim; do not split into items.

---

## Part 1: Store the transcripts

### Task 1.1: Add the field

**Files:**
- Modify: `diagnostics/models/content.py` (the `AudioClip` class, around line 21)
- Create: `diagnostics/migrations/0018_audioclip_transcript.py`
- Test: `diagnostics/tests/test_models_listening.py`

- [ ] **Step 1: Write the failing test**

Append to `diagnostics/tests/test_models_listening.py`:

```python
class AudioClipTranscriptTests(TestCase):
    """The transcript lives on the clip because it describes the recording,
    not any one question set - both sets of questions are about the same
    audio and are checked against the same words."""

    def test_a_clip_can_carry_a_transcript(self):
        clip = AudioClip.objects.create(
            number=1, task_type="picture", transcript="Interviewer: Hello."
        )
        clip.refresh_from_db()
        self.assertEqual(clip.transcript, "Interviewer: Hello.")

    def test_transcript_defaults_to_empty_not_null(self):
        """Empty string rather than NULL, so templates and str operations
        never have to special-case None."""
        clip = AudioClip.objects.create(number=2, task_type="mcq3")
        clip.refresh_from_db()
        self.assertEqual(clip.transcript, "")
```

If `AudioClip` is not already imported at the top of that file, add it to the
existing `from diagnostics.models import (...)` line.

- [ ] **Step 2: Run the test to verify it fails**

```bash
python manage.py test diagnostics.tests.test_models_listening.AudioClipTranscriptTests -v 2
```

Expected: FAIL — `TypeError: AudioClip() got unexpected keyword arguments: 'transcript'`.

- [ ] **Step 3: Add the field**

In `diagnostics/models/content.py`, inside `class AudioClip`, add after `audio_file`:

```python
    transcript = models.TextField(
        blank=True,
        help_text=(
            "The full spoken text of the recording, imported from "
            "media/diagnostics/audio/transcripts-full.md. Kept on the clip "
            "rather than the question set because both sets ask about the "
            "same audio and are checked against the same words."
        ),
    )
```

- [ ] **Step 4: Write the migration**

Create `diagnostics/migrations/0018_audioclip_transcript.py`:

```python
"""Give AudioClip somewhere to keep its transcript.

Until now the transcripts lived only in
media/diagnostics/audio/transcripts-full.md, which is gitignored and, for
clips 11-20, the sole copy in existence. Importing them into the database
also puts them inside the server's ordinary backup routine.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("diagnostics", "0017_paper_listening_sets")]

    operations = [
        migrations.AddField(
            model_name="audioclip",
            name="transcript",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "The full spoken text of the recording, imported from "
                    "media/diagnostics/audio/transcripts-full.md. Kept on the "
                    "clip rather than the question set because both sets ask "
                    "about the same audio and are checked against the same words."
                ),
            ),
        ),
    ]
```

- [ ] **Step 5: Apply it and confirm no model drift**

```bash
python manage.py migrate diagnostics
python manage.py makemigrations diagnostics --check --dry-run
```

Expected: `Applying diagnostics.0018_audioclip_transcript... OK`, then
`No changes detected`. If it wants another migration, the hand-written one does
not match the model — fix the migration, not the model.

- [ ] **Step 6: Run the test to verify it passes**

```bash
python manage.py test diagnostics.tests.test_models_listening -v 2
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add diagnostics/models/content.py diagnostics/migrations/0018_audioclip_transcript.py diagnostics/tests/test_models_listening.py
git commit -m "Give AudioClip a transcript field"
```

### Task 1.2: The import command

**Files:**
- Create: `diagnostics/management/commands/import_transcripts.py`
- Test: `diagnostics/tests/test_import_transcripts.py`

- [ ] **Step 1: Write the failing tests**

Create `diagnostics/tests/test_import_transcripts.py`:

```python
"""The transcripts are the only record of what each recording actually says,
and for clips 11-20 the markdown file is the sole copy. The importer is
therefore written to fail loudly rather than half-fill the bank."""

from io import StringIO
from pathlib import Path
import tempfile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from diagnostics.models import AudioClip

SAMPLE = """# Listening clip transcripts

Some preamble that is not a clip.

---

## Clip 1  [picture]

**1. Which dish did Mark cook?**
Interviewer: So you've won.

**2. Where is the book?**
Girl: Excuse me.

---

## Clip 2  [mcq3]

Interviewer: Hello everyone.

---
"""


class ImportTranscriptsTests(TestCase):
    def setUp(self):
        self.clip_1 = AudioClip.objects.create(number=1, task_type="picture")
        self.clip_2 = AudioClip.objects.create(number=2, task_type="mcq3")
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        )
        handle.write(SAMPLE)
        handle.close()
        self.source = Path(handle.name)

    def _run(self):
        call_command("import_transcripts", source=str(self.source), stdout=StringIO())

    def test_each_clip_gets_its_own_body(self):
        self._run()
        self.clip_1.refresh_from_db()
        self.clip_2.refresh_from_db()
        self.assertIn("Which dish did Mark cook?", self.clip_1.transcript)
        self.assertIn("Interviewer: Hello everyone.", self.clip_2.transcript)

    def test_a_clips_body_stops_at_the_next_clip(self):
        """Clip 1 must not swallow clip 2's text - the whole point of the
        page is checking a question against the right recording."""
        self._run()
        self.clip_1.refresh_from_db()
        self.assertNotIn("Hello everyone", self.clip_1.transcript)

    def test_preamble_is_not_stored_on_any_clip(self):
        self._run()
        for clip in AudioClip.objects.all():
            self.assertNotIn("Some preamble", clip.transcript)

    def test_rerunning_changes_nothing(self):
        self._run()
        before = {c.number: c.transcript for c in AudioClip.objects.all()}
        self._run()
        after = {c.number: c.transcript for c in AudioClip.objects.all()}
        self.assertEqual(before, after)

    def test_a_missing_file_is_a_command_error(self):
        with self.assertRaisesMessage(CommandError, "no-such-file.md"):
            call_command(
                "import_transcripts", source="no-such-file.md", stdout=StringIO()
            )

    def test_a_transcript_for_an_unimported_clip_is_reported_not_ignored(self):
        """A transcript with nowhere to go means the clip bank and the
        transcript file disagree, which the operator needs told."""
        AudioClip.objects.filter(number=2).delete()
        out = StringIO()
        call_command("import_transcripts", source=str(self.source), stdout=out)
        self.assertIn("2", out.getvalue())

    def test_reports_how_many_clips_it_filled(self):
        out = StringIO()
        call_command("import_transcripts", source=str(self.source), stdout=out)
        self.assertIn("2", out.getvalue())
```

- [ ] **Step 2: Run to verify they fail**

```bash
python manage.py test diagnostics.tests.test_import_transcripts -v 2
```

Expected: FAIL — `CommandError: Unknown command: 'import_transcripts'`.

- [ ] **Step 3: Write the command**

Create `diagnostics/management/commands/import_transcripts.py`:

```python
"""Load the clip transcripts from the authored markdown into the database.

The file is gitignored and, for clips 11-20, the only copy that exists, so
this command is how those words stop being a single point of failure: once
imported they are covered by the ordinary database backup.

Idempotent: each run overwrites every clip's transcript from the file. It
never touches questions, sets or papers.
"""

import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from diagnostics.models import AudioClip

DEFAULT_SOURCE = (
    Path(settings.MEDIA_ROOT) / "diagnostics" / "audio" / "transcripts-full.md"
)

#: A clip's body runs from its own "## Clip N" heading to the next "## " at
#: the start of a line, or the end of the file. Non-greedy so clip 1 cannot
#: swallow clip 2, which would silently show a reviewer the wrong recording.
CLIP_RE = re.compile(
    r"^##\s*Clip\s+(\d+)\b.*?$(.*?)(?=^##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)


class Command(BaseCommand):
    help = "Import clip transcripts from the authored markdown file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source", default=None,
            help=f"Override the markdown path (default {DEFAULT_SOURCE}).",
        )

    def handle(self, *args, **options):
        source = Path(options["source"]) if options["source"] else DEFAULT_SOURCE
        if not source.exists():
            raise CommandError(f"Missing transcript file: {source}")

        text = source.read_text(encoding="utf-8")
        bodies = {
            int(number): body.strip()
            for number, body in CLIP_RE.findall(text)
        }
        if not bodies:
            raise CommandError(
                f"No '## Clip N' headings found in {source}; the file is not "
                f"in the expected format."
            )

        clips = {clip.number: clip for clip in AudioClip.objects.all()}

        with transaction.atomic():
            filled = 0
            for number, body in sorted(bodies.items()):
                clip = clips.get(number)
                if clip is None:
                    continue
                clip.transcript = body
                clip.save(update_fields=["transcript"])
                filled += 1

        self.stdout.write(self.style.SUCCESS(
            f"Imported transcripts for {filled} clips."
        ))

        homeless = sorted(set(bodies) - set(clips))
        if homeless:
            self.stdout.write(self.style.WARNING(
                f"Transcripts for clips {homeless} have no imported AudioClip. "
                f"Run import_listening first if that is unexpected."
            ))

        empty = sorted(number for number, clip in clips.items() if not clip.transcript)
        if empty:
            self.stdout.write(self.style.WARNING(
                f"Clips {empty} have no transcript in the file."
            ))
```

- [ ] **Step 4: Run to verify they pass**

```bash
python manage.py test diagnostics.tests.test_import_transcripts -v 2
```

Expected: PASS, all seven.

- [ ] **Step 5: Run it against the real file**

```bash
python manage.py import_transcripts
```

Expected: `Imported transcripts for 20 clips.` with no warnings. If it reports
clips with no transcript, the markdown and the clip bank disagree — investigate
before continuing, do not proceed with a partial import.

- [ ] **Step 6: Spot-check one clip end to end**

```bash
python manage.py shell -c "from diagnostics.models import AudioClip; c=AudioClip.objects.get(number=16); print(len(c.transcript)); print(c.transcript[:120]); print('LEAKED' if 'Clip 17' in c.transcript else 'clean boundary')"
```

Expected: a length in the low thousands, text beginning with clip 16's own
words, and `clean boundary`.

- [ ] **Step 7: Commit**

```bash
git add diagnostics/management/commands/import_transcripts.py diagnostics/tests/test_import_transcripts.py
git commit -m "Import the clip transcripts into the database"
```

---

## Part 2: Derive the grade and group usage

### Task 2.1: The usage module

**Files:**
- Create: `diagnostics/listening_bank.py`
- Test: `diagnostics/tests/test_listening_bank.py`

This is a separate module rather than view code so the mapping — the part that
is actually easy to get wrong — can be tested without HTTP.

- [ ] **Step 1: Write the failing tests**

Create `diagnostics/tests/test_listening_bank.py`:

```python
"""Which grades and groups sit a given question set.

Derived from stored Paper rows rather than from allocation.py, for the same
reason verification.py re-derives its answers: a paper written by a bulk
update has to be described as it actually is, not as the allocator would
have made it.
"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diagnostics.listening_bank import set_usage, usage_title
from diagnostics.models import ListeningQuestionSet, Paper
from diagnostics.tests.test_build_papers import seed_content


class UsageOnABuiltBankTests(TestCase):
    def setUp(self):
        seed_content()
        call_command("build_papers", "--resample", stdout=StringIO())

    def test_every_set_a_paper_uses_is_reported(self):
        usage = set_usage()
        used = set(
            Paper.objects.values_list("listening_set_1_id", flat=True)
        ) | set(Paper.objects.values_list("listening_set_2_id", flat=True))
        self.assertEqual(set(usage) & used, used)

    def test_a_set_maps_to_grade_and_group_pairs(self):
        usage = set_usage()
        paper = Paper.objects.get(grade=9, variant="A")
        self.assertIn((9, 1), usage[paper.listening_set_1_id])

    def test_both_variants_of_a_group_collapse_to_one_pair(self):
        """A and B are one sitting, so a set both papers use is listed once
        for that group, not twice."""
        usage = set_usage()
        paper = Paper.objects.get(grade=9, variant="A")
        pairs = usage[paper.listening_set_1_id]
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_a_set_no_paper_uses_reports_empty(self):
        orphan = ListeningQuestionSet.objects.exclude(
            pk__in=Paper.objects.values_list("listening_set_1_id", flat=True)
        ).exclude(
            pk__in=Paper.objects.values_list("listening_set_2_id", flat=True)
        ).first()
        if orphan is None:
            self.skipTest("every set is allocated in this bank")
        self.assertEqual(set_usage().get(orphan.pk, []), [])


class UsageTitleTests(TestCase):
    def test_groups_are_listed_per_grade(self):
        title = usage_title([(9, 1), (9, 6), (10, 3), (10, 8), (11, 5)])
        self.assertEqual(
            title,
            "Grade 9 groups 1, 6 · Grade 10 groups 3, 8 · Grade 11 group 5",
        )

    def test_a_single_group_is_singular(self):
        self.assertEqual(usage_title([(9, 2)]), "Grade 9 group 2")

    def test_pairs_are_sorted_regardless_of_input_order(self):
        self.assertEqual(
            usage_title([(11, 5), (9, 6), (9, 1)]),
            "Grade 9 groups 1, 6 · Grade 11 group 5",
        )

    def test_an_unused_set_says_so_rather_than_returning_blank(self):
        """A set with no home is exactly what a reviewer needs to see."""
        self.assertEqual(usage_title([]), "Not currently allocated to any paper")
```

- [ ] **Step 2: Run to verify they fail**

```bash
python manage.py test diagnostics.tests.test_listening_bank -v 2
```

Expected: FAIL — `ModuleNotFoundError: No module named 'diagnostics.listening_bank'`.

- [ ] **Step 3: Write the module**

Create `diagnostics/listening_bank.py`:

```python
"""Which grades and groups actually sit each listening question set.

Read from stored Paper rows, never from allocation.py. verification.py takes
the same line and for the same reason: the question a reviewer is asking is
"what did we issue", not "what would the allocator issue".

A group, not a variant, is the unit here - a group is one room at one time,
and its two variants sit the same recording, so listing both letters would
say the same thing twice.
"""

from collections import defaultdict

from diagnostics.models import Paper
from diagnostics.navigation import group_for_variant


def set_usage():
    """Map question set id -> sorted list of (grade, group) pairs.

    Every set that any paper uses appears. A set no paper uses is absent;
    callers should treat a missing key as "unallocated" rather than an
    error - see usage_title.
    """
    pairs = defaultdict(set)
    rows = Paper.objects.values_list(
        "grade", "variant", "listening_set_1_id", "listening_set_2_id"
    )
    for grade, variant, first, second in rows:
        group = group_for_variant(variant)
        for set_id in (first, second):
            if set_id is not None:
                pairs[set_id].add((grade, group))
    return {set_id: sorted(found) for set_id, found in pairs.items()}


def usage_title(pairs):
    """Render (grade, group) pairs as one human title.

    "Grade 9 groups 1, 6 · Grade 10 groups 3, 8 · Grade 11 group 5"

    Compound because no question set is exclusive to one grade: the same
    recording is issued to several grades, so a single-grade title would be
    wrong for most of the bank.
    """
    if not pairs:
        return "Not currently allocated to any paper"

    by_grade = defaultdict(list)
    for grade, group in sorted(set(pairs)):
        by_grade[grade].append(group)

    parts = []
    for grade, groups in sorted(by_grade.items()):
        label = "group" if len(groups) == 1 else "groups"
        parts.append(f"Grade {grade} {label} {', '.join(str(g) for g in groups)}")
    return " · ".join(parts)
```

- [ ] **Step 4: Run to verify they pass**

```bash
python manage.py test diagnostics.tests.test_listening_bank -v 2
```

Expected: PASS.

- [ ] **Step 5: Confirm the multiplicities against the real bank**

```bash
python manage.py shell -c "
from collections import Counter
from diagnostics.listening_bank import set_usage
u = set_usage()
print('sets used:', len(u))
print('multiplicity:', dict(sorted(Counter(len(v) for v in u.values()).items())))
"
```

Expected: `sets used: 40` and `multiplicity: {1: 12, 2: 18, 4: 2, 5: 8}`. These
are the numbers the design was written against. A different shape means the
allocation changed — stop and reconcile before building the page on top of it.

- [ ] **Step 6: Commit**

```bash
git add diagnostics/listening_bank.py diagnostics/tests/test_listening_bank.py
git commit -m "Derive which grades and groups sit each listening set"
```

### Task 2.2: The answer key balance

**Files:**
- Modify: `diagnostics/listening_bank.py`
- Test: `diagnostics/tests/test_listening_bank.py`

A lopsided key is guessable. This is the check that caught set 2's mcq3 skew
(A=6 B=14 C=5) during the 2026-09-01 content review.

- [ ] **Step 1: Write the failing test**

Append to `diagnostics/tests/test_listening_bank.py`:

```python
class KeyBalanceTests(TestCase):
    def setUp(self):
        seed_content()

    def test_counts_answers_per_task_type(self):
        from diagnostics.listening_bank import key_balance
        from diagnostics.models import AudioClip, ListeningQuestion

        clip = AudioClip.objects.get(number=2)   # mcq3
        question_set = clip.question_sets.get(number=1)
        for position, answer in enumerate("ABBBC", start=1):
            ListeningQuestion.objects.create(
                question_set=question_set, position=position,
                stem=f"q{position}", options=["x", "y", "z"], answer=answer,
            )
        balance = key_balance(ListeningQuestion.objects.filter(
            question_set=question_set
        ))
        self.assertEqual(balance["mcq3"], {"A": 1, "B": 3, "C": 1})

    def test_a_task_type_with_no_questions_is_absent_not_zeroed(self):
        from diagnostics.listening_bank import key_balance
        from diagnostics.models import ListeningQuestion

        self.assertEqual(key_balance(ListeningQuestion.objects.none()), {})
```

- [ ] **Step 2: Run to verify it fails**

```bash
python manage.py test diagnostics.tests.test_listening_bank.KeyBalanceTests -v 2
```

Expected: FAIL — `ImportError: cannot import name 'key_balance'`.

- [ ] **Step 3: Add the function**

Append to `diagnostics/listening_bank.py`:

```python
def key_balance(questions):
    """Count answer letters per task type across `questions`.

    A guessable key is a real defect: set 2's mcq3 answers were once
    A=6 B=14 C=5, so answering B every time scored 56% against 33% by
    chance. Showing the distribution makes that visible at a glance
    instead of needing someone to tally 200 answers by hand.

    Task types are kept apart because they are not comparable - true_false
    has two options and the rest have three.
    """
    counts = defaultdict(lambda: defaultdict(int))
    rows = questions.values_list("question_set__clip__task_type", "answer")
    for task_type, answer in rows:
        counts[task_type][answer] += 1
    return {task: dict(sorted(letters.items())) for task, letters in counts.items()}
```

- [ ] **Step 4: Run to verify it passes**

```bash
python manage.py test diagnostics.tests.test_listening_bank -v 2
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add diagnostics/listening_bank.py diagnostics/tests/test_listening_bank.py
git commit -m "Count listening answer-key balance per task type"
```

---

## Part 3: The page

### Task 3.1: The view and route

**Files:**
- Modify: `diagnostics/views.py`
- Modify: `diagnostics/urls.py`
- Test: `diagnostics/tests/test_listening_bank.py`

- [ ] **Step 1: Write the failing tests**

Append to `diagnostics/tests/test_listening_bank.py`:

```python
from django.contrib.auth import get_user_model
from django.urls import reverse


class ListeningBankViewTests(TestCase):
    def setUp(self):
        seed_content()
        call_command("build_papers", "--resample", stdout=StringIO())
        User = get_user_model()
        self.staff = User.objects.create_user(
            "boss", password="pw", is_staff=True
        )
        self.teacher = User.objects.create_user("teacher", password="pw")
        self.url = reverse("diagnostics:listening_bank")

    def test_staff_can_open_it(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_a_non_staff_user_gets_404_not_403(self):
        """404 rather than 403, matching _get_visible_paper: the page does
        not advertise its own existence to someone who may not have it."""
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_signed_out_users_are_sent_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_unfiltered_shows_every_set(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["entries"]), 40)

    def test_filtering_by_grade_narrows_the_list(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url, {"grade": 9})
        entries = response.context["entries"]
        self.assertLess(len(entries), 40)
        for entry in entries:
            self.assertTrue(
                any(grade == 9 for grade, _ in entry["pairs"]),
                entry["title"],
            )

    def test_an_unknown_grade_falls_back_to_all(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url, {"grade": "banana"})
        self.assertEqual(len(response.context["entries"]), 40)
        self.assertIsNone(response.context["selected_grade"])

    def test_entries_are_ordered_by_clip_then_set(self):
        self.client.force_login(self.staff)
        entries = self.client.get(self.url).context["entries"]
        keys = [(e["clip"].number, e["question_set"].number) for e in entries]
        self.assertEqual(keys, sorted(keys))

    def test_every_question_is_present(self):
        self.client.force_login(self.staff)
        entries = self.client.get(self.url).context["entries"]
        self.assertEqual(sum(len(e["questions"]) for e in entries), 200)
```

- [ ] **Step 2: Run to verify they fail**

```bash
python manage.py test diagnostics.tests.test_listening_bank.ListeningBankViewTests -v 2
```

Expected: FAIL — `NoReverseMatch: 'listening_bank' is not a valid view function or pattern name`.

- [ ] **Step 3: Add the route**

In `diagnostics/urls.py`, add to `urlpatterns`, immediately after the `""` index
route so it is matched before `<int:grade>/`:

```python
    path("listening/", views.listening_bank, name="listening_bank"),
```

- [ ] **Step 4: Add the view**

In `diagnostics/views.py`, add these imports to the existing import block:

```python
from diagnostics.listening_bank import key_balance, set_usage, usage_title
from diagnostics.models import ListeningQuestion, ListeningQuestionSet
```

(`Http404`, `login_required`, `render` and `GRADES` are already imported. Add
only the names that are missing.)

Add the view at the end of the file:

```python
@login_required
def listening_bank(request):
    """Every listening question on one page, for checking against the
    transcripts.

    Staff only: it shows all 200 answer keys. Grade tabs filter the same
    canonical list rather than repeating it per grade - a question set is
    typically sat by several grades, so repeating would mean proofreading
    the same question three times and would still not make the tabs a real
    boundary.
    """
    if not request.user.is_staff:
        raise Http404("No page here.")

    usage = set_usage()

    raw_grade = request.GET.get("grade")
    try:
        selected_grade = int(raw_grade) if raw_grade else None
    except (TypeError, ValueError):
        selected_grade = None
    if selected_grade not in GRADES:
        selected_grade = None

    question_sets = ListeningQuestionSet.objects.select_related("clip").order_by(
        "clip__number", "number"
    )

    entries = []
    for question_set in question_sets:
        pairs = usage.get(question_set.pk, [])
        if selected_grade is not None and not any(
            grade == selected_grade for grade, _ in pairs
        ):
            continue

        questions = list(question_set.questions.order_by("position"))
        for question in questions:
            question.option_rows = option_rows(question.options or [])
            question.inline_blank = needs_inline_blank(
                question.stem, question.options
            )
        entries.append({
            "question_set": question_set,
            "clip": question_set.clip,
            "pairs": pairs,
            "title": usage_title(pairs),
            "questions": questions,
        })

    visible_ids = [entry["question_set"].pk for entry in entries]
    return render(
        request,
        "diagnostics/listening_bank.html",
        {
            "entries": entries,
            "selected_grade": selected_grade,
            "grades": list(GRADES),
            "set_count": len(entries),
            "question_count": sum(len(e["questions"]) for e in entries),
            "clip_count": len({e["clip"].pk for e in entries}),
            "balance": key_balance(
                ListeningQuestion.objects.filter(question_set_id__in=visible_ids)
            ),
        },
    )
```

- [ ] **Step 5: Run to verify they pass**

The template does not exist yet, so expect `TemplateDoesNotExist` rather than
green. Confirm the failure has moved from the URL to the template:

```bash
python manage.py test diagnostics.tests.test_listening_bank.ListeningBankViewTests -v 2
```

Expected: FAIL — `TemplateDoesNotExist: diagnostics/listening_bank.html`.

- [ ] **Step 6: Commit**

```bash
git add diagnostics/views.py diagnostics/urls.py diagnostics/tests/test_listening_bank.py
git commit -m "Add the staff-only listening bank view"
```

### Task 3.2: The template

**Files:**
- Create: `templates/diagnostics/listening_bank.html`

- [ ] **Step 1: Write the template**

Create `templates/diagnostics/listening_bank.html`:

```html
{% extends "base.html" %}
{% block title %}Listening bank{% endblock %}

{% block content %}
<div class="head">
  <h1>Listening bank</h1>
  <div class="meta">
    <span>{{ clip_count }} RECORDINGS</span>
    <span>{{ set_count }} QUESTION SETS</span>
    <span>{{ question_count }} QUESTIONS</span>
  </div>
</div>

<div class="actions">
  <a class="btn {% if not selected_grade %}{% else %}ghost{% endif %}"
     href="{% url 'diagnostics:listening_bank' %}">All grades</a>
  {% for grade in grades %}
    <a class="btn {% if selected_grade == grade %}{% else %}ghost{% endif %}"
       href="{% url 'diagnostics:listening_bank' %}?grade={{ grade }}">Grade {{ grade }}</a>
  {% endfor %}
</div>

{% if balance %}
  <div class="cont" style="border-top:1px solid var(--ink)">Answer key balance</div>
  <ul class="tally">
    {% for task, letters in balance.items %}
      <li>
        <span class="k">{{ task }}</span><span class="dots"></span>
        <span class="n">{% for letter, count in letters.items %}{{ letter }}&nbsp;{{ count }}{% if not forloop.last %} &middot; {% endif %}{% endfor %}</span>
      </li>
    {% endfor %}
  </ul>
{% endif %}

{% for entry in entries %}
  <section class="blk">
    <div class="cont" style="border-top:1px solid var(--ink);border-bottom:1px solid var(--rule)">
      {{ entry.title }}
    </div>
    <p class="qinstr">
      Clip {{ entry.clip.number }} &middot; {{ entry.clip.get_task_type_display }}
      &middot; set {{ entry.question_set.number }}
    </p>

    {% if entry.clip.audio_file %}
      <audio class="clipaudio" controls preload="none" src="{{ entry.clip.audio_file.url }}">
        Your browser cannot play audio.
      </audio>
    {% endif %}
    {% if entry.clip.intro_text %}<p class="qinstr">{{ entry.clip.intro_text }}</p>{% endif %}

    <div class="bank-split">
      <div class="bank-questions">
        {% for question in entry.questions %}
          <div class="q">
            <span class="qn">{{ question.position }}</span>
            <div>
              <p class="qprompt"><strong>{{ question.stem }}</strong>{% if question.inline_blank %}<span class="blank"></span>{% endif %}</p>
              {% if question.image %}
                <img class="bank-image" src="{{ question.image.url }}" alt="Options for question {{ question.position }}">
              {% endif %}
              {% for row in question.option_rows %}
                <p class="qopts">
                  {% for letter, option in row %}
                    <span class="{% if letter == question.answer %}bank-correct{% endif %}">{{ letter }}. {{ option }}</span>
                  {% endfor %}
                </p>
              {% endfor %}
              <p class="bank-answer"><b>Answer:</b> {{ question.answer }}{% if question.acceptable_answers %} <span class="bank-alt">(also accept: {{ question.acceptable_answers|join:", " }})</span>{% endif %}</p>
            </div>
          </div>
        {% endfor %}
      </div>

      <aside class="bank-transcript">
        <h3>Transcript</h3>
        {% if entry.clip.transcript %}
          <pre>{{ entry.clip.transcript }}</pre>
        {% else %}
          <p class="qinstr">No transcript imported. Run <code>manage.py import_transcripts</code>.</p>
        {% endif %}
      </aside>
    </div>
  </section>
{% empty %}
  <p class="qinstr">No question sets match this filter.</p>
{% endfor %}
{% endblock %}
```

The block names are confirmed against `templates/base.html`: it defines `title`,
`head`, `chrome`, `content`, and one `nav_*` block per nav item. Add
`{% block nav_listening %} class="on"{% endblock %}` under the `{% block title %}`
line so the nav entry highlights, matching how `paper_detail.html` sets
`nav_diagnostics`.

- [ ] **Step 2: Add the styles**

Append to `static/css/paper.css`, which is where the existing `.q`, `.qprompt`,
`.qopts` and `.blk` rules live (shared with `paper_detail.html` and
`assembly/preview.html` — so keep the new class names prefixed `bank-` to avoid
changing how those two pages render):

```css
/* Listening bank only. `bank-` prefixed because paper.css is shared with the
   printed paper and the assembly preview - .qans in particular is already
   defined at line 166 for the paper's right-aligned answer stamp, so the
   bank's answer line must not reuse that name. */
.bank-split { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
.bank-transcript pre { white-space: pre-wrap; font-size: .82rem; line-height: 1.5;
  max-height: 32rem; overflow-y: auto; border: 1px solid var(--rule); padding: .75rem; }
.bank-correct { font-weight: 700; text-decoration: underline; }
.bank-answer { font-size: .85rem; margin-top: .3rem; }
.bank-alt { color: var(--stamp); }
.bank-image { max-width: 100%; height: auto; }
@media (max-width: 900px) { .bank-split { grid-template-columns: 1fr; } }
```

`--stamp` is an existing variable in `paper.css`; check it resolves to a muted
tone and swap for another existing variable if not. Do not introduce a new one.

- [ ] **Step 3: Run the view tests**

```bash
python manage.py test diagnostics.tests.test_listening_bank -v 2
```

Expected: PASS, all of them.

- [ ] **Step 4: Look at the page**

```bash
python manage.py runserver
```

Open `http://127.0.0.1:8000/test-generator/diagnostics/listening/` signed in as
a staff user. Confirm by eye:

- the first entry is clip 1 set 1, titled with three grades
- the correct option is visibly marked
- picture strips render
- the transcript panel shows clip 1's words and not clip 2's
- `?grade=9` reduces the list

- [ ] **Step 5: Commit**

```bash
git add templates/diagnostics/listening_bank.html static/
git commit -m "Render the listening bank page"
```

### Task 3.3: Link it from the navigation

**Files:**
- Modify: `templates/base.html:26-31`

- [ ] **Step 1: Add the link**

In `templates/base.html`, inside `<nav>`, immediately after the Diagnostics link:

```html
      {% if user.is_staff %}<a href="{% url 'diagnostics:listening_bank' %}"{% block nav_listening %}{% endblock %}>Listening bank</a>{% endif %}
```

Gated on `is_staff` so the nav does not offer a link that 404s.

- [ ] **Step 2: Confirm it appears for staff and not for a teacher**

```bash
python manage.py test diagnostics.tests.test_listening_bank -v 2
```

Then append this test to `ListeningBankViewTests` and re-run:

```python
    def test_the_nav_link_shows_for_staff_only(self):
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(self.url), "Listening bank")

        self.client.force_login(self.teacher)
        index = self.client.get(reverse("diagnostics:paper_index"))
        self.assertNotContains(index, "Listening bank")
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add templates/base.html diagnostics/tests/test_listening_bank.py
git commit -m "Link the listening bank from the navigation"
```

---

## Part 4: Finish

### Task 4.1: Document the command

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add it to the Commands section**

In `README.md`, under `## Commands` / `### Content`, add:

```markdown
Import the clip transcripts into the database, so the listening bank page can
show each recording's words beside its questions:

```bash
python manage.py import_transcripts
```

Idempotent — re-running overwrites every clip's transcript from
`media/diagnostics/audio/transcripts-full.md`. It never touches questions.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "Document import_transcripts"
```

### Task 4.2: Full suite and deploy notes

- [ ] **Step 1: Run the full suite**

```bash
python manage.py test
```

Expected: 923 + roughly 25 new tests, 0 failures.

- [ ] **Step 2: Confirm no model drift**

```bash
python manage.py makemigrations --check --dry-run
```

Expected: `No changes detected`.

- [ ] **Step 3: Record the deploy steps in the commit**

This change needs a migration and a command run on the server. Do **not** run
them from here — hand these to whoever owns the deploy:

```bash
git pull
docker compose up -d --build      # required: the command lives in the image
docker compose exec testgen python manage.py migrate
docker compose exec testgen python manage.py import_transcripts
```

The rebuild is not optional — see the deployment note in `README.md`. The
markdown itself is under `media/`, which is bind-mounted and already current,
but the command that reads it is not. **No paper rebuild**: nothing here touches
`Paper`, allocation or question content.

- [ ] **Step 4: Final commit**

```bash
git commit --allow-empty -m "Listening bank complete: migration 0018 and import_transcripts needed on deploy"
```

---

## Self-review

**Spec coverage**

| Spec section | Task |
|---|---|
| §2 one list + grade tabs | 3.1 (filter), 3.2 (tabs) |
| §2 staff only, 404 | 3.1 |
| §2 titles from Paper rows | 2.1 |
| §3 page structure, answers, images | 3.2 |
| §3 key balance panel | 2.2, 3.2 |
| §4 transcript field, whole not per-item | 1.1 |
| §4 idempotent import | 1.2 |
| §5 all eleven files | 1.1–4.1 |
| §6 non-staff 404 | 3.1 |
| §6 missing transcript panel | 3.2 |
| §6 unallocated set | 2.1 (`usage_title([])`) |
| §6 missing file `CommandError` | 1.2 |
| §6 unknown `?grade=` | 3.1 |
| §7 all seven test groups | 1.1–3.3 |
| §8 deploy steps | 4.2 |

**Placeholders:** none. Every code step carries its code; every command carries
its expected output.

**Type consistency:** `set_usage()` returns `{set_id: [(grade, group)]}` and is
consumed that way in 3.1. `usage_title(pairs)` takes that same list and is called
with `entry["pairs"]`. `key_balance(queryset)` takes a `ListeningQuestion`
queryset in both 2.2 and 3.1. Template keys `question_set`, `clip`, `pairs`,
`title`, `questions` are built in 3.1 and read in 3.2.

**Known soft spots for the implementer**

- `static/css/paper.css` is shared with `paper_detail.html` and
  `assembly/preview.html`. Every new rule is therefore `bank-` prefixed. This
  matters: `.qans` is already defined there (line 166) for the printed paper's
  right-aligned answer stamp, so an unprefixed answer-line rule would silently
  restyle the paper preview. Verified during plan self-review; `.bank-correct`,
  `.bank-answer`, `.bank-alt` and `.bank-image` are all unused today.
- `test_a_set_no_paper_uses_reports_empty` skips when every set is allocated,
  which is the current state (40 of 40 are in use). It is there to pin the
  behaviour if the bank ever grows a clip no paper uses.
- The picture-clip questions carry an `image` but an empty `options` list, so
  `option_rows` returns `[]` and only the image and the answer line render for
  them. That is correct — the options are the A/B/C panels inside the image —
  but it means the `bank-correct` highlight does nothing on picture clips. The
  answer line beneath carries the letter, which is what a reviewer reads.
