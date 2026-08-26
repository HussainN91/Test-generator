# STEP Platform Spine — Implementation Plan (Slice 1, backend)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend spine of the STEP Platform — geography, an adaptively-imported educator roster, configurable identity matching, a data-driven obligation engine, submissions with evidence and revisions, a review loop, and analytics aggregates — as a new `step` Django app inside the existing project.

**Architecture:** A new `step` app, fully decoupled from `content`, `bank`, `assembly` and `diagnostics` (no cross-app imports in either direction — see spec §9). Geography is seeded from a repository fixture; people are imported from a spreadsheet whose columns are unknown, via a propose-then-confirm mapping with an alias-learning queue. Obligation types are database rows, not code, so new verticals are configuration. Status is stored; urgency and all dashboard figures are derived at query time.

**Tech Stack:** Django 6.1, Python 3.14, `openpyxl` (already a dependency, used by `diagnostics`), SQLite in development with the engine made env-configurable for a later Postgres cutover.

**Spec:** `docs/superpowers/specs/2026-08-26-step-platform-spine-design.md`

---

## Scope of this plan

This plan covers the **backend only**: models, import pipeline, identity, obligation engine, submissions, review, analytics functions, and the Django admin.

**Not in this plan, deliberately:** the teacher dashboard, the administrator screens, and any HTML/CSS. Those are specified in spec §7 (design system and interaction model) and require the `frontend-design` skill plus human review of the visual result. They get their own plan. Everything here is verifiable by the test suite alone, which is what makes it safe to execute unattended.

**One documented deviation from the spec.** Spec §8 says slice 1 moves to Postgres. This plan instead makes `DATABASES` env-configurable with SQLite as the default (Task 20). Cutting over unattended on a machine with no running Postgres would break the existing pre-STEP suite. The cutover becomes a deployment step, not a code step.

---

## Environment

- Work from `D:\Test generator`, on branch `step-platform-spine`.
- Interpreter: `.venv\Scripts\python.exe` — always this one.
- Run the **whole** suite, not just `step`: `.venv\Scripts\python.exe manage.py test -v 2`. The project had 327 passing tests before this plan started (an earlier draft of this plan and HANDOFF.md both said 312; that figure was already stale, so measure the baseline yourself before starting); that number must only ever go up.
- Faster iteration on one app: `.venv\Scripts\python.exe manage.py test step -v 2`
- A single test: `.venv\Scripts\python.exe manage.py test step.tests.test_geography.RegionTests.test_name -v 2`
- Commit after every task. Never use `--no-verify`.

**Codebase conventions to follow** (from `diagnostics`, which is the closest analogue):

- Tests are `django.test.TestCase`, **not pytest**. No fixtures-as-arguments, no `assert` bare statements — use `self.assertEqual` and friends.
- Models live in a `models/` package re-exported from `models/__init__.py`.
- Module docstrings explain **why** the module exists, not what it does.
- Management commands live in `<app>/management/commands/`.

---

## File structure

Created by this plan:

| File | Responsibility |
|---|---|
| `step/__init__.py`, `step/apps.py` | App registration |
| `step/models/__init__.py` | Re-exports every model |
| `step/models/geography.py` | `Region`, `District` — seeded reference data |
| `step/models/roster.py` | `School`, `Educator`, `RosterImport`, `AliasMapping`, `PendingSignup` |
| `step/models/obligations.py` | `AcademicYear`, `Term`, `ObligationType`, `Obligation` |
| `step/models/submissions.py` | `Submission`, `Evidence` |
| `step/constants.py` | Status values, categories, cadences, evidence specs, role names |
| `step/identity.py` | The single resolver used by both import and signup |
| `step/roster/mapping.py` | Header→field proposal (pure functions) |
| `step/roster/geo.py` | Region/district string resolution + alias learning |
| `step/roster/importer.py` | Idempotent spreadsheet import |
| `step/scheduling.py` | Period arithmetic and due-date rules (pure functions) |
| `step/generation.py` | Obligation instance generation |
| `step/urgency.py` | Derived urgency and teacher stat tiles |
| `step/workflow.py` | Submit, accept, return — the state transitions |
| `step/analytics.py` | The nine dashboard aggregates |
| `step/roles.py` | Group creation and role checks |
| `step/signup.py` | Claiming a roster row at signup; the pending queue |
| `step/fixtures/uz_geography.json` | The seeded administrative divisions |
| `step/management/commands/seed_geography.py` | Loads the fixture |
| `step/management/commands/seed_roles.py` | Creates the four groups |
| `step/management/commands/import_roster.py` | Runs the import |
| `step/management/commands/generate_obligations.py` | Materialises instances |
| `step/admin.py` | Every model browsable |
| `step/tests/test_*.py` | One test module per unit above |

Modified:

- `config/settings.py` — add `"step"` to `INSTALLED_APPS`, add `STEP_ROSTER_MATCH_KEYS`, make `DATABASES` env-configurable.

---

## Phase 1 — Foundation

### Task 1: Create the `step` app

**Files:**
- Create: `step/__init__.py`, `step/apps.py`, `step/models/__init__.py`, `step/migrations/__init__.py`, `step/tests/__init__.py`, `step/constants.py`
- Modify: `config/settings.py` (INSTALLED_APPS)
- Test: `step/tests/test_app.py`

- [ ] **Step 1: Write the failing test**

```python
# step/tests/test_app.py
"""The app must be installed before anything else can be tested.

This exists because a missing INSTALLED_APPS entry fails later with confusing
errors about missing tables rather than a missing app.
"""

from django.apps import apps
from django.test import TestCase

from step import constants


class AppRegistrationTests(TestCase):
    def test_step_app_is_installed(self):
        self.assertTrue(apps.is_installed("step"))

    def test_app_config_label(self):
        self.assertEqual(apps.get_app_config("step").label, "step")


class ConstantsTests(TestCase):
    def test_statuses_are_distinct(self):
        values = [v for v, _ in constants.OBLIGATION_STATUS_CHOICES]
        self.assertEqual(len(values), len(set(values)))

    def test_not_started_is_the_initial_status(self):
        self.assertEqual(constants.STATUS_NOT_STARTED, "not_started")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'step'`

- [ ] **Step 3: Create the app skeleton**

```python
# step/__init__.py
```
(empty file)

```python
# step/apps.py
"""App config for the STEP obligations platform.

STEP is decoupled from `content`, `bank`, `assembly` and `diagnostics` by
design (see the spine spec §9). Nothing here may import from those apps, and
nothing there may import from here, until the Assessments merge in slice 3.
"""

from django.apps import AppConfig


class StepConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "step"
    verbose_name = "STEP Platform"
```

```python
# step/models/__init__.py
```
(empty for now; re-exports are added as models arrive)

```python
# step/migrations/__init__.py
```
(empty)

```python
# step/tests/__init__.py
```
(empty)

```python
# step/constants.py
"""Vocabulary for the obligation engine.

These values are stored in the database and must not be renamed casually.
User-facing wording is deliberately NOT defined here — the spec (§7.0) forbids
showing this vocabulary to users, so display strings live in templates.
"""

# --- Obligation status (stored) -------------------------------------------
STATUS_NOT_STARTED = "not_started"
STATUS_SUBMITTED = "submitted"
STATUS_UNDER_REVIEW = "under_review"
STATUS_ACCEPTED = "accepted"
STATUS_RETURNED = "returned"

OBLIGATION_STATUS_CHOICES = [
    (STATUS_NOT_STARTED, "Not started"),
    (STATUS_SUBMITTED, "Submitted"),
    (STATUS_UNDER_REVIEW, "Under review"),
    (STATUS_ACCEPTED, "Accepted"),
    (STATUS_RETURNED, "Returned"),
]

#: Statuses that mean the teacher has nothing left to do.
SETTLED_STATUSES = {STATUS_ACCEPTED}

#: Statuses that mean the ball is in an administrator's court.
AWAITING_REVIEW_STATUSES = {STATUS_SUBMITTED, STATUS_UNDER_REVIEW}

# --- Categories (the sidebar groupings in the client mockup) --------------
CATEGORY_MONTHLY_REPORTING = "monthly_reporting"
CATEGORY_CPD_ONLINE = "cpd_online"
CATEGORY_CPD_OFFLINE = "cpd_offline"
CATEGORY_ECA = "eca"
CATEGORY_ASSESSMENTS = "assessments"
CATEGORY_OTHER = "other"

CATEGORY_CHOICES = [
    (CATEGORY_MONTHLY_REPORTING, "Monthly Reporting"),
    (CATEGORY_CPD_ONLINE, "CPD Online"),
    (CATEGORY_CPD_OFFLINE, "CPD Offline"),
    (CATEGORY_ECA, "ECA Programme"),
    (CATEGORY_ASSESSMENTS, "Assessments"),
    (CATEGORY_OTHER, "Other"),
]

# --- Cadence and period ---------------------------------------------------
CADENCE_MONTHLY = "monthly"
CADENCE_TERMLY = "termly"
CADENCE_ANNUAL = "annual"
CADENCE_ONCE = "once"

CADENCE_CHOICES = [
    (CADENCE_MONTHLY, "Every month"),
    (CADENCE_TERMLY, "Every term"),
    (CADENCE_ANNUAL, "Once a year"),
    (CADENCE_ONCE, "One off"),
]

PERIOD_MONTH = "month"
PERIOD_TERM = "term"
PERIOD_YEAR = "year"
PERIOD_ONCE = "once"

PERIOD_KIND_CHOICES = [
    (PERIOD_MONTH, "Month"),
    (PERIOD_TERM, "Term"),
    (PERIOD_YEAR, "Year"),
    (PERIOD_ONCE, "One off"),
]

CADENCE_TO_PERIOD_KIND = {
    CADENCE_MONTHLY: PERIOD_MONTH,
    CADENCE_TERMLY: PERIOD_TERM,
    CADENCE_ANNUAL: PERIOD_YEAR,
    CADENCE_ONCE: PERIOD_ONCE,
}

# --- Evidence requirements (spec §5.7) ------------------------------------
EVIDENCE_NONE = "none"
EVIDENCE_LINK = "link"
EVIDENCE_FILE = "file"
EVIDENCE_EITHER = "either"
EVIDENCE_BOTH = "both"

EVIDENCE_SPEC_CHOICES = [
    (EVIDENCE_NONE, "No attachment required"),
    (EVIDENCE_LINK, "At least one link"),
    (EVIDENCE_FILE, "At least one uploaded file"),
    (EVIDENCE_EITHER, "At least one link or file"),
    (EVIDENCE_BOTH, "At least one link and one file"),
]

EVIDENCE_LINK_KIND = "link"
EVIDENCE_FILE_KIND = "file"
EVIDENCE_KIND_CHOICES = [
    (EVIDENCE_LINK_KIND, "Link"),
    (EVIDENCE_FILE_KIND, "File"),
]

# --- Scope (spec §5.6: `all` is the only implementation in slice 1) -------
SCOPE_ALL = "all"
SCOPE_CHOICES = [(SCOPE_ALL, "Every active educator")]

# --- Roles ----------------------------------------------------------------
ROLE_EDUCATOR = "Educator"
ROLE_ADMIN = "Admin"
ROLE_PROGRAMME_ADMIN = "Programme Admin"
ROLE_SYSTEM_ADMIN = "System Admin"

ROLE_NAMES = [ROLE_EDUCATOR, ROLE_ADMIN, ROLE_PROGRAMME_ADMIN, ROLE_SYSTEM_ADMIN]

#: Roles that never accrue obligations (spec §5.6).
STAFF_ROLES = {ROLE_ADMIN, ROLE_PROGRAMME_ADMIN, ROLE_SYSTEM_ADMIN}

# --- Urgency (derived, never stored — spec §5.3) --------------------------
URGENCY_DONE = "done"
URGENCY_OVERDUE = "overdue"
URGENCY_DUE_TODAY = "due_today"
URGENCY_DUE_SOON = "due_soon"
URGENCY_SCHEDULED = "scheduled"

#: How many days ahead counts as "due soon" in the teacher's queue.
DUE_SOON_DAYS = 7
```

- [ ] **Step 4: Register the app**

In `config/settings.py`, add `"step",` to `INSTALLED_APPS` immediately after `"diagnostics",`:

```python
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "content",
    "bank",
    "assembly",
    "diagnostics",
    "step",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test step -v 2`
Expected: PASS — 4 tests OK

Then run the whole suite: `.venv\Scripts\python.exe manage.py test`
Expected: the pre-existing baseline plus 4 new tests, OK

- [ ] **Step 6: Commit**

```bash
git add step config/settings.py
git commit -m "Add the step app skeleton and obligation vocabulary"
```

---

### Task 2: Geography models and the seeded fixture

Region is the axis every admin chart pivots on. It is seeded from a repository fixture rather than created from spreadsheet text, so that spelling variants cannot silently fragment the rollups (spec §4.1).

**Files:**
- Create: `step/models/geography.py`, `step/fixtures/uz_geography.json`, `step/management/__init__.py`, `step/management/commands/__init__.py`, `step/management/commands/seed_geography.py`
- Modify: `step/models/__init__.py`
- Test: `step/tests/test_geography.py`

- [ ] **Step 1: Write the failing test**

```python
# step/tests/test_geography.py
"""Geography is reference data, not user data.

The seed command must be idempotent because it runs on every deployment, and
the fixture must carry all 14 top-level divisions even though the client's
mockup only shows the 11 that currently have teachers (spec §4.1).
"""

from io import StringIO

from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase

from step.models import District, Region


class RegionTests(TestCase):
    def test_region_code_is_unique(self):
        Region.objects.create(name="Samarkand", code="samarkand")
        with self.assertRaises(IntegrityError):
            Region.objects.create(name="Samarqand", code="samarkand")

    def test_str_is_the_name(self):
        region = Region.objects.create(name="Bukhara", code="bukhara")
        self.assertEqual(str(region), "Bukhara")


class DistrictTests(TestCase):
    def test_district_code_is_unique_within_a_region_only(self):
        a = Region.objects.create(name="Fergana", code="fergana")
        b = Region.objects.create(name="Andijan", code="andijan")
        District.objects.create(region=a, name="Centre", code="centre")
        # Same code under a different region is fine.
        District.objects.create(region=b, name="Centre", code="centre")
        with self.assertRaises(IntegrityError):
            District.objects.create(region=a, name="Centre again", code="centre")

    def test_str_includes_the_region(self):
        region = Region.objects.create(name="Jizzakh", code="jizzakh")
        district = District.objects.create(region=region, name="Zomin", code="zomin")
        self.assertEqual(str(district), "Zomin, Jizzakh")


class SeedGeographyTests(TestCase):
    def test_seeds_all_fourteen_top_level_divisions(self):
        call_command("seed_geography", stdout=StringIO())
        self.assertEqual(Region.objects.count(), 14)

    def test_tashkent_city_is_flagged_as_a_city(self):
        call_command("seed_geography", stdout=StringIO())
        self.assertTrue(Region.objects.get(code="tashkent-city").is_city)

    def test_tashkent_city_and_tashkent_region_are_separate(self):
        call_command("seed_geography", stdout=StringIO())
        self.assertTrue(Region.objects.filter(code="tashkent-city").exists())
        self.assertTrue(Region.objects.filter(code="tashkent-region").exists())

    def test_running_twice_does_not_duplicate(self):
        call_command("seed_geography", stdout=StringIO())
        call_command("seed_geography", stdout=StringIO())
        self.assertEqual(Region.objects.count(), 14)

    def test_every_region_has_at_least_one_district(self):
        call_command("seed_geography", stdout=StringIO())
        without = [r.name for r in Region.objects.all() if not r.districts.exists()]
        self.assertEqual(without, [], f"regions with no districts: {without}")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_geography -v 2`
Expected: FAIL — `ImportError: cannot import name 'District' from 'step.models'`

- [ ] **Step 3: Write the models**

```python
# step/models/geography.py
"""Uzbekistan's administrative divisions, seeded from a repository fixture.

Deliberately NOT derived from the client roster spreadsheet. Region is the axis
every administration chart pivots on, and free-text region names would produce
"Tashkent", "Toshkent" and "Tashkent city" as three separate regions with three
separate bars in the same chart. Seeding makes that failure impossible.
"""

from django.db import models


class Region(models.Model):
    """A viloyat, the Republic of Karakalpakstan, or Tashkent City."""

    name = models.CharField(max_length=100, unique=True)
    name_uz = models.CharField(max_length=100, blank=True)
    code = models.SlugField(max_length=32, unique=True)
    is_city = models.BooleanField(
        default=False,
        help_text="True for Tashkent City, which is a top-level division but not a viloyat.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class District(models.Model):
    """A tuman within a region."""

    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="districts")
    name = models.CharField(max_length=100)
    name_uz = models.CharField(max_length=100, blank=True)
    code = models.SlugField(max_length=48)

    class Meta:
        ordering = ["region__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["region", "code"], name="step_district_code_unique_per_region"),
        ]

    def __str__(self) -> str:
        return f"{self.name}, {self.region.name}"
```

```python
# step/models/__init__.py
"""Re-exports every STEP model so callers import from `step.models` directly."""

from step.models.geography import District, Region

__all__ = ["District", "Region"]
```

- [ ] **Step 4: Write the fixture**

Create `step/fixtures/uz_geography.json`. It is a plain JSON list (not a Django serialised fixture — the seed command reads it and upserts, so it stays readable and diffable). Include all 14 top-level divisions. Districts: include at minimum the ones listed below; adding the full district list later is a data change, not a code change.

```json
[
  {"code": "karakalpakstan", "name": "Republic of Karakalpakstan", "name_uz": "Qoraqalpogʻiston Respublikasi", "is_city": false,
   "districts": [{"code": "nukus", "name": "Nukus"}, {"code": "khodjeyli", "name": "Khodjeyli"}, {"code": "chimbay", "name": "Chimbay"}]},
  {"code": "andijan", "name": "Andijan", "name_uz": "Andijon", "is_city": false,
   "districts": [{"code": "andijan-city", "name": "Andijan City"}, {"code": "asaka", "name": "Asaka"}, {"code": "shahrixon", "name": "Shahrixon"}]},
  {"code": "bukhara", "name": "Bukhara", "name_uz": "Buxoro", "is_city": false,
   "districts": [{"code": "bukhara-city", "name": "Bukhara City"}, {"code": "gijduvan", "name": "Gijduvan"}, {"code": "kagan", "name": "Kagan"}]},
  {"code": "fergana", "name": "Fergana", "name_uz": "Fargʻona", "is_city": false,
   "districts": [{"code": "fergana-city", "name": "Fergana City"}, {"code": "kokand", "name": "Kokand"}, {"code": "margilan", "name": "Margilan"}]},
  {"code": "jizzakh", "name": "Jizzakh", "name_uz": "Jizzax", "is_city": false,
   "districts": [{"code": "jizzakh-city", "name": "Jizzakh City"}, {"code": "zomin", "name": "Zomin"}, {"code": "gallaorol", "name": "Gallaorol"}]},
  {"code": "kashkadarya", "name": "Kashkadarya", "name_uz": "Qashqadaryo", "is_city": false,
   "districts": [{"code": "karshi", "name": "Karshi"}, {"code": "shahrisabz", "name": "Shahrisabz"}, {"code": "kitab", "name": "Kitab"}]},
  {"code": "khorezm", "name": "Khorezm", "name_uz": "Xorazm", "is_city": false,
   "districts": [{"code": "urgench", "name": "Urgench"}, {"code": "khiva", "name": "Khiva"}, {"code": "hazorasp", "name": "Hazorasp"}]},
  {"code": "namangan", "name": "Namangan", "name_uz": "Namangan", "is_city": false,
   "districts": [{"code": "namangan-city", "name": "Namangan City"}, {"code": "chust", "name": "Chust"}, {"code": "pop", "name": "Pop"}]},
  {"code": "navoiy", "name": "Navoiy", "name_uz": "Navoiy", "is_city": false,
   "districts": [{"code": "navoiy-city", "name": "Navoiy City"}, {"code": "zarafshan", "name": "Zarafshan"}, {"code": "karmana", "name": "Karmana"}]},
  {"code": "samarkand", "name": "Samarkand", "name_uz": "Samarqand", "is_city": false,
   "districts": [{"code": "samarkand-city", "name": "Samarkand City"}, {"code": "urgut", "name": "Urgut"}, {"code": "kattakurgan", "name": "Kattakurgan"}]},
  {"code": "sirdaryo", "name": "Syrdarya", "name_uz": "Sirdaryo", "is_city": false,
   "districts": [{"code": "gulistan", "name": "Gulistan"}, {"code": "yangiyer", "name": "Yangiyer"}, {"code": "shirin", "name": "Shirin"}]},
  {"code": "surkhandarya", "name": "Surkhandarya", "name_uz": "Surxondaryo", "is_city": false,
   "districts": [{"code": "termez", "name": "Termez"}, {"code": "denau", "name": "Denau"}, {"code": "sherabad", "name": "Sherabad"}]},
  {"code": "tashkent-region", "name": "Tashkent Region", "name_uz": "Toshkent viloyati", "is_city": false,
   "districts": [{"code": "nurafshon", "name": "Nurafshon"}, {"code": "angren", "name": "Angren"}, {"code": "chirchiq", "name": "Chirchiq"}, {"code": "olmaliq", "name": "Olmaliq"}]},
  {"code": "tashkent-city", "name": "Tashkent City", "name_uz": "Toshkent shahri", "is_city": true,
   "districts": [{"code": "chilonzor", "name": "Chilonzor"}, {"code": "yunusobod", "name": "Yunusobod"}, {"code": "mirzo-ulugbek", "name": "Mirzo Ulugbek"}, {"code": "sergeli", "name": "Sergeli"}, {"code": "yakkasaroy", "name": "Yakkasaroy"}]}
]
```

- [ ] **Step 5: Write the seed command**

```python
# step/management/__init__.py
```
(empty)

```python
# step/management/commands/__init__.py
```
(empty)

```python
# step/management/commands/seed_geography.py
"""Loads Uzbekistan's administrative divisions.

Idempotent by design: it runs on every deployment, and re-running must never
duplicate a region or orphan a district. Upserts on `code`, which is why the
fixture carries stable codes rather than relying on names.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from step.models import District, Region

FIXTURE = Path(__file__).resolve().parent.parent.parent / "fixtures" / "uz_geography.json"


class Command(BaseCommand):
    help = "Seed or refresh Uzbekistan's regions and districts. Safe to re-run."

    @transaction.atomic
    def handle(self, *args, **options):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

        regions_touched = districts_touched = 0
        for entry in payload:
            region, _ = Region.objects.update_or_create(
                code=entry["code"],
                defaults={
                    "name": entry["name"],
                    "name_uz": entry.get("name_uz", ""),
                    "is_city": entry.get("is_city", False),
                },
            )
            regions_touched += 1
            for d in entry.get("districts", []):
                District.objects.update_or_create(
                    region=region,
                    code=d["code"],
                    defaults={"name": d["name"], "name_uz": d.get("name_uz", "")},
                )
                districts_touched += 1

        self.stdout.write(
            self.style.SUCCESS(f"Seeded {regions_touched} regions and {districts_touched} districts.")
        )
```

- [ ] **Step 6: Make and run migrations**

Run: `.venv\Scripts\python.exe manage.py makemigrations step`
Expected: `Migrations for 'step': step/migrations/0001_initial.py` creating `Region` and `District`

Run: `.venv\Scripts\python.exe manage.py migrate`
Expected: applies `step.0001_initial`

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_geography -v 2`
Expected: PASS — 9 tests OK

- [ ] **Step 8: Commit**

```bash
git add step
git commit -m "Add seeded Uzbek geography with an idempotent seed command"
```

---

### Task 3: Roster models

**Files:**
- Create: `step/models/roster.py`
- Modify: `step/models/__init__.py`
- Test: `step/tests/test_roster_models.py`

- [ ] **Step 1: Write the failing test**

```python
# step/tests/test_roster_models.py
"""The roster must survive a spreadsheet whose columns nobody has seen.

Every field except an identity key and a geographic anchor is optional, and
unrecognised columns are preserved in `source_fields` rather than dropped
(spec §4.2). School is nullable because the sheet may not carry usable school
names.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from step.models import District, Educator, PendingSignup, Region, School


class EducatorTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.district = District.objects.create(region=self.region, name="Urgut", code="urgut")

    def test_an_educator_needs_only_a_name_and_a_region(self):
        educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.assertIsNone(educator.school)
        self.assertIsNone(educator.user)
        self.assertEqual(educator.email, "")
        self.assertEqual(educator.source_fields, {})

    def test_unrecognised_columns_are_preserved(self):
        educator = Educator.objects.create(
            full_name="Maria Santos",
            region=self.region,
            source_fields={"Contract Type": "Two year", "Intake": "2025-A"},
        )
        educator.refresh_from_db()
        self.assertEqual(educator.source_fields["Intake"], "2025-A")

    def test_is_active_defaults_true_and_missing_flag_defaults_false(self):
        educator = Educator.objects.create(full_name="A B", region=self.region)
        self.assertTrue(educator.is_active)
        self.assertFalse(educator.missing_from_last_import)

    def test_deleting_a_user_does_not_delete_the_educator(self):
        user = get_user_model().objects.create_user("maria", password="x")
        educator = Educator.objects.create(full_name="Maria", region=self.region, user=user)
        user.delete()
        educator.refresh_from_db()
        self.assertIsNone(educator.user)

    def test_str_is_the_name(self):
        educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.assertEqual(str(educator), "Maria Santos")


class SchoolTests(TestCase):
    def test_school_belongs_to_a_district(self):
        region = Region.objects.create(name="Fergana", code="fergana")
        district = District.objects.create(region=region, name="Kokand", code="kokand")
        school = School.objects.create(name="International School 4", district=district)
        self.assertEqual(school.district.region, region)
        self.assertEqual(str(school), "International School 4")


class PendingSignupTests(TestCase):
    def test_a_signup_that_matches_nobody_is_recorded_for_an_admin(self):
        pending = PendingSignup.objects.create(
            full_name="Unknown Person", email="nobody@example.com"
        )
        self.assertFalse(pending.resolved)
        self.assertIn("Unknown Person", str(pending))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_roster_models -v 2`
Expected: FAIL — `ImportError: cannot import name 'Educator' from 'step.models'`

- [ ] **Step 3: Write the models**

```python
# step/models/roster.py
"""Educators, their schools, and the machinery for importing them.

The client's roster spreadsheet exists but its columns are unknown at design
time and may change between terms (spec §4.2). Everything here is therefore
built to tolerate an unfamiliar sheet: two required fields, every other column
preserved verbatim in `source_fields`, and no destructive updates — a person
who vanishes from the sheet is flagged, never deleted.
"""

from django.conf import settings
from django.db import models

from step.models.geography import District, Region


class School(models.Model):
    name = models.CharField(max_length=200)
    district = models.ForeignKey(District, on_delete=models.PROTECT, related_name="schools")
    external_id = models.CharField(
        max_length=64, blank=True, help_text="The client's own identifier, if the sheet carries one."
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Educator(models.Model):
    """An international educator. The only role that accrues obligations."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="educator",
        help_text="Set when the person signs up and is matched to this roster row.",
    )
    full_name = models.CharField(max_length=200)

    # Identity candidates. All optional: which one is authoritative is a
    # deployment decision (settings.STEP_ROSTER_MATCH_KEYS), not a schema one.
    email = models.EmailField(blank=True)
    passport_no = models.CharField(max_length=64, blank=True)
    pinfl = models.CharField(max_length=32, blank=True)

    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="educators")
    district = models.ForeignKey(
        District, null=True, blank=True, on_delete=models.SET_NULL, related_name="educators"
    )
    school = models.ForeignKey(
        School, null=True, blank=True, on_delete=models.SET_NULL, related_name="educators"
    )

    is_active = models.BooleanField(default=True)
    missing_from_last_import = models.BooleanField(
        default=False,
        help_text="Set when a re-import no longer finds this person. Never auto-deleted.",
    )
    source_fields = models.JSONField(
        default=dict,
        blank=True,
        help_text="Every spreadsheet column that did not map to a known field, kept verbatim.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]
        indexes = [
            models.Index(fields=["region", "is_active"]),
            models.Index(fields=["email"]),
        ]

    def __str__(self) -> str:
        return self.full_name


class RosterImport(models.Model):
    """One spreadsheet upload, with the column mapping that was confirmed for it."""

    file = models.FileField(upload_to="step/roster/")
    imported_at = models.DateTimeField(auto_now_add=True)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    header_row = models.PositiveIntegerField(default=1)
    mapping = models.JSONField(
        default=dict, blank=True, help_text="Spreadsheet header -> canonical field name."
    )
    row_count = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    unresolved_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-imported_at"]

    def __str__(self) -> str:
        return f"Roster import {self.pk} ({self.row_count} rows)"


class AliasMapping(models.Model):
    """A remembered decision about what a messy source string actually meant.

    Exists so a human maps "Tash. city" to Tashkent City exactly once. Without
    it, every import repeats the same manual work.
    """

    KIND_REGION = "region"
    KIND_DISTRICT = "district"
    KIND_SCHOOL = "school"
    KIND_CHOICES = [(KIND_REGION, "Region"), (KIND_DISTRICT, "District"), (KIND_SCHOOL, "School")]

    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    raw_value = models.CharField(max_length=200)
    normalised = models.CharField(max_length=200, db_index=True)
    region = models.ForeignKey(Region, null=True, blank=True, on_delete=models.CASCADE)
    district = models.ForeignKey(District, null=True, blank=True, on_delete=models.CASCADE)
    school = models.ForeignKey(School, null=True, blank=True, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["kind", "normalised"], name="step_alias_unique_per_kind"),
        ]

    def __str__(self) -> str:
        return f"{self.kind}: {self.raw_value}"


class UnresolvedRow(models.Model):
    """A spreadsheet row the importer could not place. Reviewed by hand."""

    roster_import = models.ForeignKey(
        RosterImport, on_delete=models.CASCADE, related_name="unresolved_rows"
    )
    row_number = models.PositiveIntegerField()
    reason = models.CharField(max_length=200)
    payload = models.JSONField(default=dict)
    resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ["roster_import", "row_number"]

    def __str__(self) -> str:
        return f"Row {self.row_number}: {self.reason}"


class PendingSignup(models.Model):
    """Someone signed up but matched no roster row. An administrator decides.

    The spreadsheet is the gatekeeper (spec §4.3), so an unmatched signup is
    held here rather than silently creating an educator.
    """

    full_name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    passport_no = models.CharField(max_length=64, blank=True)
    pinfl = models.CharField(max_length=32, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self) -> str:
        return f"Pending signup: {self.full_name}"
```

- [ ] **Step 4: Update the model re-exports**

```python
# step/models/__init__.py
"""Re-exports every STEP model so callers import from `step.models` directly."""

from step.models.geography import District, Region
from step.models.roster import (
    AliasMapping,
    Educator,
    PendingSignup,
    RosterImport,
    School,
    UnresolvedRow,
)

__all__ = [
    "AliasMapping",
    "District",
    "Educator",
    "PendingSignup",
    "Region",
    "RosterImport",
    "School",
    "UnresolvedRow",
]
```

- [ ] **Step 5: Make and run migrations**

Run: `.venv\Scripts\python.exe manage.py makemigrations step`
Expected: `step/migrations/0002_*.py` creating the six roster models

Run: `.venv\Scripts\python.exe manage.py migrate`

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_roster_models -v 2`
Expected: PASS — 8 tests OK

- [ ] **Step 7: Commit**

```bash
git add step
git commit -m "Add roster models with adaptive source-field preservation"
```

---

### Task 4: Roles

**Files:**
- Create: `step/roles.py`, `step/management/commands/seed_roles.py`
- Test: `step/tests/test_roles.py`

- [ ] **Step 1: Write the failing test**

```python
# step/tests/test_roles.py
"""Roles decide who accrues obligations, so getting them wrong creates
phantom work for staff (spec §5.6). Django Groups are used so permission
checks stay conventional.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase

from step import constants, roles


class SeedRolesTests(TestCase):
    def test_creates_the_four_groups(self):
        call_command("seed_roles", stdout=StringIO())
        self.assertEqual(
            sorted(Group.objects.values_list("name", flat=True)),
            sorted(constants.ROLE_NAMES),
        )

    def test_running_twice_does_not_duplicate(self):
        call_command("seed_roles", stdout=StringIO())
        call_command("seed_roles", stdout=StringIO())
        self.assertEqual(Group.objects.count(), 4)


class RoleHelperTests(TestCase):
    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        self.user = get_user_model().objects.create_user("maria", password="x")

    def test_a_user_with_no_group_has_no_role(self):
        self.assertEqual(roles.role_names(self.user), set())
        self.assertFalse(roles.is_educator(self.user))
        self.assertFalse(roles.is_staff_role(self.user))

    def test_assigning_a_role_is_reflected(self):
        roles.assign(self.user, constants.ROLE_EDUCATOR)
        self.assertTrue(roles.is_educator(self.user))
        self.assertFalse(roles.is_staff_role(self.user))

    def test_staff_roles_are_recognised(self):
        roles.assign(self.user, constants.ROLE_PROGRAMME_ADMIN)
        self.assertTrue(roles.is_staff_role(self.user))
        self.assertFalse(roles.is_educator(self.user))

    def test_assigning_an_unknown_role_raises(self):
        with self.assertRaises(ValueError):
            roles.assign(self.user, "Wizard")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_roles -v 2`
Expected: FAIL — `ImportError: cannot import name 'roles' from 'step'`

- [ ] **Step 3: Write the helper and the command**

```python
# step/roles.py
"""Role membership, expressed as Django Groups.

Groups rather than a `role` column because permission checks, the admin, and
`user.has_perm` all already understand groups. A column would mean reinventing
that plumbing.
"""

from django.contrib.auth.models import Group

from step import constants


def role_names(user) -> set[str]:
    if not user or not user.is_authenticated:
        return set()
    return set(user.groups.values_list("name", flat=True)) & set(constants.ROLE_NAMES)


def assign(user, role_name: str) -> None:
    if role_name not in constants.ROLE_NAMES:
        raise ValueError(f"Unknown role: {role_name!r}. Known roles: {constants.ROLE_NAMES}")
    user.groups.add(Group.objects.get(name=role_name))


def is_educator(user) -> bool:
    return constants.ROLE_EDUCATOR in role_names(user)


def is_staff_role(user) -> bool:
    return bool(role_names(user) & constants.STAFF_ROLES)
```

```python
# step/management/commands/seed_roles.py
"""Creates the four STEP role groups. Idempotent; runs on every deployment."""

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from step import constants


class Command(BaseCommand):
    help = "Create the STEP role groups. Safe to re-run."

    def handle(self, *args, **options):
        for name in constants.ROLE_NAMES:
            Group.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS(f"Ensured {len(constants.ROLE_NAMES)} role groups."))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_roles -v 2`
Expected: PASS — 6 tests OK

- [ ] **Step 5: Commit**

```bash
git add step
git commit -m "Add STEP roles as Django groups with a seed command"
```

---

## Phase 2 — Roster import and identity

### Task 5: Header mapping proposal

Pure functions, no database. This is what lets the importer face a sheet nobody has seen.

**Files:**
- Create: `step/roster/__init__.py`, `step/roster/mapping.py`
- Test: `step/tests/test_mapping.py`

- [ ] **Step 1: Write the failing test**

```python
# step/tests/test_mapping.py
"""The importer must guess what a column means without being told.

These are the header spellings actually seen in the wild for this kind of
sheet. The proposal is always shown for confirmation before anything is
written (spec §4.2), so a wrong guess is cheap; a missing guess is not.
"""

from django.test import SimpleTestCase

from step.roster import mapping


class NormaliseTests(SimpleTestCase):
    def test_case_punctuation_and_spacing_are_ignored(self):
        self.assertEqual(mapping.normalise("  Full  Name! "), "fullname")
        self.assertEqual(mapping.normalise("E-mail"), "email")
        self.assertEqual(mapping.normalise("PINFL / ПИНФЛ"), "pinflпинфл")


class ProposeMappingTests(SimpleTestCase):
    def test_recognises_common_name_headers(self):
        for header in ["Full Name", "Teacher Name", "Name", "FULL NAME"]:
            proposed = mapping.propose_mapping([header])
            self.assertEqual(proposed[header], "full_name", f"failed on {header!r}")

    def test_recognises_email_headers(self):
        for header in ["Email", "E-mail", "Email Address", "Gmail"]:
            self.assertEqual(mapping.propose_mapping([header])[header], "email")

    def test_recognises_region_headers(self):
        for header in ["Region", "Viloyat", "Province", "Oblast"]:
            self.assertEqual(mapping.propose_mapping([header])[header], "region")

    def test_recognises_district_school_passport_and_pinfl(self):
        proposed = mapping.propose_mapping(["District", "School", "Passport Number", "PINFL"])
        self.assertEqual(proposed["District"], "district")
        self.assertEqual(proposed["School"], "school")
        self.assertEqual(proposed["Passport Number"], "passport_no")
        self.assertEqual(proposed["PINFL"], "pinfl")

    def test_unknown_headers_map_to_none(self):
        proposed = mapping.propose_mapping(["Contract Type", "Intake Cohort"])
        self.assertIsNone(proposed["Contract Type"])
        self.assertIsNone(proposed["Intake Cohort"])

    def test_a_header_is_never_mapped_to_two_fields(self):
        proposed = mapping.propose_mapping(["Name", "Full Name"])
        mapped = [v for v in proposed.values() if v is not None]
        self.assertEqual(len(mapped), len(set(mapped)), f"duplicate targets in {proposed}")

    def test_blank_headers_are_ignored(self):
        proposed = mapping.propose_mapping(["Name", "", None, "  "])
        self.assertEqual(list(proposed), ["Name"])


class SufficiencyTests(SimpleTestCase):
    def test_a_mapping_with_an_identity_key_and_a_region_is_sufficient(self):
        ok, missing = mapping.check_sufficiency({"Email": "email", "Region": "region"})
        self.assertTrue(ok)
        self.assertEqual(missing, [])

    def test_a_mapping_with_no_geographic_anchor_is_insufficient(self):
        ok, missing = mapping.check_sufficiency({"Email": "email"})
        self.assertFalse(ok)
        self.assertIn("a geographic anchor (region, district or school)", missing)

    def test_a_mapping_with_no_identity_key_is_insufficient(self):
        ok, missing = mapping.check_sufficiency({"Region": "region"})
        self.assertFalse(ok)
        self.assertIn("an identity key (email, passport_no or pinfl)", missing)

    def test_district_alone_satisfies_the_geographic_anchor(self):
        ok, _ = mapping.check_sufficiency({"PINFL": "pinfl", "District": "district"})
        self.assertTrue(ok)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_mapping -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'step.roster'`

- [ ] **Step 3: Write the mapping module**

```python
# step/roster/__init__.py
```
(empty)

```python
# step/roster/mapping.py
"""Guessing what a spreadsheet column means.

The client's roster sheet exists but its headers are unknown and will change
between terms. Rather than hardcode column positions, the importer proposes a
mapping and a human confirms it before any row is written (spec §4.2).

Everything here is a pure function: no database, no Django models. That makes
the guessing logic cheap to test against real header spellings as they turn up.
"""

import re

#: Canonical field name -> the normalised header spellings that mean it.
#: Ordered most-specific first so "email address" wins over a bare "address".
ALIASES: dict[str, tuple[str, ...]] = {
    "full_name": ("fullname", "teachername", "educatorname", "name", "fio", "surnameandname"),
    "email": ("emailaddress", "email", "email", "gmail", "mail"),
    "passport_no": ("passportnumber", "passportno", "passport", "passportseries"),
    "pinfl": ("pinfl", "pnfl", "jshshir", "personalnumber"),
    "region": ("region", "viloyat", "province", "oblast", "viloyati"),
    "district": ("district", "tuman", "tumani", "rayon"),
    "school": ("schoolname", "school", "maktab", "institution", "workplace"),
}

#: One of these must be mapped for a row to be identifiable.
IDENTITY_FIELDS = ("email", "passport_no", "pinfl")

#: One of these must be mapped for a row to be placeable on the map.
GEOGRAPHIC_FIELDS = ("region", "district", "school")


def normalise(value) -> str:
    """Lowercase and strip everything that is not a letter or digit.

    Deliberately keeps non-ASCII letters so Cyrillic and Uzbek Latin headers
    survive; only punctuation and spacing are discarded.
    """
    if value is None:
        return ""
    return re.sub(r"[^\w]", "", str(value), flags=re.UNICODE).lower().replace("_", "")


def propose_mapping(headers) -> dict:
    """Return {original header: canonical field or None}.

    Blank headers are skipped entirely. A canonical field is claimed by at most
    one header — the first that matches — because two columns mapping to
    `email` would silently overwrite each other during import.
    """
    proposed: dict = {}
    claimed: set[str] = set()

    for header in headers:
        if header is None or not str(header).strip():
            continue
        key = normalise(header)
        match = None
        for field, aliases in ALIASES.items():
            if field in claimed:
                continue
            if key in aliases:
                match = field
                break
        if match:
            claimed.add(match)
        proposed[header] = match

    return proposed


def check_sufficiency(mapping_dict) -> tuple[bool, list[str]]:
    """Is this mapping enough to import from?

    Enforces *minimum sufficiency* rather than a fixed column list, matching
    the convention already used by the diagnostics import commands.
    """
    targets = {v for v in mapping_dict.values() if v}
    missing = []
    if not targets & set(IDENTITY_FIELDS):
        missing.append("an identity key (email, passport_no or pinfl)")
    if not targets & set(GEOGRAPHIC_FIELDS):
        missing.append("a geographic anchor (region, district or school)")
    return (not missing), missing
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_mapping -v 2`
Expected: PASS — 12 tests OK

- [ ] **Step 5: Commit**

```bash
git add step
git commit -m "Add header mapping proposal with minimum-sufficiency checking"
```

---

### Task 6: Geographic resolution with alias learning

**Files:**
- Create: `step/roster/geo.py`
- Test: `step/tests/test_geo_resolution.py`

- [ ] **Step 1: Write the failing test**

```python
# step/tests/test_geo_resolution.py
"""Messy region strings must resolve to seeded regions, and a human decision
must only ever be needed once (spec §4.2).
"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from step.models import AliasMapping, District, Region
from step.roster import geo


class ResolveRegionTests(TestCase):
    def setUp(self):
        call_command("seed_geography", stdout=StringIO())

    def test_exact_name_resolves(self):
        self.assertEqual(geo.resolve_region("Samarkand").code, "samarkand")

    def test_case_and_spacing_are_ignored(self):
        self.assertEqual(geo.resolve_region("  samarkand ").code, "samarkand")

    def test_uzbek_spelling_resolves(self):
        self.assertEqual(geo.resolve_region("Samarqand").code, "samarkand")

    def test_tashkent_city_and_region_do_not_collide(self):
        self.assertEqual(geo.resolve_region("Tashkent City").code, "tashkent-city")
        self.assertEqual(geo.resolve_region("Tashkent Region").code, "tashkent-region")

    def test_an_unknown_string_returns_none_rather_than_guessing(self):
        self.assertIsNone(geo.resolve_region("Atlantis"))

    def test_a_bare_tashkent_is_ambiguous_and_returns_none(self):
        """Refusing to guess is the point: guessing wrong silently splits a chart."""
        self.assertIsNone(geo.resolve_region("Tashkent"))

    def test_a_learned_alias_resolves_afterwards(self):
        self.assertIsNone(geo.resolve_region("Tash. city"))
        geo.learn_region_alias("Tash. city", Region.objects.get(code="tashkent-city"))
        self.assertEqual(geo.resolve_region("Tash. city").code, "tashkent-city")

    def test_learning_the_same_alias_twice_is_harmless(self):
        region = Region.objects.get(code="samarkand")
        geo.learn_region_alias("Smrkd", region)
        geo.learn_region_alias("Smrkd", region)
        self.assertEqual(AliasMapping.objects.filter(normalised="smrkd").count(), 1)


class ResolveDistrictTests(TestCase):
    def setUp(self):
        call_command("seed_geography", stdout=StringIO())

    def test_district_resolves_within_its_region(self):
        region = Region.objects.get(code="fergana")
        self.assertEqual(geo.resolve_district("Kokand", region).code, "kokand")

    def test_district_from_the_wrong_region_does_not_resolve(self):
        region = Region.objects.get(code="bukhara")
        self.assertIsNone(geo.resolve_district("Kokand", region))

    def test_district_resolves_without_a_region_when_unambiguous(self):
        district = geo.resolve_district("Kokand", None)
        self.assertIsNotNone(district)
        self.assertEqual(district.region.code, "fergana")

    def test_an_ambiguous_district_without_a_region_returns_none(self):
        region = Region.objects.get(code="bukhara")
        District.objects.create(region=region, name="Kokand", code="kokand-dup")
        self.assertIsNone(geo.resolve_district("Kokand", None))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_geo_resolution -v 2`
Expected: FAIL — `ImportError: cannot import name 'geo' from 'step.roster'`

- [ ] **Step 3: Write the resolver**

```python
# step/roster/geo.py
"""Turning spreadsheet place-names into seeded Region and District rows.

The governing rule is **refuse to guess**. A wrong region silently splits a bar
in the administration chart and nobody notices; an unresolved row lands in a
queue where somebody fixes it once and the decision is remembered. Ambiguity is
therefore always resolved to None, never to a best effort.
"""

from step.models import AliasMapping, District, Region
from step.roster.mapping import normalise


def _alias(kind: str, raw: str):
    return AliasMapping.objects.filter(kind=kind, normalised=normalise(raw)).first()


def resolve_region(raw):
    """Return a Region, or None if unknown or ambiguous."""
    if not raw or not str(raw).strip():
        return None
    key = normalise(raw)

    learned = _alias(AliasMapping.KIND_REGION, raw)
    if learned and learned.region:
        return learned.region

    for region in Region.objects.all():
        if key in {normalise(region.name), normalise(region.name_uz), normalise(region.code)}:
            return region
    return None


def resolve_district(raw, region=None):
    """Return a District, or None if unknown or ambiguous.

    When `region` is given the search is confined to it. When it is not, a name
    matching districts in two different regions is ambiguous and returns None.
    """
    if not raw or not str(raw).strip():
        return None
    key = normalise(raw)

    learned = _alias(AliasMapping.KIND_DISTRICT, raw)
    if learned and learned.district:
        if region is None or learned.district.region_id == region.pk:
            return learned.district

    queryset = District.objects.select_related("region")
    if region is not None:
        queryset = queryset.filter(region=region)

    matches = [
        d for d in queryset
        if key in {normalise(d.name), normalise(d.name_uz), normalise(d.code)}
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def learn_region_alias(raw: str, region: Region) -> AliasMapping:
    alias, _ = AliasMapping.objects.update_or_create(
        kind=AliasMapping.KIND_REGION,
        normalised=normalise(raw),
        defaults={"raw_value": str(raw), "region": region},
    )
    return alias


def learn_district_alias(raw: str, district: District) -> AliasMapping:
    alias, _ = AliasMapping.objects.update_or_create(
        kind=AliasMapping.KIND_DISTRICT,
        normalised=normalise(raw),
        defaults={"raw_value": str(raw), "district": district},
    )
    return alias
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_geo_resolution -v 2`
Expected: PASS — 12 tests OK

Note on `test_a_bare_tashkent_is_ambiguous_and_returns_none`: the fixture names are "Tashkent City" and "Tashkent Region", so a bare "Tashkent" normalises to `tashkent` and matches neither. That is the intended behaviour, and it is why the fixture must not name either region simply "Tashkent".

- [ ] **Step 5: Commit**

```bash
git add step
git commit -m "Resolve place-names to seeded geography, refusing to guess"
```

---

### Task 7: The identity resolver

One resolver, used by both the importer and signup, driven by an ordered setting. Which identifier is authoritative is not yet decided by the client (spec §4.3), so it must be configuration.

**Files:**
- Create: `step/identity.py`
- Modify: `config/settings.py` (add `STEP_ROSTER_MATCH_KEYS`)
- Test: `step/tests/test_identity.py`

- [ ] **Step 1: Write the failing test**

```python
# step/tests/test_identity.py
"""No single identifier is safe here (spec §4.3): PINFL is an Uzbek citizen
number foreign educators may not hold, passports change on renewal, and email
gets mistyped. So the resolver tries keys in a configured order and refuses to
answer when two roster rows both match.
"""

from django.test import TestCase, override_settings

from step import identity
from step.models import Educator, Region


class ResolveTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.maria = Educator.objects.create(
            full_name="Maria Santos",
            region=self.region,
            email="maria@example.com",
            passport_no="P1234567",
            pinfl="12345678901234",
        )

    @override_settings(STEP_ROSTER_MATCH_KEYS=["pinfl", "passport_no", "email"])
    def test_matches_on_the_first_configured_key(self):
        educator, key = identity.resolve(pinfl="12345678901234")
        self.assertEqual(educator, self.maria)
        self.assertEqual(key, "pinfl")

    @override_settings(STEP_ROSTER_MATCH_KEYS=["pinfl", "passport_no", "email"])
    def test_falls_back_to_a_later_key(self):
        educator, key = identity.resolve(email="maria@example.com")
        self.assertEqual(educator, self.maria)
        self.assertEqual(key, "email")

    @override_settings(STEP_ROSTER_MATCH_KEYS=["email"])
    def test_a_key_not_in_the_configured_order_is_ignored(self):
        educator, key = identity.resolve(pinfl="12345678901234")
        self.assertIsNone(educator)
        self.assertIsNone(key)

    @override_settings(STEP_ROSTER_MATCH_KEYS=["email"])
    def test_email_matching_is_case_insensitive_and_trimmed(self):
        educator, _ = identity.resolve(email="  MARIA@EXAMPLE.COM ")
        self.assertEqual(educator, self.maria)

    @override_settings(STEP_ROSTER_MATCH_KEYS=["passport_no"])
    def test_blank_values_never_match_blank_roster_fields(self):
        Educator.objects.create(full_name="Blank Person", region=self.region)
        educator, key = identity.resolve(passport_no="")
        self.assertIsNone(educator)
        self.assertIsNone(key)

    @override_settings(STEP_ROSTER_MATCH_KEYS=["email"])
    def test_two_rows_matching_the_same_key_is_a_conflict_not_a_match(self):
        Educator.objects.create(
            full_name="Maria Santos (duplicate)", region=self.region, email="maria@example.com"
        )
        with self.assertRaises(identity.AmbiguousIdentity):
            identity.resolve(email="maria@example.com")

    @override_settings(STEP_ROSTER_MATCH_KEYS=["email"])
    def test_no_candidates_returns_none(self):
        educator, key = identity.resolve()
        self.assertIsNone(educator)
        self.assertIsNone(key)


class RequiredSignupFieldsTests(TestCase):
    @override_settings(STEP_ROSTER_MATCH_KEYS=["pinfl", "email"])
    def test_signup_asks_for_the_configured_keys(self):
        self.assertEqual(identity.required_signup_fields(), ["pinfl", "email"])

    @override_settings(STEP_ROSTER_MATCH_KEYS=["nonsense", "email"])
    def test_unknown_configured_keys_are_rejected_loudly(self):
        with self.assertRaises(ValueError):
            identity.required_signup_fields()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_identity -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'step.identity'`

- [ ] **Step 3: Write the resolver**

```python
# step/identity.py
"""Matching a person to a roster row.

Used by BOTH the spreadsheet importer and self-signup, deliberately: if they
matched differently, a teacher could sign up and create a duplicate of a row
that already exists. One resolver, one behaviour.

Which identifier is authoritative is a deployment decision the client has not
yet made (spec §4.3), so it lives in settings.STEP_ROSTER_MATCH_KEYS as an
ordered list. Changing it is a settings change, never a migration.
"""

from django.conf import settings

from step.models import Educator

#: The only identifiers the resolver understands. Anything else in the setting
#: is a configuration error worth failing loudly on.
KNOWN_KEYS = ("pinfl", "passport_no", "email")


class AmbiguousIdentity(Exception):
    """Two or more roster rows matched. A human must decide."""


def _configured_keys() -> list[str]:
    keys = list(getattr(settings, "STEP_ROSTER_MATCH_KEYS", ["email"]))
    unknown = [k for k in keys if k not in KNOWN_KEYS]
    if unknown:
        raise ValueError(
            f"STEP_ROSTER_MATCH_KEYS contains unknown keys {unknown}. Known: {list(KNOWN_KEYS)}"
        )
    return keys


def required_signup_fields() -> list[str]:
    """What the signup form must ask for, in order."""
    return _configured_keys()


def _normalise(key: str, value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if key == "email":
        text = text.lower()
    return text


def resolve(*, email=None, passport_no=None, pinfl=None):
    """Return (Educator, key_used), or (None, None) if nothing matched.

    Raises AmbiguousIdentity when one key matches more than one roster row —
    silently picking the first would attach a teacher to the wrong person.
    """
    supplied = {"email": email, "passport_no": passport_no, "pinfl": pinfl}

    for key in _configured_keys():
        value = _normalise(key, supplied.get(key))
        if not value:
            continue
        lookup = f"{key}__iexact" if key == "email" else key
        matches = list(Educator.objects.filter(**{lookup: value})[:2])
        if len(matches) > 1:
            raise AmbiguousIdentity(f"{key}={value!r} matches more than one roster row")
        if matches:
            return matches[0], key

    return None, None
```

- [ ] **Step 4: Add the setting**

In `config/settings.py`, after the `DATABASES` block, add:

```python
# --- STEP Platform --------------------------------------------------------
# Which identifiers match a signup to a roster row, in priority order.
# The client has not yet decided what signup asks for (email + passport, or
# email + PINFL), so this is configuration rather than schema. Known values:
# "pinfl", "passport_no", "email".
STEP_ROSTER_MATCH_KEYS = [
    k.strip()
    for k in os.environ.get("STEP_ROSTER_MATCH_KEYS", "email").split(",")
    if k.strip()
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_identity -v 2`
Expected: PASS — 9 tests OK

- [ ] **Step 6: Commit**

```bash
git add step config/settings.py
git commit -m "Add the configurable identity resolver shared by import and signup"
```

---

### Task 8: The idempotent roster importer

**Files:**
- Create: `step/roster/importer.py`, `step/management/commands/import_roster.py`
- Test: `step/tests/test_importer.py`

- [ ] **Step 1: Write the failing test**

```python
# step/tests/test_importer.py
"""Re-importing an updated sheet must never destroy people (spec §4.2).

The sheet is a living source of truth: it grows, it gets re-exported, and rows
disappear for mundane reasons. A person who vanishes is flagged, not deleted,
because deletion would cascade away their entire submission history.
"""

import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings
from openpyxl import Workbook

from step.models import Educator, Region, RosterImport, School, UnresolvedRow
from step.roster import importer

MEDIA = tempfile.mkdtemp()


def write_sheet(rows, headers=("Full Name", "Email", "Region", "School")):
    """Write a temporary .xlsx and return its path.

    Django's TestCase rolls back the database but NOT file writes, so these go
    to a temp directory that the class cleans up.
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(list(headers))
    for row in rows:
        sheet.append(list(row))
    path = Path(tempfile.mkstemp(suffix=".xlsx")[1])
    workbook.save(path)
    return path


@override_settings(MEDIA_ROOT=MEDIA, STEP_ROSTER_MATCH_KEYS=["email"])
class ImportRosterTests(TestCase):
    def setUp(self):
        call_command("seed_geography", stdout=StringIO())

    def test_creates_educators_schools_and_records_the_import(self):
        path = write_sheet([
            ("Maria Santos", "maria@example.com", "Samarkand", "International School 4"),
            ("John Cruz", "john@example.com", "Fergana", "School 12"),
        ])
        result = importer.import_file(path)

        self.assertEqual(Educator.objects.count(), 2)
        self.assertEqual(School.objects.count(), 2)
        self.assertEqual(result.created_count, 2)
        self.assertEqual(result.updated_count, 0)
        self.assertEqual(RosterImport.objects.count(), 1)

    def test_unmapped_columns_are_preserved(self):
        path = write_sheet(
            [("Maria Santos", "maria@example.com", "Samarkand", "Contract A")],
            headers=("Full Name", "Email", "Region", "Contract Type"),
        )
        importer.import_file(path)
        educator = Educator.objects.get(email="maria@example.com")
        self.assertEqual(educator.source_fields["Contract Type"], "Contract A")

    def test_reimport_updates_in_place_and_does_not_duplicate(self):
        first = write_sheet([("Maria Santos", "maria@example.com", "Samarkand", "School A")])
        importer.import_file(first)

        second = write_sheet([("Maria Santos-Cruz", "maria@example.com", "Samarkand", "School A")])
        result = importer.import_file(second)

        self.assertEqual(Educator.objects.count(), 1)
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.updated_count, 1)
        self.assertEqual(Educator.objects.get().full_name, "Maria Santos-Cruz")

    def test_a_person_missing_from_a_reimport_is_flagged_not_deleted(self):
        first = write_sheet([
            ("Maria Santos", "maria@example.com", "Samarkand", "School A"),
            ("John Cruz", "john@example.com", "Fergana", "School B"),
        ])
        importer.import_file(first)

        second = write_sheet([("Maria Santos", "maria@example.com", "Samarkand", "School A")])
        importer.import_file(second)

        self.assertEqual(Educator.objects.count(), 2)
        self.assertTrue(Educator.objects.get(email="john@example.com").missing_from_last_import)
        self.assertFalse(Educator.objects.get(email="maria@example.com").missing_from_last_import)

    def test_returning_to_the_sheet_clears_the_missing_flag(self):
        both = [
            ("Maria Santos", "maria@example.com", "Samarkand", "School A"),
            ("John Cruz", "john@example.com", "Fergana", "School B"),
        ]
        importer.import_file(write_sheet(both))
        importer.import_file(write_sheet(both[:1]))
        importer.import_file(write_sheet(both))
        self.assertFalse(Educator.objects.get(email="john@example.com").missing_from_last_import)

    def test_an_unresolvable_region_becomes_an_unresolved_row(self):
        path = write_sheet([("Maria Santos", "maria@example.com", "Atlantis", "School A")])
        result = importer.import_file(path)

        self.assertEqual(Educator.objects.count(), 0)
        self.assertEqual(result.unresolved_count, 1)
        row = UnresolvedRow.objects.get()
        self.assertIn("region", row.reason.lower())
        self.assertEqual(row.payload["Full Name"], "Maria Santos")

    def test_a_row_with_no_identity_value_is_unresolved(self):
        path = write_sheet([("Maria Santos", "", "Samarkand", "School A")])
        result = importer.import_file(path)
        self.assertEqual(result.unresolved_count, 1)
        self.assertEqual(Educator.objects.count(), 0)

    def test_an_insufficient_sheet_raises_before_writing_anything(self):
        path = write_sheet(
            [("Maria Santos", "Contract A")], headers=("Full Name", "Contract Type")
        )
        with self.assertRaises(importer.InsufficientMapping):
            importer.import_file(path)
        self.assertEqual(Educator.objects.count(), 0)
        self.assertEqual(RosterImport.objects.count(), 0)

    def test_a_district_column_alone_places_the_educator(self):
        path = write_sheet(
            [("Maria Santos", "maria@example.com", "Kokand")],
            headers=("Full Name", "Email", "District"),
        )
        importer.import_file(path)
        educator = Educator.objects.get()
        self.assertEqual(educator.district.code, "kokand")
        self.assertEqual(educator.region.code, "fergana")

    def test_the_confirmed_mapping_is_stored_on_the_import(self):
        path = write_sheet([("Maria Santos", "maria@example.com", "Samarkand", "School A")])
        importer.import_file(path)
        stored = RosterImport.objects.get().mapping
        self.assertEqual(stored["Email"], "email")
        self.assertEqual(stored["Region"], "region")


@override_settings(MEDIA_ROOT=MEDIA, STEP_ROSTER_MATCH_KEYS=["email"])
class ImportRosterCommandTests(TestCase):
    def setUp(self):
        call_command("seed_geography", stdout=StringIO())

    def test_dry_run_reports_without_writing(self):
        path = write_sheet([("Maria Santos", "maria@example.com", "Samarkand", "School A")])
        out = StringIO()
        call_command("import_roster", str(path), "--dry-run", stdout=out)
        self.assertIn("would create 1", out.getvalue().lower())
        self.assertEqual(Educator.objects.count(), 0)

    def test_command_imports(self):
        path = write_sheet([("Maria Santos", "maria@example.com", "Samarkand", "School A")])
        call_command("import_roster", str(path), stdout=StringIO())
        self.assertEqual(Educator.objects.count(), 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_importer -v 2`
Expected: FAIL — `ImportError: cannot import name 'importer' from 'step.roster'`

- [ ] **Step 3: Write the importer**

```python
# step/roster/importer.py
"""Importing the client's roster spreadsheet without knowing its shape.

Three properties matter more than anything else here:

1. **Nothing is written until the whole sheet is understood.** An insufficient
   mapping raises before a single row is touched, so a wrong file cannot half-
   import.
2. **Re-import is idempotent.** Rows are matched through `step.identity`, the
   same resolver signup uses. Updates happen in place.
3. **Nobody is ever deleted.** A person absent from a re-import is flagged.
   Deleting would cascade away their submission history, which is the one thing
   in this system that cannot be recreated.
"""

from dataclasses import dataclass, field

from django.core.files import File
from django.db import transaction
from openpyxl import load_workbook

from step import identity
from step.models import Educator, RosterImport, School, UnresolvedRow
from step.roster import geo
from step.roster.mapping import check_sufficiency, propose_mapping


class InsufficientMapping(Exception):
    """The sheet lacks an identity key or a geographic anchor."""


@dataclass
class ImportResult:
    created_count: int = 0
    updated_count: int = 0
    unresolved_count: int = 0
    row_count: int = 0
    mapping: dict = field(default_factory=dict)
    roster_import: RosterImport | None = None


def read_rows(path, header_row: int = 1):
    """Return (headers, [row dicts]) from the first worksheet.

    Opened read-only: the client's files are treated as read-only source
    material, matching the convention in the diagnostics extraction code.
    """
    workbook = load_workbook(filename=str(path), read_only=True, data_only=True)
    sheet = workbook[workbook.sheetnames[0]]

    rows = []
    headers = []
    for index, raw in enumerate(sheet.iter_rows(values_only=True), start=1):
        if index < header_row:
            continue
        if index == header_row:
            headers = [h for h in raw]
            continue
        if all(cell is None or str(cell).strip() == "" for cell in raw):
            continue
        rows.append({headers[i]: raw[i] for i in range(min(len(headers), len(raw)))})
    workbook.close()
    return headers, rows


def _value(row, mapping_dict, field_name):
    for header, target in mapping_dict.items():
        if target == field_name:
            raw = row.get(header)
            return "" if raw is None else str(raw).strip()
    return ""


def _place(row, mapping_dict):
    """Return (region, district, school_name) or raise ValueError with a reason."""
    region_raw = _value(row, mapping_dict, "region")
    district_raw = _value(row, mapping_dict, "district")
    school_name = _value(row, mapping_dict, "school")

    region = geo.resolve_region(region_raw) if region_raw else None
    district = geo.resolve_district(district_raw, region) if district_raw else None

    if region is None and district is not None:
        region = district.region
    if region is None:
        if region_raw:
            raise ValueError(f"could not resolve region {region_raw!r}")
        if district_raw:
            raise ValueError(f"could not resolve district {district_raw!r}")
        raise ValueError("no region or district given")

    return region, district, school_name


@transaction.atomic
def import_file(path, *, header_row: int = 1, dry_run: bool = False, user=None) -> ImportResult:
    headers, rows = read_rows(path, header_row=header_row)
    mapping_dict = propose_mapping(headers)

    sufficient, missing = check_sufficiency(mapping_dict)
    if not sufficient:
        raise InsufficientMapping(
            "The sheet is missing " + " and ".join(missing) + f". Headers seen: {headers}"
        )

    result = ImportResult(row_count=len(rows), mapping={k: v for k, v in mapping_dict.items() if v})

    roster_import = None
    if not dry_run:
        roster_import = RosterImport(header_row=header_row, mapping=result.mapping, imported_by=user)
        with open(path, "rb") as handle:
            roster_import.file.save(getattr(path, "name", str(path)).split("/")[-1], File(handle), save=False)
        roster_import.save()
        result.roster_import = roster_import

    seen_ids = []
    for number, row in enumerate(rows, start=header_row + 1):
        email = _value(row, mapping_dict, "email")
        passport_no = _value(row, mapping_dict, "passport_no")
        pinfl = _value(row, mapping_dict, "pinfl")

        if not any([email, passport_no, pinfl]):
            result.unresolved_count += 1
            if not dry_run:
                UnresolvedRow.objects.create(
                    roster_import=roster_import, row_number=number,
                    reason="no identity value in this row", payload=_payload(row),
                )
            continue

        try:
            region, district, school_name = _place(row, mapping_dict)
        except ValueError as exc:
            result.unresolved_count += 1
            if not dry_run:
                UnresolvedRow.objects.create(
                    roster_import=roster_import, row_number=number,
                    reason=str(exc), payload=_payload(row),
                )
            continue

        try:
            existing, _key = identity.resolve(email=email, passport_no=passport_no, pinfl=pinfl)
        except identity.AmbiguousIdentity as exc:
            result.unresolved_count += 1
            if not dry_run:
                UnresolvedRow.objects.create(
                    roster_import=roster_import, row_number=number,
                    reason=str(exc), payload=_payload(row),
                )
            continue

        if dry_run:
            if existing:
                result.updated_count += 1
            else:
                result.created_count += 1
            continue

        school = None
        if school_name and district is not None:
            school, _ = School.objects.get_or_create(name=school_name, district=district)

        defaults = {
            "full_name": _value(row, mapping_dict, "full_name") or (existing.full_name if existing else email),
            "email": email,
            "passport_no": passport_no,
            "pinfl": pinfl,
            "region": region,
            "district": district,
            "source_fields": _unmapped(row, mapping_dict),
            "missing_from_last_import": False,
        }
        if school is not None:
            defaults["school"] = school

        if existing:
            for name, value in defaults.items():
                setattr(existing, name, value)
            existing.save()
            result.updated_count += 1
            seen_ids.append(existing.pk)
        else:
            created = Educator.objects.create(**defaults)
            result.created_count += 1
            seen_ids.append(created.pk)

    if not dry_run:
        Educator.objects.exclude(pk__in=seen_ids).update(missing_from_last_import=True)
        roster_import.row_count = result.row_count
        roster_import.created_count = result.created_count
        roster_import.updated_count = result.updated_count
        roster_import.unresolved_count = result.unresolved_count
        roster_import.save()

    return result


def _payload(row):
    return {str(k): ("" if v is None else str(v)) for k, v in row.items() if k}


def _unmapped(row, mapping_dict):
    return {
        str(header): ("" if value is None else str(value))
        for header, value in row.items()
        if header and mapping_dict.get(header) is None
    }
```

```python
# step/management/commands/import_roster.py
"""Imports the client roster spreadsheet.

`--dry-run` exists because the sheet's shape is unknown: the safe first move on
any new file is to see what the importer thinks it is looking at.
"""

from django.core.management.base import BaseCommand, CommandError

from step.roster import importer


class Command(BaseCommand):
    help = "Import educators from a roster spreadsheet. Idempotent; never deletes."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--header-row", type=int, default=1)
        parser.add_argument("--dry-run", action="store_true", help="Report without writing.")

    def handle(self, *args, **options):
        try:
            result = importer.import_file(
                options["path"], header_row=options["header_row"], dry_run=options["dry_run"]
            )
        except importer.InsufficientMapping as exc:
            raise CommandError(str(exc)) from exc

        verb = "would create" if options["dry_run"] else "created"
        second = "would update" if options["dry_run"] else "updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{result.row_count} rows: {verb} {result.created_count}, "
                f"{second} {result.updated_count}, {result.unresolved_count} unresolved."
            )
        )
        self.stdout.write(f"Mapping used: {result.mapping}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_importer -v 2`
Expected: PASS — 12 tests OK

- [ ] **Step 5: Run the whole suite**

Run: `.venv\Scripts\python.exe manage.py test`
Expected: all tests OK, count strictly greater than the baseline you measured

- [ ] **Step 6: Commit**

```bash
git add step
git commit -m "Add the idempotent roster importer with an unresolved-row queue"
```

---

## Phase 3 — The obligation engine

### Task 9: Period arithmetic and due-date rules

Pure functions, no models. Isolated here because date arithmetic is where off-by-one bugs live, and they are cheapest to catch without a database.

**Files:**
- Create: `step/scheduling.py`
- Test: `step/tests/test_scheduling.py`

- [ ] **Step 1: Write the failing test**

```python
# step/tests/test_scheduling.py
"""Due dates come from a rule on the obligation type (spec §5.4).

Month-end is the classic trap: "day 31 of the month" must not explode in
February, and "five days before term end" must land inside the term.
"""

from datetime import date

from django.test import SimpleTestCase

from step import constants, scheduling


class MonthPeriodTests(SimpleTestCase):
    def test_month_start_normalises_to_the_first(self):
        self.assertEqual(scheduling.period_start_for(date(2026, 5, 17), constants.PERIOD_MONTH), date(2026, 5, 1))

    def test_month_end(self):
        self.assertEqual(scheduling.period_end(date(2026, 5, 1), constants.PERIOD_MONTH), date(2026, 5, 31))

    def test_february_end_in_a_leap_year(self):
        self.assertEqual(scheduling.period_end(date(2028, 2, 1), constants.PERIOD_MONTH), date(2028, 2, 29))

    def test_next_month_rolls_the_year(self):
        self.assertEqual(scheduling.next_period_start(date(2026, 12, 1), constants.PERIOD_MONTH), date(2027, 1, 1))


class DueDateRuleTests(SimpleTestCase):
    def test_day_of_month(self):
        rule = {"kind": "day_of_month", "day": 27}
        due = scheduling.due_date_for(rule, date(2026, 5, 1), date(2026, 5, 31))
        self.assertEqual(due, date(2026, 5, 27))

    def test_day_of_month_is_clamped_to_the_last_day(self):
        rule = {"kind": "day_of_month", "day": 31}
        due = scheduling.due_date_for(rule, date(2026, 2, 1), date(2026, 2, 28))
        self.assertEqual(due, date(2026, 2, 28))

    def test_days_before_period_end(self):
        rule = {"kind": "days_before_period_end", "days": 5}
        due = scheduling.due_date_for(rule, date(2025, 9, 1), date(2025, 11, 30))
        self.assertEqual(due, date(2025, 11, 25))

    def test_days_before_period_end_never_precedes_the_start(self):
        rule = {"kind": "days_before_period_end", "days": 500}
        due = scheduling.due_date_for(rule, date(2026, 5, 1), date(2026, 5, 31))
        self.assertEqual(due, date(2026, 5, 1))

    def test_days_after_period_start(self):
        rule = {"kind": "days_after_period_start", "days": 10}
        due = scheduling.due_date_for(rule, date(2026, 5, 1), date(2026, 5, 31))
        self.assertEqual(due, date(2026, 5, 11))

    def test_fixed_date(self):
        rule = {"kind": "fixed", "date": "2026-06-15"}
        due = scheduling.due_date_for(rule, date(2026, 5, 1), date(2026, 5, 31))
        self.assertEqual(due, date(2026, 6, 15))

    def test_an_unknown_rule_kind_raises_rather_than_defaulting(self):
        with self.assertRaises(ValueError):
            scheduling.due_date_for({"kind": "whenever"}, date(2026, 5, 1), date(2026, 5, 31))

    def test_an_empty_rule_defaults_to_the_period_end(self):
        due = scheduling.due_date_for({}, date(2026, 5, 1), date(2026, 5, 31))
        self.assertEqual(due, date(2026, 5, 31))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_scheduling -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'step.scheduling'`

- [ ] **Step 3: Write the module**

```python
# step/scheduling.py
"""Period arithmetic and due-date rules.

Kept free of models on purpose. Date handling is where the quiet bugs are —
"day 31" in February, a term deadline that lands before the term starts — and
pure functions make those cases cheap to pin down in tests.

A due rule is a small JSON object stored on the obligation type:

    {"kind": "day_of_month", "day": 27}
    {"kind": "days_before_period_end", "days": 5}
    {"kind": "days_after_period_start", "days": 10}
    {"kind": "fixed", "date": "2026-06-15"}

An empty rule means "the last day of the period".
"""

import calendar
from datetime import date, timedelta

from step import constants


def period_start_for(day: date, period_kind: str) -> date:
    if period_kind == constants.PERIOD_MONTH:
        return day.replace(day=1)
    return day


def period_end(start: date, period_kind: str) -> date:
    if period_kind == constants.PERIOD_MONTH:
        return start.replace(day=calendar.monthrange(start.year, start.month)[1])
    if period_kind == constants.PERIOD_YEAR:
        return date(start.year, 12, 31)
    return start


def next_period_start(start: date, period_kind: str) -> date:
    if period_kind == constants.PERIOD_MONTH:
        if start.month == 12:
            return date(start.year + 1, 1, 1)
        return date(start.year, start.month + 1, 1)
    if period_kind == constants.PERIOD_YEAR:
        return date(start.year + 1, start.month, start.day)
    return start


def due_date_for(rule, period_start: date, period_finish: date) -> date:
    """Resolve a due rule against a concrete period.

    Always returns a date inside [period_start, period_finish] for the relative
    rules; a "fixed" rule is trusted as given, because an explicit date is an
    explicit decision.
    """
    if not rule:
        return period_finish

    kind = rule.get("kind")

    if kind == "day_of_month":
        day = int(rule["day"])
        last = calendar.monthrange(period_start.year, period_start.month)[1]
        return period_start.replace(day=min(day, last))

    if kind == "days_before_period_end":
        candidate = period_finish - timedelta(days=int(rule["days"]))
        return max(candidate, period_start)

    if kind == "days_after_period_start":
        candidate = period_start + timedelta(days=int(rule["days"]))
        return min(candidate, period_finish)

    if kind == "fixed":
        return date.fromisoformat(rule["date"])

    raise ValueError(f"Unknown due rule kind: {kind!r}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_scheduling -v 2`
Expected: PASS — 12 tests OK

- [ ] **Step 5: Commit**

```bash
git add step
git commit -m "Add period arithmetic and due-date rules as pure functions"
```

---

### Task 10: Obligation models

**Files:**
- Create: `step/models/obligations.py`
- Modify: `step/models/__init__.py`
- Test: `step/tests/test_obligation_models.py`

- [ ] **Step 1: Write the failing test**

```python
# step/tests/test_obligation_models.py
"""An obligation type is a database row, not a class (spec §5.1).

That is what makes CPD Online, CPD Offline and ECA configuration rather than
three more builds. The test that matters is the last one: creating a new
vertical must take no code.
"""

from datetime import date

from django.db import IntegrityError
from django.test import TestCase

from step import constants
from step.models import AcademicYear, Educator, Obligation, ObligationType, Region, Term


class TermTests(TestCase):
    def setUp(self):
        self.year = AcademicYear.objects.create(
            label="2025-26", start=date(2025, 9, 1), end=date(2026, 5, 31), is_current=True
        )

    def test_terms_order_by_sequence(self):
        Term.objects.create(year=self.year, name="Term 3", sequence=3, start=date(2026, 3, 1), end=date(2026, 5, 31))
        Term.objects.create(year=self.year, name="Term 1", sequence=1, start=date(2025, 9, 1), end=date(2025, 11, 30))
        self.assertEqual([t.name for t in self.year.terms.all()], ["Term 1", "Term 3"])

    def test_only_one_year_can_be_current(self):
        AcademicYear.objects.create(
            label="2026-27", start=date(2026, 9, 1), end=date(2027, 5, 31), is_current=True
        )
        self.assertEqual(AcademicYear.objects.filter(is_current=True).count(), 1)
        self.assertEqual(AcademicYear.objects.get(is_current=True).label, "2026-27")


class ObligationTypeTests(TestCase):
    def test_defaults_are_the_least_surprising_ones(self):
        obligation_type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY,
        )
        self.assertTrue(obligation_type.is_active)
        self.assertEqual(obligation_type.evidence_spec, constants.EVIDENCE_EITHER)
        self.assertEqual(obligation_type.scope_rule, constants.SCOPE_ALL)
        self.assertEqual(obligation_type.min_count, 1)
        self.assertFalse(obligation_type.requires_review)

    def test_period_kind_follows_the_cadence(self):
        monthly = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY,
        )
        termly = ObligationType.objects.create(
            name_template="ECA Plan", category=constants.CATEGORY_ECA,
            cadence=constants.CADENCE_TERMLY,
        )
        self.assertEqual(monthly.period_kind, constants.PERIOD_MONTH)
        self.assertEqual(termly.period_kind, constants.PERIOD_TERM)

    def test_a_new_vertical_needs_no_code(self):
        """The acceptance test for the whole design (spec §2)."""
        ObligationType.objects.create(
            name_template="CPD Offline - {period}", category=constants.CATEGORY_CPD_OFFLINE,
            cadence=constants.CADENCE_TERMLY, evidence_spec=constants.EVIDENCE_FILE,
            requires_review=True,
        )
        self.assertEqual(ObligationType.objects.filter(category=constants.CATEGORY_CPD_OFFLINE).count(), 1)


class ObligationTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY,
        )

    def test_status_starts_not_started(self):
        obligation = Obligation.objects.create(
            type=self.type, educator=self.educator,
            period_kind=constants.PERIOD_MONTH, period_start=date(2026, 5, 1),
            due_date=date(2026, 5, 27),
        )
        self.assertEqual(obligation.status, constants.STATUS_NOT_STARTED)

    def test_one_obligation_per_type_educator_and_period(self):
        for _ in range(1):
            Obligation.objects.create(
                type=self.type, educator=self.educator,
                period_kind=constants.PERIOD_MONTH, period_start=date(2026, 5, 1),
                due_date=date(2026, 5, 27),
            )
        with self.assertRaises(IntegrityError):
            Obligation.objects.create(
                type=self.type, educator=self.educator,
                period_kind=constants.PERIOD_MONTH, period_start=date(2026, 5, 1),
                due_date=date(2026, 5, 27),
            )

    def test_display_name_renders_the_template_with_the_period(self):
        obligation = Obligation.objects.create(
            type=self.type, educator=self.educator,
            period_kind=constants.PERIOD_MONTH, period_start=date(2026, 5, 1),
            due_date=date(2026, 5, 27),
        )
        self.assertEqual(obligation.display_name, "Monthly Report - May 2026")

    def test_a_template_with_an_explicit_period_placeholder_is_honoured(self):
        obligation_type = ObligationType.objects.create(
            name_template="ECA Programme Plan - {period}", category=constants.CATEGORY_ECA,
            cadence=constants.CADENCE_TERMLY,
        )
        obligation = Obligation.objects.create(
            type=obligation_type, educator=self.educator,
            period_kind=constants.PERIOD_TERM, period_start=date(2025, 9, 1),
            period_label="Term 1", due_date=date(2025, 11, 25),
        )
        self.assertEqual(obligation.display_name, "ECA Programme Plan - Term 1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_obligation_models -v 2`
Expected: FAIL — `ImportError: cannot import name 'AcademicYear' from 'step.models'`

- [ ] **Step 3: Write the models**

```python
# step/models/obligations.py
"""The obligation engine.

An ObligationType is a database row rather than a Python class, which is the
single decision the whole platform rests on: it makes CPD Online, CPD Offline,
ECA and any future vertical configuration rather than code (spec §5.1). Only a
vertical needing a bespoke form or bespoke content requires programming, and it
attaches through `form_slug`.

Status is stored. Urgency is not — see `step/urgency.py` and spec §5.3.
"""

from django.db import models

from step import constants
from step.models.roster import Educator
from step.scheduling import period_end as _period_end


class AcademicYear(models.Model):
    label = models.CharField(max_length=32, unique=True, help_text='For example "2025-26".')
    start = models.DateField()
    end = models.DateField()
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["-start"]

    def save(self, *args, **kwargs):
        """Only one year is current. Enforced here because two current years
        would make every "this year" figure on the dashboard ambiguous."""
        super().save(*args, **kwargs)
        if self.is_current:
            AcademicYear.objects.exclude(pk=self.pk).filter(is_current=True).update(is_current=False)

    def __str__(self) -> str:
        return self.label


class Term(models.Model):
    year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="terms")
    name = models.CharField(max_length=32)
    sequence = models.PositiveSmallIntegerField()
    start = models.DateField()
    end = models.DateField()

    class Meta:
        ordering = ["year", "sequence"]
        constraints = [
            models.UniqueConstraint(fields=["year", "sequence"], name="step_term_sequence_unique_per_year"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.year.label})"


class ObligationType(models.Model):
    name_template = models.CharField(
        max_length=200,
        help_text='Shown to teachers. "{period}" is replaced with the month or term; '
                  'if absent, the period is appended after a dash.',
    )
    category = models.CharField(max_length=32, choices=constants.CATEGORY_CHOICES)
    cadence = models.CharField(max_length=16, choices=constants.CADENCE_CHOICES)
    due_rule = models.JSONField(
        default=dict, blank=True,
        help_text='For example {"kind": "day_of_month", "day": 27}. Empty means the period end.',
    )
    evidence_spec = models.CharField(
        max_length=16, choices=constants.EVIDENCE_SPEC_CHOICES, default=constants.EVIDENCE_EITHER
    )
    min_count = models.PositiveSmallIntegerField(default=1)
    requires_review = models.BooleanField(
        default=False, help_text="When false, a submission is accepted immediately."
    )
    scope_rule = models.CharField(
        max_length=16, choices=constants.SCOPE_CHOICES, default=constants.SCOPE_ALL
    )
    form_slug = models.SlugField(
        max_length=64, blank=True,
        help_text="Names a coded form for verticals that need one. Blank means link/file only.",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category", "name_template"]

    @property
    def period_kind(self) -> str:
        return constants.CADENCE_TO_PERIOD_KIND[self.cadence]

    def __str__(self) -> str:
        return self.name_template


class Obligation(models.Model):
    """One concrete thing one educator owes for one period."""

    type = models.ForeignKey(ObligationType, on_delete=models.PROTECT, related_name="obligations")
    educator = models.ForeignKey(Educator, on_delete=models.CASCADE, related_name="obligations")

    period_kind = models.CharField(max_length=16, choices=constants.PERIOD_KIND_CHOICES)
    period_start = models.DateField()
    period_label = models.CharField(
        max_length=32, blank=True,
        help_text='For terms, the term name ("Term 1"). Months derive their own label.',
    )

    due_date = models.DateField()
    due_date_overridden = models.BooleanField(
        default=False, help_text="Set when an extension was granted. Visible, never silent."
    )
    status = models.CharField(
        max_length=16, choices=constants.OBLIGATION_STATUS_CHOICES, default=constants.STATUS_NOT_STARTED
    )
    opened_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "type__category"]
        constraints = [
            models.UniqueConstraint(
                fields=["type", "educator", "period_start"], name="step_obligation_unique_per_period"
            ),
        ]
        indexes = [
            models.Index(fields=["educator", "status"]),
            models.Index(fields=["type", "period_start", "status"]),
            models.Index(fields=["due_date"]),
        ]

    @property
    def period_display(self) -> str:
        if self.period_label:
            return self.period_label
        if self.period_kind == constants.PERIOD_MONTH:
            return self.period_start.strftime("%B %Y")
        if self.period_kind == constants.PERIOD_YEAR:
            return str(self.period_start.year)
        return ""

    @property
    def display_name(self) -> str:
        """What the teacher actually reads. Never exposes model vocabulary."""
        template = self.type.name_template
        period = self.period_display
        if "{period}" in template:
            return template.replace("{period}", period)
        return f"{template} - {period}" if period else template

    @property
    def period_end(self):
        return _period_end(self.period_start, self.period_kind)

    def __str__(self) -> str:
        return f"{self.display_name} ({self.educator.full_name})"
```

- [ ] **Step 4: Update re-exports**

Add to `step/models/__init__.py`:

```python
from step.models.obligations import AcademicYear, Obligation, ObligationType, Term
```

and add `"AcademicYear"`, `"Obligation"`, `"ObligationType"`, `"Term"` to `__all__`.

- [ ] **Step 5: Migrate, test, commit**

Run: `.venv\Scripts\python.exe manage.py makemigrations step`
Run: `.venv\Scripts\python.exe manage.py migrate`
Run: `.venv\Scripts\python.exe manage.py test step.tests.test_obligation_models -v 2`
Expected: PASS — 9 tests OK

```bash
git add step
git commit -m "Add the obligation type and instance models"
```

---

### Task 11: Obligation generation

**Files:**
- Create: `step/generation.py`, `step/management/commands/generate_obligations.py`
- Test: `step/tests/test_generation.py`

- [ ] **Step 1: Write the failing test**

```python
# step/tests/test_generation.py
"""Generation must be safe to run repeatedly — it is scheduled, and a retry
after a partial failure must not double up (spec §5.2). Staff must never
accrue obligations (spec §5.6).
"""

from datetime import date
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from step import constants, generation, roles
from step.models import AcademicYear, Educator, Obligation, ObligationType, Region, Term


class GenerateTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.maria = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.john = Educator.objects.create(full_name="John Cruz", region=self.region)
        self.year = AcademicYear.objects.create(
            label="2025-26", start=date(2025, 9, 1), end=date(2026, 5, 31), is_current=True
        )
        self.term1 = Term.objects.create(
            year=self.year, name="Term 1", sequence=1, start=date(2025, 9, 1), end=date(2025, 11, 30)
        )
        self.monthly = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, due_rule={"kind": "day_of_month", "day": 27},
        )

    def test_generates_one_obligation_per_active_educator(self):
        created = generation.generate_for_month(date(2026, 5, 1))
        self.assertEqual(created, 2)
        self.assertEqual(Obligation.objects.count(), 2)

    def test_the_due_date_comes_from_the_rule(self):
        generation.generate_for_month(date(2026, 5, 1))
        self.assertEqual(Obligation.objects.first().due_date, date(2026, 5, 27))

    def test_running_twice_creates_nothing_new(self):
        generation.generate_for_month(date(2026, 5, 1))
        created = generation.generate_for_month(date(2026, 5, 1))
        self.assertEqual(created, 0)
        self.assertEqual(Obligation.objects.count(), 2)

    def test_inactive_educators_are_skipped(self):
        self.john.is_active = False
        self.john.save()
        generation.generate_for_month(date(2026, 5, 1))
        self.assertEqual(Obligation.objects.count(), 1)

    def test_educators_missing_from_the_last_import_are_skipped(self):
        self.john.missing_from_last_import = True
        self.john.save()
        generation.generate_for_month(date(2026, 5, 1))
        self.assertEqual(Obligation.objects.count(), 1)

    def test_inactive_types_are_skipped(self):
        self.monthly.is_active = False
        self.monthly.save()
        self.assertEqual(generation.generate_for_month(date(2026, 5, 1)), 0)

    def test_termly_types_are_not_generated_by_the_monthly_run(self):
        ObligationType.objects.create(
            name_template="ECA Plan", category=constants.CATEGORY_ECA, cadence=constants.CADENCE_TERMLY
        )
        generation.generate_for_month(date(2026, 5, 1))
        self.assertEqual(Obligation.objects.filter(period_kind=constants.PERIOD_TERM).count(), 0)

    def test_termly_generation_uses_the_term_dates_and_label(self):
        ObligationType.objects.create(
            name_template="ECA Programme Plan - {period}", category=constants.CATEGORY_ECA,
            cadence=constants.CADENCE_TERMLY, due_rule={"kind": "days_before_period_end", "days": 5},
        )
        created = generation.generate_for_term(self.term1)
        self.assertEqual(created, 2)
        obligation = Obligation.objects.get(educator=self.maria, period_kind=constants.PERIOD_TERM)
        self.assertEqual(obligation.period_label, "Term 1")
        self.assertEqual(obligation.due_date, date(2025, 11, 25))
        self.assertEqual(obligation.display_name, "ECA Programme Plan - Term 1")

    def test_staff_users_without_an_educator_row_get_nothing(self):
        user = get_user_model().objects.create_user("admin2", password="x")
        call_command("seed_roles", stdout=StringIO())
        roles.assign(user, constants.ROLE_PROGRAMME_ADMIN)
        generation.generate_for_month(date(2026, 5, 1))
        self.assertEqual(Obligation.objects.count(), 2)


class GenerateCommandTests(TestCase):
    def setUp(self):
        region = Region.objects.create(name="Samarkand", code="samarkand")
        Educator.objects.create(full_name="Maria Santos", region=region)
        ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, due_rule={"kind": "day_of_month", "day": 27},
        )

    def test_command_generates_for_an_explicit_month(self):
        out = StringIO()
        call_command("generate_obligations", "--month", "2026-05", stdout=out)
        self.assertEqual(Obligation.objects.count(), 1)
        self.assertIn("1", out.getvalue())

    def test_command_rejects_a_malformed_month(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command("generate_obligations", "--month", "May", stdout=StringIO())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_generation -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'step.generation'`

- [ ] **Step 3: Write generation**

```python
# step/generation.py
"""Materialising obligation instances.

Rows rather than on-the-fly computation (spec §5.2): submissions, extensions
and history all need something durable to hang off, and 60,000 rows a year is
not a storage problem.

Idempotent through the unique constraint on (type, educator, period_start), so
a scheduled run that is retried after a partial failure cannot double up.
"""

from datetime import date

from django.db import transaction

from step import constants, scheduling
from step.models import Educator, Obligation, ObligationType


def eligible_educators():
    """Every educator who should accrue obligations.

    Excludes people flagged as missing from the last import — generating work
    for someone who has left the programme creates false overdue figures.
    """
    return Educator.objects.filter(is_active=True, missing_from_last_import=False)


def _create_missing(obligation_type, period_kind, period_start, due, label=""):
    created = 0
    for educator in eligible_educators():
        _, made = Obligation.objects.get_or_create(
            type=obligation_type,
            educator=educator,
            period_start=period_start,
            defaults={
                "period_kind": period_kind,
                "period_label": label,
                "due_date": due,
            },
        )
        if made:
            created += 1
    return created


@transaction.atomic
def generate_for_month(month_start: date) -> int:
    """Create this month's obligations for every monthly type."""
    start = scheduling.period_start_for(month_start, constants.PERIOD_MONTH)
    finish = scheduling.period_end(start, constants.PERIOD_MONTH)

    created = 0
    for obligation_type in ObligationType.objects.filter(
        is_active=True, cadence=constants.CADENCE_MONTHLY
    ):
        due = scheduling.due_date_for(obligation_type.due_rule, start, finish)
        created += _create_missing(obligation_type, constants.PERIOD_MONTH, start, due)
    return created


@transaction.atomic
def generate_for_term(term) -> int:
    """Create this term's obligations for every termly type."""
    created = 0
    for obligation_type in ObligationType.objects.filter(
        is_active=True, cadence=constants.CADENCE_TERMLY
    ):
        due = scheduling.due_date_for(obligation_type.due_rule, term.start, term.end)
        created += _create_missing(
            obligation_type, constants.PERIOD_TERM, term.start, due, label=term.name
        )
    return created
```

```python
# step/management/commands/generate_obligations.py
"""Creates the next period's obligations. Scheduled, and safe to re-run."""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from step import generation
from step.models import AcademicYear, Term


class Command(BaseCommand):
    help = "Generate obligation instances for a month and/or a term. Idempotent."

    def add_arguments(self, parser):
        parser.add_argument("--month", help='Month to generate, as YYYY-MM. Defaults to today.')
        parser.add_argument("--term", help="Term name within the current academic year.")

    def handle(self, *args, **options):
        total = 0

        raw_month = options.get("month")
        if raw_month:
            try:
                year, month = raw_month.split("-")
                month_start = date(int(year), int(month), 1)
            except (ValueError, TypeError) as exc:
                raise CommandError(f"--month must look like 2026-05, got {raw_month!r}") from exc
        else:
            month_start = date.today().replace(day=1)

        total += generation.generate_for_month(month_start)

        term_name = options.get("term")
        if term_name:
            current = AcademicYear.objects.filter(is_current=True).first()
            if current is None:
                raise CommandError("No academic year is marked current.")
            term = Term.objects.filter(year=current, name=term_name).first()
            if term is None:
                raise CommandError(f"No term named {term_name!r} in {current.label}.")
            total += generation.generate_for_term(term)

        self.stdout.write(self.style.SUCCESS(f"Created {total} obligations."))
```

- [ ] **Step 4: Run tests, then commit**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_generation -v 2`
Expected: PASS — 11 tests OK

```bash
git add step
git commit -m "Generate obligation instances idempotently for months and terms"
```

---

### Task 12: Derived urgency and the teacher's tiles

Nothing in this task is stored. That is the point (spec §5.3).

**Files:**
- Create: `step/urgency.py`
- Test: `step/tests/test_urgency.py`

- [ ] **Step 1: Write the failing test**

```python
# step/tests/test_urgency.py
"""Urgency badges and stat tiles are computed, never stored (spec §5.3).

Storing them means a nightly job has to flip them, and the day it fails the
dashboard lies without anyone noticing.
"""

from datetime import date, timedelta

from django.test import TestCase

from step import constants, urgency
from step.models import Educator, Obligation, ObligationType, Region

TODAY = date(2026, 5, 20)


class UrgencyTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY,
        )

    def make(self, due, status=constants.STATUS_NOT_STARTED, period=date(2026, 5, 1)):
        return Obligation.objects.create(
            type=self.type, educator=self.educator, period_kind=constants.PERIOD_MONTH,
            period_start=period, due_date=due, status=status,
        )

    def test_an_accepted_obligation_is_done_regardless_of_date(self):
        obligation = self.make(TODAY - timedelta(days=30), status=constants.STATUS_ACCEPTED)
        self.assertEqual(urgency.urgency_of(obligation, TODAY), constants.URGENCY_DONE)

    def test_a_submitted_obligation_awaiting_review_is_done_for_the_teacher(self):
        obligation = self.make(TODAY - timedelta(days=1), status=constants.STATUS_SUBMITTED)
        self.assertEqual(urgency.urgency_of(obligation, TODAY), constants.URGENCY_DONE)

    def test_a_returned_obligation_past_its_date_is_overdue_again(self):
        obligation = self.make(TODAY - timedelta(days=1), status=constants.STATUS_RETURNED)
        self.assertEqual(urgency.urgency_of(obligation, TODAY), constants.URGENCY_OVERDUE)

    def test_past_due_is_overdue(self):
        self.assertEqual(urgency.urgency_of(self.make(TODAY - timedelta(days=1)), TODAY), constants.URGENCY_OVERDUE)

    def test_due_today(self):
        self.assertEqual(urgency.urgency_of(self.make(TODAY), TODAY), constants.URGENCY_DUE_TODAY)

    def test_within_the_window_is_due_soon(self):
        self.assertEqual(urgency.urgency_of(self.make(TODAY + timedelta(days=3)), TODAY), constants.URGENCY_DUE_SOON)

    def test_beyond_the_window_is_merely_scheduled(self):
        far = TODAY + timedelta(days=constants.DUE_SOON_DAYS + 1)
        self.assertEqual(urgency.urgency_of(self.make(far), TODAY), constants.URGENCY_SCHEDULED)


class TeacherTilesTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY,
        )

    def make(self, period, due, status=constants.STATUS_NOT_STARTED):
        return Obligation.objects.create(
            type=self.type, educator=self.educator, period_kind=constants.PERIOD_MONTH,
            period_start=period, due_date=due, status=status,
        )

    def test_tiles_count_active_due_this_month_completed_and_progress(self):
        self.make(date(2026, 5, 1), date(2026, 5, 27))
        self.make(date(2026, 4, 1), date(2026, 4, 27), status=constants.STATUS_ACCEPTED)
        self.make(date(2026, 6, 1), date(2026, 6, 27))

        tiles = urgency.teacher_tiles(self.educator, today=TODAY)
        self.assertEqual(tiles["active"], 2)
        self.assertEqual(tiles["due_this_month"], 1)
        self.assertEqual(tiles["completed"], 1)
        self.assertEqual(tiles["progress_percent"], 33)

    def test_progress_is_zero_with_no_obligations_rather_than_dividing_by_zero(self):
        tiles = urgency.teacher_tiles(self.educator, today=TODAY)
        self.assertEqual(tiles["progress_percent"], 0)
        self.assertEqual(tiles["active"], 0)

    def test_next_action_is_the_most_urgent_outstanding_obligation(self):
        self.make(date(2026, 6, 1), date(2026, 6, 27))
        soonest = self.make(date(2026, 5, 1), date(2026, 5, 22))
        self.assertEqual(urgency.next_action(self.educator, today=TODAY), soonest)

    def test_next_action_is_none_when_everything_is_settled(self):
        self.make(date(2026, 5, 1), date(2026, 5, 22), status=constants.STATUS_ACCEPTED)
        self.assertIsNone(urgency.next_action(self.educator, today=TODAY))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_urgency -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'step.urgency'`

- [ ] **Step 3: Write the module**

```python
# step/urgency.py
"""Everything the teacher's screen shows that is not stored.

Urgency badges and the four stat tiles are derived at read time. The teacher's
view of "done" is deliberately generous: once they have submitted, the ball is
with an administrator, so a submission awaiting review shows as done rather
than as outstanding work. Only a *returned* submission comes back to them.
"""

from datetime import date

from step import constants


def _outstanding(status: str) -> bool:
    return status in {constants.STATUS_NOT_STARTED, constants.STATUS_RETURNED}


def urgency_of(obligation, today: date | None = None) -> str:
    today = today or date.today()

    if not _outstanding(obligation.status):
        return constants.URGENCY_DONE

    days = (obligation.due_date - today).days
    if days < 0:
        return constants.URGENCY_OVERDUE
    if days == 0:
        return constants.URGENCY_DUE_TODAY
    if days <= constants.DUE_SOON_DAYS:
        return constants.URGENCY_DUE_SOON
    return constants.URGENCY_SCHEDULED


def outstanding_for(educator):
    return educator.obligations.filter(
        status__in=[constants.STATUS_NOT_STARTED, constants.STATUS_RETURNED]
    ).select_related("type")


def next_action(educator, today: date | None = None):
    """The single most urgent thing, for the "what do I do now" panel (spec §7.1)."""
    return outstanding_for(educator).order_by("due_date").first()


def teacher_tiles(educator, today: date | None = None) -> dict:
    """The four figures across the top of the teacher's home."""
    today = today or date.today()
    obligations = list(educator.obligations.all())

    active = sum(1 for o in obligations if _outstanding(o.status))
    completed = sum(1 for o in obligations if o.status in constants.SETTLED_STATUSES)
    due_this_month = sum(
        1 for o in obligations
        if _outstanding(o.status)
        and o.due_date.year == today.year
        and o.due_date.month == today.month
    )
    total = len(obligations)
    progress = round(completed * 100 / total) if total else 0

    return {
        "active": active,
        "due_this_month": due_this_month,
        "completed": completed,
        "progress_percent": progress,
    }
```

- [ ] **Step 4: Run tests, then commit**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_urgency -v 2`
Expected: PASS — 11 tests OK

```bash
git add step
git commit -m "Derive urgency badges and teacher stat tiles at read time"
```

---

## Phase 4 — Submissions, review and analytics

### Task 13: Submission and evidence models

**Files:**
- Create: `step/models/submissions.py`
- Modify: `step/models/__init__.py`
- Test: `step/tests/test_submission_models.py`

- [ ] **Step 1: Write the failing test**

```python
# step/tests/test_submission_models.py
"""Evidence is a list, not a field (spec §5.7), and revisions never overwrite
(spec §5.8). The revision history is the audit trail and the data behind
Feedback & Correction.
"""

import tempfile
from datetime import date

from django.test import TestCase, override_settings

from step import constants
from step.models import (
    Educator, Evidence, Obligation, ObligationType, Region, Submission,
)

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class SubmissionTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY,
        )
        self.obligation = Obligation.objects.create(
            type=self.type, educator=self.educator, period_kind=constants.PERIOD_MONTH,
            period_start=date(2026, 5, 1), due_date=date(2026, 5, 27),
        )

    def test_a_submission_starts_at_revision_one(self):
        submission = Submission.objects.create(obligation=self.obligation)
        self.assertEqual(submission.revision, 1)

    def test_one_submission_per_revision(self):
        from django.db import IntegrityError
        Submission.objects.create(obligation=self.obligation, revision=1)
        with self.assertRaises(IntegrityError):
            Submission.objects.create(obligation=self.obligation, revision=1)

    def test_latest_returns_the_highest_revision(self):
        Submission.objects.create(obligation=self.obligation, revision=1)
        second = Submission.objects.create(obligation=self.obligation, revision=2)
        self.assertEqual(self.obligation.latest_submission, second)

    def test_a_submission_carries_many_evidence_items(self):
        submission = Submission.objects.create(obligation=self.obligation)
        Evidence.objects.create(
            submission=submission, kind=constants.EVIDENCE_LINK_KIND, url="https://drive.example/1"
        )
        Evidence.objects.create(
            submission=submission, kind=constants.EVIDENCE_LINK_KIND, url="https://drive.example/2"
        )
        self.assertEqual(submission.evidence.count(), 2)

    def test_self_reported_evaluation_fields_default_empty(self):
        submission = Submission.objects.create(obligation=self.obligation)
        self.assertIsNone(submission.director_rating)
        self.assertEqual(submission.director_name, "")
        self.assertEqual(submission.outcome, "")

    def test_self_reported_fields_accept_the_two_mockup_signals(self):
        """The star rating and the binary outcome are separate signals (spec §6)."""
        submission = Submission.objects.create(
            obligation=self.obligation,
            director_rating=4,
            director_name="John Dela Cruz",
            outcome=constants.OUTCOME_SATISFACTORY_OR_BETTER,
        )
        submission.refresh_from_db()
        self.assertEqual(submission.director_rating, 4)
        self.assertEqual(submission.outcome, constants.OUTCOME_SATISFACTORY_OR_BETTER)

    def test_str_names_the_obligation_and_revision(self):
        submission = Submission.objects.create(obligation=self.obligation)
        self.assertIn("rev 1", str(submission))
```

- [ ] **Step 2: Add the outcome constants**

Append to `step/constants.py`:

```python
# --- Self-reported evaluation (spec §5.10) --------------------------------
# The director never logs in, so these are transcribed by the teacher and
# verified only by the photographed stamp. Anything rendering them MUST label
# them as self-reported.
OUTCOME_SATISFACTORY_OR_BETTER = "satisfactory_or_better"
OUTCOME_NEEDS_IMPROVEMENT = "needs_improvement"

OUTCOME_CHOICES = [
    (OUTCOME_SATISFACTORY_OR_BETTER, "Received Satisfactory or Better"),
    (OUTCOME_NEEDS_IMPROVEMENT, "Received Needs Improvement"),
]

#: Director star rating, 1-5, as drawn in the client mockup.
DIRECTOR_RATING_CHOICES = [(n, str(n)) for n in range(1, 6)]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_submission_models -v 2`
Expected: FAIL — `ImportError: cannot import name 'Submission' from 'step.models'`

- [ ] **Step 4: Write the models**

```python
# step/models/submissions.py
"""What a teacher hands in, and what an administrator says about it.

Two decisions are load-bearing:

* **Evidence is a list.** The monthly report needs both the form data and the
  photographed stamp, so one submission carries many items (spec §5.7).
* **Revisions never overwrite.** A returned submission that is resubmitted
  becomes revision 2; revision 1 stays. That history is the only record of what
  was originally sent, and it cannot be reconstructed (spec §5.8).

The director's rating, name, date and comments are captured here but are
**self-reported** — no Uzbek staff hold accounts, so the teacher transcribes
them and the stamped photograph is the only verification (spec §5.10).
"""

from django.conf import settings
from django.db import models

from step import constants
from step.models.obligations import Obligation


class Submission(models.Model):
    obligation = models.ForeignKey(Obligation, on_delete=models.CASCADE, related_name="submissions")
    revision = models.PositiveSmallIntegerField(default=1)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True, help_text="Anything the teacher wants to say.")

    # --- Self-reported evaluation (spec §5.10) ---------------------------
    director_rating = models.PositiveSmallIntegerField(
        null=True, blank=True, choices=constants.DIRECTOR_RATING_CHOICES,
        help_text="SELF-REPORTED. Transcribed by the teacher from the stamped paper.",
    )
    director_name = models.CharField(max_length=200, blank=True, help_text="SELF-REPORTED.")
    director_comments = models.TextField(blank=True, help_text="SELF-REPORTED.")
    evaluation_date = models.DateField(null=True, blank=True, help_text="SELF-REPORTED.")
    outcome = models.CharField(
        max_length=32, blank=True, choices=constants.OUTCOME_CHOICES,
        help_text="SELF-REPORTED. The binary outcome radio from the client mockup.",
    )

    # --- Review outcome ---------------------------------------------------
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="step_reviews",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_comment = models.TextField(
        blank=True, help_text="Shown to the teacher under Feedback & Correction when returned.",
    )

    class Meta:
        ordering = ["obligation", "-revision"]
        constraints = [
            models.UniqueConstraint(
                fields=["obligation", "revision"], name="step_submission_revision_unique"
            ),
        ]
        indexes = [models.Index(fields=["submitted_at"])]

    def __str__(self) -> str:
        return f"{self.obligation.display_name} rev {self.revision}"


class Evidence(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="evidence")
    kind = models.CharField(max_length=8, choices=constants.EVIDENCE_KIND_CHOICES)
    url = models.URLField(blank=True, max_length=1000)
    file = models.FileField(upload_to="step/evidence/%Y/%m/", blank=True)
    caption = models.CharField(max_length=200, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["submission", "uploaded_at"]

    def __str__(self) -> str:
        return self.caption or self.url or (self.file.name if self.file else f"Evidence {self.pk}")
```

- [ ] **Step 5: Add `latest_submission` to `Obligation`**

In `step/models/obligations.py`, add to the `Obligation` class:

```python
    @property
    def latest_submission(self):
        """The current revision, or None. Earlier revisions stay in `submissions`."""
        return self.submissions.order_by("-revision").first()
```

- [ ] **Step 6: Update re-exports, migrate, test, commit**

Add to `step/models/__init__.py`:

```python
from step.models.submissions import Evidence, Submission
```

and add `"Evidence"`, `"Submission"` to `__all__`.

Run: `.venv\Scripts\python.exe manage.py makemigrations step`
Run: `.venv\Scripts\python.exe manage.py migrate`
Run: `.venv\Scripts\python.exe manage.py test step.tests.test_submission_models -v 2`
Expected: PASS — 7 tests OK

```bash
git add step
git commit -m "Add submissions with revisions and list-valued evidence"
```

---

### Task 14: The submit / accept / return workflow

**Files:**
- Create: `step/workflow.py`
- Test: `step/tests/test_workflow.py`

- [ ] **Step 1: Write the failing test**

```python
# step/tests/test_workflow.py
"""State transitions live in one module so no view can invent its own.

The rules that matter: evidence requirements are enforced at submit time
(spec §5.7); a type with requires_review=False accepts immediately (spec §5.9);
returning sends the obligation back to the teacher and resubmitting bumps the
revision rather than editing history (spec §5.8).
"""

import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from step import constants, workflow
from step.models import Educator, Obligation, ObligationType, Region, Submission

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class SubmitTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.user = get_user_model().objects.create_user("maria", password="x")
        self.educator.user = self.user
        self.educator.save()

    def make_obligation(self, evidence_spec, requires_review=False, min_count=1):
        obligation_type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=evidence_spec,
            requires_review=requires_review, min_count=min_count,
        )
        return Obligation.objects.create(
            type=obligation_type, educator=self.educator, period_kind=constants.PERIOD_MONTH,
            period_start=date(2026, 5, 1), due_date=date(2026, 5, 27),
        )

    def test_submitting_with_no_evidence_when_none_is_required_succeeds(self):
        obligation = self.make_obligation(constants.EVIDENCE_NONE)
        submission = workflow.submit(obligation, user=self.user, evidence=[])
        obligation.refresh_from_db()
        self.assertEqual(submission.revision, 1)
        self.assertEqual(obligation.status, constants.STATUS_ACCEPTED)

    def test_a_link_requirement_rejects_a_file_only_submission(self):
        obligation = self.make_obligation(constants.EVIDENCE_LINK)
        with self.assertRaises(workflow.EvidenceRequired):
            workflow.submit(
                obligation, user=self.user,
                evidence=[{"kind": constants.EVIDENCE_FILE_KIND, "file": None, "caption": "x"}],
            )

    def test_either_accepts_a_link_alone(self):
        obligation = self.make_obligation(constants.EVIDENCE_EITHER)
        submission = workflow.submit(
            obligation, user=self.user,
            evidence=[{"kind": constants.EVIDENCE_LINK_KIND, "url": "https://x.example"}],
        )
        self.assertEqual(submission.evidence.count(), 1)

    def test_both_requires_a_link_and_a_file(self):
        obligation = self.make_obligation(constants.EVIDENCE_BOTH)
        with self.assertRaises(workflow.EvidenceRequired):
            workflow.submit(
                obligation, user=self.user,
                evidence=[{"kind": constants.EVIDENCE_LINK_KIND, "url": "https://x.example"}],
            )

    def test_min_count_is_enforced(self):
        obligation = self.make_obligation(constants.EVIDENCE_LINK, min_count=2)
        with self.assertRaises(workflow.EvidenceRequired):
            workflow.submit(
                obligation, user=self.user,
                evidence=[{"kind": constants.EVIDENCE_LINK_KIND, "url": "https://x.example"}],
            )

    def test_a_type_requiring_review_lands_in_the_queue(self):
        obligation = self.make_obligation(constants.EVIDENCE_NONE, requires_review=True)
        workflow.submit(obligation, user=self.user, evidence=[])
        obligation.refresh_from_db()
        self.assertEqual(obligation.status, constants.STATUS_SUBMITTED)

    def test_self_reported_evaluation_is_stored_on_the_submission(self):
        obligation = self.make_obligation(constants.EVIDENCE_NONE, requires_review=True)
        submission = workflow.submit(
            obligation, user=self.user, evidence=[],
            evaluation={
                "director_rating": 4,
                "director_name": "John Dela Cruz",
                "outcome": constants.OUTCOME_SATISFACTORY_OR_BETTER,
            },
        )
        self.assertEqual(submission.director_rating, 4)
        self.assertEqual(submission.outcome, constants.OUTCOME_SATISFACTORY_OR_BETTER)

    def test_submitting_an_already_accepted_obligation_is_refused(self):
        obligation = self.make_obligation(constants.EVIDENCE_NONE)
        workflow.submit(obligation, user=self.user, evidence=[])
        with self.assertRaises(workflow.InvalidTransition):
            workflow.submit(obligation, user=self.user, evidence=[])


@override_settings(MEDIA_ROOT=MEDIA)
class ReviewTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.educator = Educator.objects.create(full_name="Maria Santos", region=self.region)
        self.teacher = get_user_model().objects.create_user("maria", password="x")
        self.educator.user = self.teacher
        self.educator.save()
        self.admin = get_user_model().objects.create_user("admin2", password="x")

        obligation_type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
            requires_review=True,
        )
        self.obligation = Obligation.objects.create(
            type=obligation_type, educator=self.educator, period_kind=constants.PERIOD_MONTH,
            period_start=date(2026, 5, 1), due_date=date(2026, 5, 27),
        )
        self.submission = workflow.submit(self.obligation, user=self.teacher, evidence=[])

    def test_accepting_settles_the_obligation(self):
        workflow.accept(self.submission, reviewer=self.admin)
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_ACCEPTED)
        self.assertEqual(self.submission.reviewed_by, self.admin)
        self.assertIsNotNone(self.submission.reviewed_at)

    def test_returning_sends_it_back_with_a_comment(self):
        workflow.retur_n = None  # guard against a typo'd name in implementation
        workflow.return_for_correction(
            self.submission, reviewer=self.admin, comment="Stamp not visible."
        )
        self.obligation.refresh_from_db()
        self.submission.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_RETURNED)
        self.assertEqual(self.submission.review_comment, "Stamp not visible.")

    def test_returning_without_a_comment_is_refused(self):
        with self.assertRaises(ValueError):
            workflow.return_for_correction(self.submission, reviewer=self.admin, comment="  ")

    def test_resubmitting_after_a_return_bumps_the_revision(self):
        workflow.return_for_correction(self.submission, reviewer=self.admin, comment="Redo")
        second = workflow.submit(self.obligation, user=self.teacher, evidence=[])
        self.assertEqual(second.revision, 2)
        self.assertEqual(Submission.objects.filter(obligation=self.obligation).count(), 2)

    def test_the_first_revision_survives_a_resubmission(self):
        workflow.return_for_correction(self.submission, reviewer=self.admin, comment="Redo")
        workflow.submit(self.obligation, user=self.teacher, evidence=[])
        first = Submission.objects.get(obligation=self.obligation, revision=1)
        self.assertEqual(first.review_comment, "Redo")

    def test_accepting_an_already_accepted_submission_is_refused(self):
        workflow.accept(self.submission, reviewer=self.admin)
        with self.assertRaises(workflow.InvalidTransition):
            workflow.accept(self.submission, reviewer=self.admin)


class ReviewQueueTests(TestCase):
    def test_the_queue_holds_only_submissions_awaiting_a_decision(self):
        region = Region.objects.create(name="Samarkand", code="samarkand")
        educator = Educator.objects.create(full_name="Maria Santos", region=region)
        needs = ObligationType.objects.create(
            name_template="Needs review", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
            requires_review=True,
        )
        auto = ObligationType.objects.create(
            name_template="Auto accepted", category=constants.CATEGORY_OTHER,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
        )
        for obligation_type in (needs, auto):
            obligation = Obligation.objects.create(
                type=obligation_type, educator=educator, period_kind=constants.PERIOD_MONTH,
                period_start=date(2026, 5, 1), due_date=date(2026, 5, 27),
            )
            workflow.submit(obligation, user=None, evidence=[])

        queue = workflow.review_queue()
        self.assertEqual(queue.count(), 1)
        self.assertEqual(queue.first().obligation.type, needs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_workflow -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'step.workflow'`

- [ ] **Step 3: Write the workflow**

```python
# step/workflow.py
"""The only place obligation status changes.

Centralised so that no view, admin action or management command can invent its
own transition. Everything that writes `Obligation.status` goes through here.
"""

from django.db import transaction
from django.utils import timezone

from step import constants
from step.models import Evidence, Obligation, Submission


class EvidenceRequired(Exception):
    """The submission does not satisfy the type's evidence_spec."""


class InvalidTransition(Exception):
    """The requested change is not legal from the current status."""


def _check_evidence(obligation_type, evidence_items):
    """Raise EvidenceRequired unless the items satisfy the type.

    Messages are written for a person, not a developer: they say what to do
    next, per spec §7.1.
    """
    spec = obligation_type.evidence_spec
    if spec == constants.EVIDENCE_NONE:
        return

    links = [e for e in evidence_items if e.get("kind") == constants.EVIDENCE_LINK_KIND]
    files = [e for e in evidence_items if e.get("kind") == constants.EVIDENCE_FILE_KIND]
    minimum = obligation_type.min_count

    if spec == constants.EVIDENCE_LINK and len(links) < minimum:
        raise EvidenceRequired(f"Please add {minimum} link(s) before submitting.")
    if spec == constants.EVIDENCE_FILE and len(files) < minimum:
        raise EvidenceRequired(f"Please attach {minimum} file(s) before submitting.")
    if spec == constants.EVIDENCE_EITHER and len(evidence_items) < minimum:
        raise EvidenceRequired(f"Please add {minimum} link(s) or file(s) before submitting.")
    if spec == constants.EVIDENCE_BOTH and (len(links) < minimum or len(files) < minimum):
        raise EvidenceRequired(
            f"Please add {minimum} link(s) and attach {minimum} file(s) before submitting."
        )


@transaction.atomic
def submit(obligation: Obligation, *, user, evidence, evaluation=None) -> Submission:
    """Record a submission, creating a new revision if this is a resubmission."""
    if obligation.status not in {constants.STATUS_NOT_STARTED, constants.STATUS_RETURNED}:
        raise InvalidTransition(
            f"{obligation.display_name} is {obligation.status}; it cannot be submitted again."
        )

    evidence = list(evidence or [])
    _check_evidence(obligation.type, evidence)

    previous = obligation.submissions.order_by("-revision").first()
    revision = (previous.revision + 1) if previous else 1

    fields = {"obligation": obligation, "revision": revision, "submitted_by": user}
    fields.update(evaluation or {})
    submission = Submission.objects.create(**fields)

    for item in evidence:
        Evidence.objects.create(
            submission=submission,
            kind=item.get("kind", constants.EVIDENCE_LINK_KIND),
            url=item.get("url", "") or "",
            file=item.get("file") or None,
            caption=item.get("caption", "") or "",
        )

    if obligation.type.requires_review:
        obligation.status = constants.STATUS_SUBMITTED
    else:
        obligation.status = constants.STATUS_ACCEPTED
    obligation.save(update_fields=["status"])

    return submission


@transaction.atomic
def accept(submission: Submission, *, reviewer) -> Submission:
    obligation = submission.obligation
    if obligation.status not in constants.AWAITING_REVIEW_STATUSES:
        raise InvalidTransition(f"{obligation.display_name} is not awaiting review.")

    submission.reviewed_by = reviewer
    submission.reviewed_at = timezone.now()
    submission.save(update_fields=["reviewed_by", "reviewed_at"])

    obligation.status = constants.STATUS_ACCEPTED
    obligation.save(update_fields=["status"])
    return submission


@transaction.atomic
def return_for_correction(submission: Submission, *, reviewer, comment: str) -> Submission:
    """Send it back. A comment is mandatory — "returned" with no reason is useless."""
    if not comment or not comment.strip():
        raise ValueError("A comment is required when returning a submission.")

    obligation = submission.obligation
    if obligation.status not in constants.AWAITING_REVIEW_STATUSES:
        raise InvalidTransition(f"{obligation.display_name} is not awaiting review.")

    submission.reviewed_by = reviewer
    submission.reviewed_at = timezone.now()
    submission.review_comment = comment.strip()
    submission.save(update_fields=["reviewed_by", "reviewed_at", "review_comment"])

    obligation.status = constants.STATUS_RETURNED
    obligation.save(update_fields=["status"])
    return submission


def review_queue():
    """Submissions waiting for an administrator's decision."""
    return (
        Submission.objects.filter(obligation__status__in=constants.AWAITING_REVIEW_STATUSES)
        .select_related("obligation", "obligation__type", "obligation__educator")
        .order_by("submitted_at")
    )


def feedback_for(educator):
    """Returned submissions the teacher still needs to act on."""
    return (
        Submission.objects.filter(
            obligation__educator=educator, obligation__status=constants.STATUS_RETURNED
        )
        .select_related("obligation", "obligation__type")
        .order_by("-reviewed_at")
    )
```

Note: the test contains the line `workflow.retur_n = None`, which merely asserts the module is importable and writable before calling `return_for_correction`. Leave it; it costs nothing and catches a misnamed function early.

- [ ] **Step 4: Run tests, then commit**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_workflow -v 2`
Expected: PASS — 15 tests OK

```bash
git add step
git commit -m "Add the submit, accept and return workflow with evidence rules"
```

---

### Task 15: Analytics aggregates

Nine functions returning plain dictionaries. No new models, no caching (spec §6).

**Files:**
- Create: `step/analytics.py`
- Test: `step/tests/test_analytics.py`

- [ ] **Step 1: Write the failing test**

```python
# step/tests/test_analytics.py
"""The metric definitions in spec §6.1 are normative — these tests are what
makes them so. In particular "Pending" and "Not started" are REPORTING
categories derived from the due date, and are not the stored `not_started`
status.
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from step import analytics, constants, workflow
from step.models import Educator, Obligation, ObligationType, Region

PERIOD = date(2026, 5, 1)


class AnalyticsTests(TestCase):
    def setUp(self):
        self.tashkent = Region.objects.create(name="Tashkent City", code="tashkent-city", is_city=True)
        self.samarkand = Region.objects.create(name="Samarkand", code="samarkand")
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
            requires_review=True,
        )
        self.user = get_user_model().objects.create_user("maria", password="x")

    def make(self, region, due=date(2026, 5, 27)):
        educator = Educator.objects.create(
            full_name=f"Teacher {Educator.objects.count() + 1}", region=region
        )
        return Obligation.objects.create(
            type=self.type, educator=educator, period_kind=constants.PERIOD_MONTH,
            period_start=PERIOD, due_date=due,
        )

    def test_teachers_by_region_counts_active_educators(self):
        self.make(self.tashkent)
        self.make(self.tashkent)
        self.make(self.samarkand)
        rows = analytics.teachers_by_region()
        by_name = {r["region"]: r["count"] for r in rows}
        self.assertEqual(by_name["Tashkent City"], 2)
        self.assertEqual(by_name["Samarkand"], 1)

    def test_teachers_by_region_is_sorted_largest_first(self):
        self.make(self.samarkand)
        self.make(self.tashkent)
        self.make(self.tashkent)
        self.assertEqual(analytics.teachers_by_region()[0]["region"], "Tashkent City")

    def test_submission_status_splits_submitted_pending_and_not_started(self):
        submitted = self.make(self.tashkent)
        workflow.submit(submitted, user=self.user, evidence=[])
        self.make(self.tashkent, due=date(2026, 5, 27))   # pending: due later
        self.make(self.samarkand, due=date(2026, 5, 1))   # not started: due passed

        status = analytics.submission_status(PERIOD, today=date(2026, 5, 20))
        self.assertEqual(status["total"], 3)
        self.assertEqual(status["submitted"], 1)
        self.assertEqual(status["pending"], 1)
        self.assertEqual(status["not_started"], 1)

    def test_submission_status_percentages_are_rounded_and_sum_sensibly(self):
        for _ in range(4):
            self.make(self.tashkent)
        workflow.submit(Obligation.objects.first(), user=self.user, evidence=[])
        status = analytics.submission_status(PERIOD, today=date(2026, 5, 20))
        self.assertEqual(status["submitted_percent"], 25.0)

    def test_submission_status_with_no_obligations_does_not_divide_by_zero(self):
        status = analytics.submission_status(PERIOD, today=date(2026, 5, 20))
        self.assertEqual(status["total"], 0)
        self.assertEqual(status["submitted_percent"], 0.0)

    def test_rating_distribution_is_flagged_self_reported(self):
        obligation = self.make(self.tashkent)
        workflow.submit(
            obligation, user=self.user, evidence=[], evaluation={"director_rating": 5}
        )
        result = analytics.rating_distribution(PERIOD)
        self.assertTrue(result["self_reported"])
        self.assertEqual(result["counts"][5], 1)
        self.assertEqual(result["counts"][3], 0)

    def test_outcome_distribution_is_flagged_self_reported(self):
        obligation = self.make(self.tashkent)
        workflow.submit(
            obligation, user=self.user, evidence=[],
            evaluation={"outcome": constants.OUTCOME_NEEDS_IMPROVEMENT},
        )
        result = analytics.outcome_distribution(PERIOD)
        self.assertTrue(result["self_reported"])
        self.assertEqual(result["counts"][constants.OUTCOME_NEEDS_IMPROVEMENT], 1)

    def test_timeliness_counts_on_time_and_late_by_the_due_date(self):
        early = self.make(self.tashkent, due=date(2030, 1, 1))
        late = self.make(self.samarkand, due=date(2020, 1, 1))
        workflow.submit(early, user=self.user, evidence=[])
        workflow.submit(late, user=self.user, evidence=[])

        result = analytics.timeliness(PERIOD)
        self.assertEqual(result["on_time"], 1)
        self.assertEqual(result["late"], 1)
        self.assertEqual(result["on_time_percent"], 50.0)

    def test_average_submission_time_is_in_days(self):
        obligation = self.make(self.tashkent)
        workflow.submit(obligation, user=self.user, evidence=[])
        result = analytics.timeliness(PERIOD)
        self.assertGreaterEqual(result["average_submission_days"], 0.0)

    def test_status_by_region_returns_one_row_per_region_with_teachers(self):
        self.make(self.tashkent)
        self.make(self.samarkand)
        rows = analytics.status_by_region(PERIOD, today=date(2026, 5, 20))
        self.assertEqual(len(rows), 2)
        self.assertIn("submitted", rows[0])
        self.assertIn("pending", rows[0])
        self.assertIn("not_started", rows[0])

    def test_submission_trend_is_cumulative_and_never_decreases(self):
        for _ in range(3):
            obligation = self.make(self.tashkent)
            workflow.submit(obligation, user=self.user, evidence=[])
        points = analytics.submission_trend(PERIOD)
        values = [p["cumulative_percent"] for p in points]
        self.assertEqual(values, sorted(values))
        self.assertLessEqual(values[-1], 100.0)

    def test_completeness_rate_counts_filled_evidence_slots(self):
        obligation_type = ObligationType.objects.create(
            name_template="With evidence", category=constants.CATEGORY_OTHER,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_LINK,
        )
        educator = Educator.objects.create(full_name="E", region=self.tashkent)
        obligation = Obligation.objects.create(
            type=obligation_type, educator=educator, period_kind=constants.PERIOD_MONTH,
            period_start=PERIOD, due_date=date(2026, 5, 27),
        )
        workflow.submit(
            obligation, user=self.user,
            evidence=[{"kind": constants.EVIDENCE_LINK_KIND, "url": "https://x.example"}],
        )
        self.assertEqual(analytics.completeness_rate(PERIOD), 100.0)

    def test_completeness_rate_with_no_submissions_is_zero(self):
        self.assertEqual(analytics.completeness_rate(PERIOD), 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_analytics -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'step.analytics'`

- [ ] **Step 3: Write the analytics module**

```python
# step/analytics.py
"""The nine administration dashboard figures.

Computed live. At roughly 2,012 educators these are trivial aggregates given
the indexes already declared on Obligation, and precomputing them would buy
nothing while introducing a cache-invalidation bug (spec §6).

The metric definitions here are normative — spec §6.1. Note especially that
"pending" and "not started" are REPORTING categories derived from the due date;
they are not the stored `not_started` status.

Every function that returns self-reported data sets `self_reported: True` in
its payload, because these charts reach a ministry and must be labelled
(spec §5.10).
"""

from datetime import date

from django.db.models import Count

from step import constants
from step.models import Educator, Evidence, Obligation, Region, Submission


def _percent(part: int, whole: int) -> float:
    return round(part * 100 / whole, 1) if whole else 0.0


def teachers_by_region():
    """Counts of active educators per region, largest first."""
    rows = (
        Educator.objects.filter(is_active=True, missing_from_last_import=False)
        .values("region__name")
        .annotate(count=Count("id"))
        .order_by("-count", "region__name")
    )
    return [{"region": r["region__name"], "count": r["count"]} for r in rows]


def _period_obligations(period_start: date):
    return Obligation.objects.filter(period_start=period_start)


def submission_status(period_start: date, today: date | None = None) -> dict:
    today = today or date.today()
    obligations = list(_period_obligations(period_start).only("status", "due_date"))

    total = len(obligations)
    submitted = sum(1 for o in obligations if o.status != constants.STATUS_NOT_STARTED)
    outstanding = [o for o in obligations if o.status == constants.STATUS_NOT_STARTED]
    pending = sum(1 for o in outstanding if o.due_date >= today)
    not_started = sum(1 for o in outstanding if o.due_date < today)

    return {
        "total": total,
        "submitted": submitted,
        "pending": pending,
        "not_started": not_started,
        "submitted_percent": _percent(submitted, total),
        "pending_percent": _percent(pending, total),
        "not_started_percent": _percent(not_started, total),
    }


def _latest_submissions(period_start: date):
    """The current revision of every submitted obligation in the period."""
    return Submission.objects.filter(obligation__period_start=period_start).order_by(
        "obligation_id", "-revision"
    ).distinct("obligation_id") if _supports_distinct_on() else _latest_submissions_portable(period_start)


def _supports_distinct_on() -> bool:
    """DISTINCT ON is Postgres-only; SQLite needs the portable path.

    The project runs SQLite today and Postgres later (spec §8), so both must
    work — otherwise the dashboard breaks on exactly the cutover it was
    designed for.
    """
    from django.db import connection
    return connection.vendor == "postgresql"


def _latest_submissions_portable(period_start: date):
    latest_ids = []
    seen = set()
    for submission in Submission.objects.filter(
        obligation__period_start=period_start
    ).order_by("obligation_id", "-revision").only("id", "obligation_id", "revision"):
        if submission.obligation_id in seen:
            continue
        seen.add(submission.obligation_id)
        latest_ids.append(submission.id)
    return Submission.objects.filter(id__in=latest_ids)


def rating_distribution(period_start: date) -> dict:
    """Director star ratings. SELF-REPORTED — see spec §5.10."""
    counts = {n: 0 for n in range(1, 6)}
    for submission in _latest_submissions(period_start).exclude(director_rating=None):
        counts[submission.director_rating] += 1
    total = sum(counts.values())
    return {
        "counts": counts,
        "percents": {n: _percent(c, total) for n, c in counts.items()},
        "total": total,
        "self_reported": True,
    }


def outcome_distribution(period_start: date) -> dict:
    """The binary outcome radio. SELF-REPORTED — see spec §5.10."""
    counts = {
        constants.OUTCOME_SATISFACTORY_OR_BETTER: 0,
        constants.OUTCOME_NEEDS_IMPROVEMENT: 0,
    }
    for submission in _latest_submissions(period_start).exclude(outcome=""):
        if submission.outcome in counts:
            counts[submission.outcome] += 1
    total = sum(counts.values())
    return {
        "counts": counts,
        "percents": {k: _percent(v, total) for k, v in counts.items()},
        "total": total,
        "self_reported": True,
    }


def timeliness(period_start: date) -> dict:
    """On-time vs late, and the average time taken. Spec §6.1 definitions."""
    on_time = late = 0
    durations = []

    for submission in _latest_submissions(period_start).select_related("obligation"):
        obligation = submission.obligation
        submitted_on = submission.submitted_at.date()
        if submitted_on <= obligation.due_date:
            on_time += 1
        else:
            late += 1
        durations.append((submission.submitted_at - obligation.opened_at).total_seconds() / 86400)

    total = on_time + late
    return {
        "on_time": on_time,
        "late": late,
        "on_time_percent": _percent(on_time, total),
        "late_percent": _percent(late, total),
        "average_submission_days": round(sum(durations) / len(durations), 1) if durations else 0.0,
    }


def status_by_region(period_start: date, today: date | None = None):
    """One row per region that has educators, for the stacked bar chart."""
    today = today or date.today()
    rows = []
    for region in Region.objects.filter(educators__isnull=False).distinct():
        obligations = list(
            _period_obligations(period_start).filter(educator__region=region).only("status", "due_date")
        )
        outstanding = [o for o in obligations if o.status == constants.STATUS_NOT_STARTED]
        rows.append({
            "region": region.name,
            "submitted": sum(1 for o in obligations if o.status != constants.STATUS_NOT_STARTED),
            "pending": sum(1 for o in outstanding if o.due_date >= today),
            "not_started": sum(1 for o in outstanding if o.due_date < today),
        })
    return sorted(rows, key=lambda r: -(r["submitted"] + r["pending"] + r["not_started"]))


def submission_trend(period_start: date):
    """Cumulative submission percentage across the period, one point per day."""
    from step.scheduling import period_end

    finish = period_end(period_start, constants.PERIOD_MONTH)
    total = _period_obligations(period_start).count()

    dates = sorted(
        s.submitted_at.date() for s in _latest_submissions(period_start).only("submitted_at")
    )

    points = []
    cumulative = 0
    index = 0
    day = period_start
    while day <= finish:
        while index < len(dates) and dates[index] <= day:
            cumulative += 1
            index += 1
        points.append({"date": day.isoformat(), "cumulative_percent": _percent(cumulative, total)})
        day = date.fromordinal(day.toordinal() + 1)
    return points


def completeness_rate(period_start: date) -> float:
    """Share of required evidence slots actually filled.

    PROVISIONAL definition — the client mockup does not define this figure and
    it needs confirmation (spec §6.1, open question 3).
    """
    required = filled = 0
    for submission in _latest_submissions(period_start).select_related("obligation__type"):
        obligation_type = submission.obligation.type
        if obligation_type.evidence_spec == constants.EVIDENCE_NONE:
            continue
        need = obligation_type.min_count
        if obligation_type.evidence_spec == constants.EVIDENCE_BOTH:
            need *= 2
        required += need
        filled += min(Evidence.objects.filter(submission=submission).count(), need)
    return _percent(filled, required)
```

- [ ] **Step 4: Run tests, then commit**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_analytics -v 2`
Expected: PASS — 13 tests OK

```bash
git add step
git commit -m "Add the nine dashboard aggregates with normative metric definitions"
```

---

## Phase 5 — Admin and configuration

### Task 16: Signup matching

The spreadsheet is the gatekeeper (spec §4.3). This is the service layer only — no form, no view, no template; those belong to the interface plan.

**Files:**
- Create: `step/signup.py`
- Test: `step/tests/test_signup.py`

- [ ] **Step 1: Write the failing test**

```python
# step/tests/test_signup.py
"""Self-signup matched against the roster (spec §4.3).

No mass invite email is sent, so there are no dead links and no 2,000-message
spam problem: the teacher signs up, and the sheet decides whether they are let
in. An unmatched signup is held for an administrator rather than silently
creating an educator.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from step import constants, roles, signup
from step.models import Educator, PendingSignup, Region


@override_settings(STEP_ROSTER_MATCH_KEYS=["email"])
class SignupTests(TestCase):
    def setUp(self):
        from django.core.management import call_command
        from io import StringIO
        call_command("seed_roles", stdout=StringIO())
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.maria = Educator.objects.create(
            full_name="Maria Santos", region=self.region, email="maria@example.com"
        )
        self.user = get_user_model().objects.create_user("maria", password="x")

    def test_a_matching_signup_links_the_user_and_grants_the_role(self):
        result = signup.claim(self.user, full_name="Maria Santos", email="maria@example.com")
        self.maria.refresh_from_db()
        self.assertTrue(result.matched)
        self.assertEqual(result.educator, self.maria)
        self.assertEqual(self.maria.user, self.user)
        self.assertTrue(roles.is_educator(self.user))

    def test_an_unmatched_signup_creates_a_pending_record_and_no_educator(self):
        before = Educator.objects.count()
        result = signup.claim(self.user, full_name="Nobody", email="nobody@example.com")
        self.assertFalse(result.matched)
        self.assertIsNone(result.educator)
        self.assertEqual(Educator.objects.count(), before)
        self.assertEqual(PendingSignup.objects.count(), 1)
        self.assertFalse(roles.is_educator(self.user))

    def test_claiming_a_roster_row_already_taken_by_someone_else_is_refused(self):
        other = get_user_model().objects.create_user("other", password="x")
        signup.claim(other, full_name="Maria Santos", email="maria@example.com")
        result = signup.claim(self.user, full_name="Maria Santos", email="maria@example.com")
        self.assertFalse(result.matched)
        self.assertIn("already", result.reason.lower())
        self.assertEqual(PendingSignup.objects.count(), 1)

    def test_reclaiming_the_same_row_by_the_same_user_is_idempotent(self):
        signup.claim(self.user, full_name="Maria Santos", email="maria@example.com")
        result = signup.claim(self.user, full_name="Maria Santos", email="maria@example.com")
        self.assertTrue(result.matched)
        self.assertEqual(PendingSignup.objects.count(), 0)

    def test_an_ambiguous_identity_becomes_pending_rather_than_a_wrong_match(self):
        Educator.objects.create(
            full_name="Maria Santos (duplicate)", region=self.region, email="maria@example.com"
        )
        result = signup.claim(self.user, full_name="Maria Santos", email="maria@example.com")
        self.assertFalse(result.matched)
        self.assertEqual(PendingSignup.objects.count(), 1)

    def test_resolving_a_pending_signup_attaches_the_user(self):
        signup.claim(self.user, full_name="Nobody", email="nobody@example.com")
        pending = PendingSignup.objects.get()
        signup.resolve_pending(pending, self.maria, self.user)
        self.maria.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual(self.maria.user, self.user)
        self.assertTrue(pending.resolved)
        self.assertTrue(roles.is_educator(self.user))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_signup -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'step.signup'`

- [ ] **Step 3: Write the service**

```python
# step/signup.py
"""Claiming a roster row at signup.

Uses `step.identity` — the same resolver the importer uses — so a teacher can
never sign up and create a duplicate of a row that already exists.

An unmatched or ambiguous signup produces a PendingSignup rather than an
Educator. Creating a roster row from a signup would make the spreadsheet stop
being the source of truth, which is the one thing this design relies on.
"""

from dataclasses import dataclass
from django.db import transaction

from step import constants, identity, roles
from step.models import Educator, PendingSignup


@dataclass
class ClaimResult:
    matched: bool
    educator: Educator | None = None
    pending: PendingSignup | None = None
    reason: str = ""


def _hold(user, full_name, email, passport_no, pinfl, reason) -> ClaimResult:
    pending = PendingSignup.objects.create(
        full_name=full_name, email=email or "", passport_no=passport_no or "",
        pinfl=pinfl or "", note=reason,
    )
    return ClaimResult(matched=False, pending=pending, reason=reason)


@transaction.atomic
def claim(user, *, full_name="", email="", passport_no="", pinfl="") -> ClaimResult:
    try:
        educator, _key = identity.resolve(email=email, passport_no=passport_no, pinfl=pinfl)
    except identity.AmbiguousIdentity as exc:
        return _hold(user, full_name, email, passport_no, pinfl, str(exc))

    if educator is None:
        return _hold(
            user, full_name, email, passport_no, pinfl,
            "No roster row matched these details.",
        )

    if educator.user_id and educator.user_id != user.pk:
        return _hold(
            user, full_name, email, passport_no, pinfl,
            "That roster row has already been claimed by another account.",
        )

    educator.user = user
    educator.save(update_fields=["user"])
    roles.assign(user, constants.ROLE_EDUCATOR)
    return ClaimResult(matched=True, educator=educator)


@transaction.atomic
def resolve_pending(pending: PendingSignup, educator: Educator, user) -> Educator:
    """An administrator decides which roster row a pending signup belongs to."""
    educator.user = user
    educator.save(update_fields=["user"])
    roles.assign(user, constants.ROLE_EDUCATOR)
    pending.resolved = True
    pending.save(update_fields=["resolved"])
    return educator
```

- [ ] **Step 4: Run tests, then commit**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_signup -v 2`
Expected: PASS — 6 tests OK

```bash
git add step
git commit -m "Match signups against the roster, holding unmatched ones for review"
```

---

### Task 17: Register everything in the Django admin

Until the STEP screens exist, the admin is the only way to look at any of this.

**Files:**
- Create: `step/admin.py`
- Test: `step/tests/test_admin.py`

- [ ] **Step 1: Write the failing test**

```python
# step/tests/test_admin.py
"""Every model must be browsable, because until the STEP interface exists the
admin is the only way to see what the importer and generator produced. This
mirrors the same test in the diagnostics app.

Personal identifiers must not appear in list views (spec §4.4).
"""

from django.apps import apps
from django.contrib import admin
from django.test import TestCase

from step.models import Educator


class AdminRegistrationTests(TestCase):
    def test_every_step_model_is_registered(self):
        unregistered = [
            model._meta.label
            for model in apps.get_app_config("step").get_models()
            if not admin.site.is_registered(model)
        ]
        self.assertEqual(unregistered, [], f"not browsable in the admin: {unregistered}")


class PersonalIdentifierTests(TestCase):
    def test_passport_and_pinfl_are_not_in_the_educator_list_display(self):
        list_display = admin.site._registry[Educator].list_display
        self.assertNotIn("passport_no", list_display)
        self.assertNotIn("pinfl", list_display)

    def test_passport_and_pinfl_are_not_searchable(self):
        """Search terms end up in query strings and server logs (spec §4.4)."""
        search_fields = admin.site._registry[Educator].search_fields
        self.assertNotIn("passport_no", search_fields)
        self.assertNotIn("pinfl", search_fields)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_admin -v 2`
Expected: FAIL — several models unregistered

- [ ] **Step 3: Write the admin**

```python
# step/admin.py
"""Admin registration.

Until the STEP interface is built this is the only view onto the data, so every
model is registered. Passport numbers and PINFL are deliberately kept out of
list displays and search fields — search terms reach query strings and server
logs, and these are regulated identifiers (spec §4.4).
"""

from django.contrib import admin

from step.models import (
    AcademicYear, AliasMapping, District, Educator, Evidence, Obligation,
    ObligationType, PendingSignup, Region, RosterImport, School, Submission,
    Term, UnresolvedRow,
)


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("name", "name_uz", "code", "is_city")
    search_fields = ("name", "name_uz", "code")


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ("name", "region", "code")
    list_filter = ("region",)
    search_fields = ("name", "name_uz", "code")


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "district", "external_id")
    list_filter = ("district__region",)
    search_fields = ("name", "external_id")


@admin.register(Educator)
class EducatorAdmin(admin.ModelAdmin):
    # No passport_no or pinfl here, deliberately — spec §4.4.
    list_display = ("full_name", "email", "region", "school", "is_active", "missing_from_last_import")
    list_filter = ("region", "is_active", "missing_from_last_import")
    search_fields = ("full_name", "email")
    readonly_fields = ("created_at", "updated_at")


class UnresolvedRowInline(admin.TabularInline):
    model = UnresolvedRow
    extra = 0


@admin.register(RosterImport)
class RosterImportAdmin(admin.ModelAdmin):
    list_display = ("id", "imported_at", "row_count", "created_count", "updated_count", "unresolved_count")
    inlines = [UnresolvedRowInline]
    readonly_fields = ("imported_at",)


@admin.register(UnresolvedRow)
class UnresolvedRowAdmin(admin.ModelAdmin):
    list_display = ("roster_import", "row_number", "reason", "resolved")
    list_filter = ("resolved",)


@admin.register(AliasMapping)
class AliasMappingAdmin(admin.ModelAdmin):
    list_display = ("kind", "raw_value", "region", "district", "school")
    list_filter = ("kind",)
    search_fields = ("raw_value", "normalised")


@admin.register(PendingSignup)
class PendingSignupAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "submitted_at", "resolved")
    list_filter = ("resolved",)
    search_fields = ("full_name", "email")


class TermInline(admin.TabularInline):
    model = Term
    extra = 0


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ("label", "start", "end", "is_current")
    inlines = [TermInline]


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ("name", "year", "sequence", "start", "end")
    list_filter = ("year",)


@admin.register(ObligationType)
class ObligationTypeAdmin(admin.ModelAdmin):
    list_display = ("name_template", "category", "cadence", "evidence_spec", "requires_review", "is_active")
    list_filter = ("category", "cadence", "requires_review", "is_active")
    search_fields = ("name_template",)


@admin.register(Obligation)
class ObligationAdmin(admin.ModelAdmin):
    list_display = ("display_name", "educator", "due_date", "status", "due_date_overridden")
    list_filter = ("status", "type__category", "period_kind", "educator__region")
    search_fields = ("educator__full_name",)
    date_hierarchy = "due_date"


class EvidenceInline(admin.TabularInline):
    model = Evidence
    extra = 0


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("obligation", "revision", "submitted_at", "director_rating", "outcome", "reviewed_at")
    list_filter = ("outcome", "director_rating")
    inlines = [EvidenceInline]
    readonly_fields = ("submitted_at",)


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ("submission", "kind", "caption", "uploaded_at")
    list_filter = ("kind",)
```

- [ ] **Step 4: Run tests, then commit**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_admin -v 2`
Expected: PASS — 3 tests OK

```bash
git add step
git commit -m "Register every STEP model in the admin, keeping identifiers out of lists"
```

---

### Task 18: Make the database engine configurable

Spec §8 calls for Postgres. This task makes the switch a deployment setting rather than a code change, so the existing suite keeps running on SQLite.

**Files:**
- Modify: `config/settings.py`
- Modify: `requirements.txt`
- Test: `step/tests/test_settings.py`

- [ ] **Step 1: Write the failing test**

```python
# step/tests/test_settings.py
"""The database must be switchable without a code change (spec §8).

SQLite stays the default so the existing pre-STEP suite keeps running on a
machine with no Postgres. The cutover is a deployment step.
"""

import importlib

from django.test import SimpleTestCase


class DatabaseConfigTests(SimpleTestCase):
    def test_defaults_to_sqlite(self):
        from django.conf import settings
        self.assertIn("sqlite3", settings.DATABASES["default"]["ENGINE"])

    def test_postgres_is_selected_by_environment(self):
        import os
        from config import settings as settings_module

        previous = os.environ.get("TESTGEN_DB_ENGINE")
        os.environ["TESTGEN_DB_ENGINE"] = "postgres"
        try:
            reloaded = importlib.reload(settings_module)
            self.assertIn("postgresql", reloaded.DATABASES["default"]["ENGINE"])
        finally:
            if previous is None:
                os.environ.pop("TESTGEN_DB_ENGINE", None)
            else:
                os.environ["TESTGEN_DB_ENGINE"] = previous
            importlib.reload(settings_module)


class StepSettingsTests(SimpleTestCase):
    def test_roster_match_keys_is_a_list(self):
        from django.conf import settings
        self.assertIsInstance(settings.STEP_ROSTER_MATCH_KEYS, list)
        self.assertTrue(settings.STEP_ROSTER_MATCH_KEYS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_settings -v 2`
Expected: FAIL on `test_postgres_is_selected_by_environment` — the engine is hardcoded

- [ ] **Step 3: Replace the DATABASES block**

In `config/settings.py`, replace the existing `DATABASES` block with:

```python
# SQLite is the default so a developer machine, and the existing test suite,
# need no database server. Production sets TESTGEN_DB_ENGINE=postgres — see
# the spine spec §8. The cutover is a deployment step, never a code change.
if os.environ.get("TESTGEN_DB_ENGINE", "sqlite").strip().lower() in {"postgres", "postgresql"}:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("TESTGEN_DB_NAME", "testgen"),
            "USER": os.environ.get("TESTGEN_DB_USER", "testgen"),
            "PASSWORD": os.environ.get("TESTGEN_DB_PASSWORD", ""),
            "HOST": os.environ.get("TESTGEN_DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("TESTGEN_DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("TESTGEN_DB_PATH", BASE_DIR / "db.sqlite3"),
            "OPTIONS": {"init_command": "PRAGMA journal_mode=WAL;"},
        }
    }
```

Also update the module docstring's environment-variable list to mention `TESTGEN_DB_ENGINE`, `TESTGEN_DB_NAME`, `TESTGEN_DB_USER`, `TESTGEN_DB_PASSWORD`, `TESTGEN_DB_HOST`, `TESTGEN_DB_PORT` and `STEP_ROSTER_MATCH_KEYS`.

- [ ] **Step 4: Add the driver to requirements**

Append to `requirements.txt`:

```
psycopg[binary]>=3.2   # Postgres driver; only used when TESTGEN_DB_ENGINE=postgres
```

Do **not** install it as part of this task — it is not needed while SQLite is the default, and installing a binary wheel unattended is an unnecessary risk.

- [ ] **Step 5: Run tests, then commit**

Run: `.venv\Scripts\python.exe manage.py test step.tests.test_settings -v 2`
Expected: PASS — 3 tests OK

```bash
git add config/settings.py requirements.txt step
git commit -m "Make the database engine env-configurable, defaulting to SQLite"
```

---

### Task 19: Final verification

- [ ] **Step 1: Run the full project suite**

Run: `.venv\Scripts\python.exe manage.py test -v 2`
Expected: OK, with a total strictly greater than the baseline you measured, and **zero** failures or errors. If any pre-existing test broke, that is a regression introduced by this plan — fix it rather than accepting it.

- [ ] **Step 2: Verify the pipeline end to end against a real database**

```bash
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py seed_geography
.venv/Scripts/python.exe manage.py seed_roles
```

Expected: `Seeded 14 regions and ... districts.` and `Ensured 4 role groups.`

- [ ] **Step 3: Confirm the decoupling constraint holds**

Run: `grep -rn "diagnostics\|from bank\|from assembly\|from content" step/ --include=*.py`
Expected: **no matches.** Spec §9 forbids STEP importing from those apps, and them importing from STEP, until slice 3.

Run: `grep -rn "from step" diagnostics/ bank/ assembly/ content/ --include=*.py`
Expected: **no matches.**

- [ ] **Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "Verify the STEP spine end to end"
```

---

## What is deliberately not here

- **Any interface.** The teacher dashboard and administrator screens are specified in spec §7 and need the `frontend-design` skill plus human review of the visual result. They get their own plan.
- **The Monthly Reporting wizard.** Slice 2.
- **Assessments wiring.** Slice 3.
- **Notifications, calendar, resource library, search.** Explicitly out of slice 1.
- **The Postgres cutover itself.** Configuration exists; running it needs a server.
- **Access logging for personal identifiers.** Spec §4.4 requires reads of `passport_no`
  and `pinfl` to be logged. This plan implements the other two thirds of that requirement —
  they are kept out of list displays and out of search fields, so they never reach a query
  string or a server log — but the read-audit trail needs a decision about where audit
  records live, which is a question for the interface plan. **This is a known, deliberate
  gap, not an oversight.**

## Open questions carried forward from the spec

These do not block this plan, but they block later ones. They are listed in spec §10:
the roster sheet's real columns, what signup asks for, the definition of *data
completeness rate*, whether a registration source exists beyond the sheet, who staffs the
review queue, and the confirmed academic-year dates.

