# STEP Admin Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the administrator-facing screens for STEP — a dashboard led by an action queue,
a submission review workflow (accept/return), and a searchable teacher directory — over the
already-built and already-tested `step/analytics.py`, `step/workflow.py` and `step/roles.py`.

**Architecture:** A new, isolated slice: `step/admin_views.py`, `step/admin_urls.py`,
`templates/step/admin/*.html`. No existing file owned by another session (`step/views.py`,
`step/presentation.py`, `templates/step/base.html`, `static/css/step.css`, `step/urls.py`) is
modified by this plan except for the shared includes `_letterhead.html`/`_messages.html`, which
are read-only, and one `path("admin/", include("step.admin_urls"))` line that needs adding to
`step/urls.py` by whoever owns it (see Task 1).

**Tech Stack:** Django (function-based views, matching `step/views.py`'s existing style), Django's
test client, no JS framework — `<details>`/`<summary>` for progressive disclosure. All chart
rendering uses the primitives already built and browser-verified in `static/css/step.css` §17
(`.bars`, `.stack-rows`, `.donut`, `.trend`, the `.s-*` series classes) — this plan adds no new
CSS file and no new chart components.

**Spec:** `docs/superpowers/specs/2026-08-27-step-admin-dashboard-design.md`

---

## Before you start

1. This repo is a shared working directory with several other active Claude sessions. If anything
   below (class names, the letterhead's parameter names, `step.css` custom properties) doesn't
   match what you find in the actual files, the files are the source of truth — they may have
   moved since this plan was written. `templates/step/_letterhead.html` takes three optional
   context variables (`lh_who`, `lh_where`, `lh_ref`) and falls back to the teacher's own details
   if none are set — read it before Task 2.
2. Colour discipline, non-negotiable and checked by test in Task 4: `--stamp` and `--seal` (and
   their `.s-*` equivalents, which don't exist — there is deliberately no `.s-stamp`/`.s-seal`)
   mean *late* and *accepted* everywhere else in this system. Never use them as a chart series
   colour. Use `.s-quiet` for "not started", not `--stamp`.
3. The two rating/outcome widgets chart **self-reported** data (spec §5.10) — the director never
   logs in; the teacher transcribes a stamped rating. Every render of that data is labelled, via
   `.chart--selfreported` + `.chart__note`, with no exceptions.

---

### Task 1: Staff-only access control, and the URL module

**Files:**
- Create: `step/admin_views.py`
- Create: `step/admin_urls.py`
- Test: `step/tests/test_admin_views.py`

- [ ] **Step 1: Write the failing test**

```python
"""Admin-facing screens: the action-queue dashboard, the review workflow, and
the teacher directory. Gated to the three staff roles (spec §5.6); an
Educator or an anonymous visitor must never reach any of it.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from step import constants, roles
from step.models import Educator, Region


class AccessControlTests(TestCase):
    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        self.region = Region.objects.create(name="Samarkand", code="samarkand")

    def _staff(self, username, role=constants.ROLE_ADMIN):
        user = get_user_model().objects.create_user(username, password="pw")
        roles.assign(user, role)
        return user

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse("step:admin-dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_an_educator_is_forbidden(self):
        user = get_user_model().objects.create_user("maria", password="pw")
        roles.assign(user, constants.ROLE_EDUCATOR)
        Educator.objects.create(full_name="Maria Santos", region=self.region, user=user)
        self.client.login(username="maria", password="pw")
        response = self.client.get(reverse("step:admin-dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_a_signed_in_user_with_no_role_at_all_is_forbidden(self):
        get_user_model().objects.create_user("nobody", password="pw")
        self.client.login(username="nobody", password="pw")
        response = self.client.get(reverse("step:admin-dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_each_of_the_three_staff_roles_is_admitted(self):
        for i, role in enumerate(
            [constants.ROLE_ADMIN, constants.ROLE_PROGRAMME_ADMIN, constants.ROLE_SYSTEM_ADMIN]
        ):
            self._staff(f"staff{i}", role)
            self.client.login(username=f"staff{i}", password="pw")
            response = self.client.get(reverse("step:admin-dashboard"))
            self.assertEqual(response.status_code, 200, f"{role} was refused the dashboard")
            self.client.logout()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test step.tests.test_admin_views -v 2`
Expected: FAIL — `NoReverseMatch: Reverse for 'admin-dashboard' not found` (nothing exists yet).

- [ ] **Step 3: Write the decorator, a minimal dashboard view, and the URL module**

```python
"""Administration screens: the action-queue dashboard, the submission review
workflow, and the teacher directory.

This module owns no business logic. Every state change goes through
`step.workflow`; every figure comes from `step.analytics`. A view here is
allowed to query and to shape context for a template, and nothing else.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render

from step import roles


def staff_required(view):
    """Only the three staff roles reach anything in this module (spec §5.6).

    A plain 403 with words a confused administrator can act on — not a stack
    trace, not a silent bounce back to their own dashboard.
    """
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not roles.is_staff_role(request.user):
            return HttpResponseForbidden(
                "This area is for programme staff. If you believe this is a mistake, "
                "contact your System Administrator."
            )
        return view(request, *args, **kwargs)
    return wrapped


def _admin_chrome(request) -> dict:
    """Context every admin screen's shell needs — the admin equivalent of
    step/views.py's `_chrome`, kept separate because the two shells show
    different things (a staff member's name and role, not a teacher's school
    and file reference)."""
    return {
        "lh_who": request.user.get_username(),
        "lh_where": "Administration",
    }


@staff_required
def dashboard(request):
    context = {"nav": "dashboard"}
    context.update(_admin_chrome(request))
    return render(request, "step/admin/dashboard.html", context)
```

Create `step/admin_urls.py`:

```python
"""URLs for the administration screens, included from step/urls.py under
`admin/`. Kept in a separate module so the file that owns the teacher-facing
routes (step/urls.py, owned by another session working in parallel) only
ever needs one `include()` line added to it, never a merge of two people's
url patterns.
"""

from django.urls import path

from step import admin_views

urlpatterns = [
    path("admin/", admin_views.dashboard, name="admin-dashboard"),
]
```

**Coordination step (not a file edit in this repo checkout):** send whoever owns `step/urls.py`
this line to add once, near the existing `urlpatterns`:

```python
from django.urls import include
urlpatterns += [path("admin/", include("step.admin_urls"))]
```

Until that line lands, the real running app's `/step/admin/` 404s even though `step/admin_urls.py`
is correct — the test client in this plan's tests resolves URLs straight from
`ROOT_URLCONF`/app urlconfs, so this gap is easy to miss. Task 7, Step 6 has an explicit manual
check for it. If you have direct write access to `step/urls.py` yourself (no peer session owns
it), add the line directly instead of messaging anyone.

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test step.tests.test_admin_views -v 2`
Expected: PASS, all four tests in `AccessControlTests`.

- [ ] **Step 5: Commit**

```bash
git add step/admin_views.py step/admin_urls.py step/tests/test_admin_views.py
git commit -m "Add staff-only access control for the admin screens"
```

---

### Task 2: `base_admin.html` shell

**Files:**
- Create: `templates/step/base_admin.html`
- Create: `templates/step/admin/dashboard.html`

- [ ] **Step 1: Write the failing test**

Add to `step/tests/test_admin_views.py`:

```python
class DashboardShellTests(TestCase):
    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        user = get_user_model().objects.create_user("admin1", password="pw")
        roles.assign(user, constants.ROLE_ADMIN)
        self.client.login(username="admin1", password="pw")

    def test_dashboard_renders_the_letterhead_and_admin_rail(self):
        response = self.client.get(reverse("step:admin-dashboard"))
        self.assertContains(response, "STEP")
        self.assertContains(response, "Administration")

    def test_dashboard_shows_the_signed_in_staff_members_name(self):
        response = self.client.get(reverse("step:admin-dashboard"))
        self.assertContains(response, "admin1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test step.tests.test_admin_views.DashboardShellTests -v 2`
Expected: FAIL — `TemplateDoesNotExist: step/admin/dashboard.html`.

- [ ] **Step 3: Write `base_admin.html`**

Copy the `<head>` block verbatim from `templates/step/base.html` (fonts + `step.css` link) rather
than retyping it — it has changed more than once today and a hand-typed copy will drift. As of
this writing it is:

```django
{% load static %}<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{% block title %}STEP Administration{% endblock %}</title>

<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Commissioner:wght@400;500;600;700&family=Literata:ital,opsz,wght@0,7..72,400;0,7..72,600;1,7..72,400&family=PT+Mono&display=swap" rel="stylesheet">

<link rel="stylesheet" href="{% static 'css/step.css' %}">
</head>
<body>

<a class="skip-link" href="#sheet">Skip to the main content</a>

{% include "step/_letterhead.html" %}

<div class="shell">

  <nav class="rail" aria-label="Sections">
    <div class="rail__heading">Administration</div>
    <a class="rail__link" href="{% url 'step:admin-dashboard' %}" {% if nav == 'dashboard' %}aria-current="page"{% endif %}>Overview</a>
    <a class="rail__link" href="{% url 'step:admin-review-queue' %}" {% if nav == 'review' %}aria-current="page"{% endif %}>Review queue</a>
    <a class="rail__link" href="{% url 'step:admin-teachers' %}" {% if nav == 'teachers' %}aria-current="page"{% endif %}>Teachers</a>
  </nav>

  <main class="sheet" id="sheet">
    {% include "step/_messages.html" %}
    {% block content %}{% endblock %}
  </main>

</div>

</body>
</html>
```

`_letterhead.html` reads `lh_who`/`lh_where` from the context `_admin_chrome` already supplies
(Task 1) — no `with` clause needed on the `include`, it inherits the current context, matching
how `templates/step/base.html` uses it.

- [ ] **Step 4: Write `admin/dashboard.html` and add the two placeholder URLs**

```django
{% extends "step/base_admin.html" %}
{% block title %}Overview — STEP Administration{% endblock %}
{% block content %}
<h1>Overview</h1>
{% endblock %}
```

The rail links to `step:admin-review-queue` and `step:admin-teachers`, which don't have real
views until Tasks 5 and 6. `{% url %}` resolves at render time, so add working stub routes to
`step/admin_urls.py` now (fully functional code, not a placeholder — it renders the real
dashboard at both URLs until Tasks 5 and 6 replace it):

```python
from django.urls import path

from step import admin_views

urlpatterns = [
    path("admin/", admin_views.dashboard, name="admin-dashboard"),
    path("admin/review/", admin_views.dashboard, name="admin-review-queue"),
    path("admin/teachers/", admin_views.dashboard, name="admin-teachers"),
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python manage.py test step.tests.test_admin_views -v 2`
Expected: PASS — `DashboardShellTests` and `AccessControlTests` all green.

- [ ] **Step 6: Commit**

```bash
git add templates/step/base_admin.html templates/step/admin/dashboard.html step/admin_urls.py step/tests/test_admin_views.py
git commit -m "Add the admin shell and a rendering dashboard page"
```

---

### Task 3: Action queue and headline figure

**Files:**
- Modify: `step/admin_views.py`
- Modify: `templates/step/admin/dashboard.html`

- [ ] **Step 1: Write the failing test**

```python
from datetime import date

from step.models import Obligation, ObligationType


class ActionQueueTests(TestCase):
    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        user = get_user_model().objects.create_user("admin1", password="pw")
        roles.assign(user, constants.ROLE_ADMIN)
        self.client.login(username="admin1", password="pw")

        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
            requires_review=True,
        )

    def _obligation(self, due, status=constants.STATUS_NOT_STARTED):
        educator = Educator.objects.create(
            full_name=f"Teacher {Educator.objects.count() + 1}", region=self.region
        )
        return Obligation.objects.create(
            type=self.type, educator=educator, period_kind=constants.PERIOD_MONTH,
            period_start=date(2026, 5, 1), due_date=due, status=status,
        )

    def test_the_outstanding_count_reaches_the_dashboard(self):
        self._obligation(date(2026, 5, 27))
        self._obligation(date(2026, 5, 27))
        response = self.client.get(reverse("step:admin-dashboard") + "?period=2026-05")
        self.assertEqual(response.context["outstanding_count"], 2)

    def test_the_review_queue_count_reaches_the_dashboard(self):
        submitted = self._obligation(date(2026, 5, 27), status=constants.STATUS_SUBMITTED)
        from step.models import Submission
        Submission.objects.create(obligation=submitted, revision=1)
        response = self.client.get(reverse("step:admin-dashboard"))
        self.assertEqual(response.context["review_count"], 1)

    def test_headline_figures_come_from_submission_status(self):
        self._obligation(date(2026, 5, 27))
        response = self.client.get(reverse("step:admin-dashboard") + "?period=2026-05")
        self.assertEqual(response.context["headline"]["total"], 1)

    def test_the_action_queue_wording_is_on_the_page(self):
        self._obligation(date(2026, 5, 27))
        response = self.client.get(reverse("step:admin-dashboard") + "?period=2026-05")
        self.assertContains(response, "have not submitted")

    def test_a_malformed_period_is_a_404_not_a_500(self):
        response = self.client.get(reverse("step:admin-dashboard") + "?period=not-a-month")
        self.assertEqual(response.status_code, 404)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test step.tests.test_admin_views.ActionQueueTests -v 2`
Expected: FAIL — `KeyError: 'outstanding_count'`.

- [ ] **Step 3: Implement the period helper and dashboard context**

Add to `step/admin_views.py`:

```python
from datetime import date

from django.http import Http404

from step import analytics, constants, workflow
from step.models import Obligation


def _current_period(request) -> date:
    """The month the dashboard reports on. `?period=YYYY-MM`, defaulting to
    the current month. A malformed value 404s rather than silently showing
    the wrong month — a teacher-facing default (September) sitting under a
    ministry figure is worse than an obvious error page.
    """
    raw = request.GET.get("period")
    if not raw:
        return date.today().replace(day=1)
    try:
        year, month = raw.split("-")
        return date(int(year), int(month), 1)
    except (ValueError, TypeError) as exc:
        raise Http404("That is not a month this dashboard understands.") from exc


@staff_required
def dashboard(request):
    period = _current_period(request)
    headline = analytics.submission_status(period)
    outstanding_count = (
        Obligation.objects.filter(period_start=period, status=constants.STATUS_NOT_STARTED)
        .values("educator_id").distinct().count()
    )
    review_count = workflow.review_queue().count()

    context = {
        "nav": "dashboard",
        "period": period,
        "headline": headline,
        "outstanding_count": outstanding_count,
        "review_count": review_count,
    }
    context.update(_admin_chrome(request))
    return render(request, "step/admin/dashboard.html", context)
```

- [ ] **Step 4: Write the action queue and headline markup**

```django
{% extends "step/base_admin.html" %}
{% block title %}Overview — STEP Administration{% endblock %}
{% block content %}
<h1>Overview</h1>

<div class="block">
  {% if outstanding_count %}
  <p class="entry__title">
    <a href="{% url 'step:admin-teachers' %}?status=outstanding&period={{ period|date:'Y-m' }}">
      {{ outstanding_count }} teacher{{ outstanding_count|pluralize }} have not submitted for {{ period|date:"F Y" }}
    </a>
  </p>
  {% endif %}
  {% if review_count %}
  <p class="entry__title">
    <a href="{% url 'step:admin-review-queue' %}">
      {{ review_count }} submission{{ review_count|pluralize }} waiting for your review
    </a>
  </p>
  {% endif %}
  {% if not outstanding_count and not review_count %}
  <p>Nothing is waiting on you right now.</p>
  {% endif %}
</div>

<div class="record">
  <div class="record__cell">
    <div class="record__value">{{ headline.submitted_percent }}%</div>
    <div class="label">Submitted</div>
  </div>
  <div class="record__cell">
    <div class="record__value">{{ headline.pending }}</div>
    <div class="label">Pending</div>
  </div>
  <div class="record__cell">
    <div class="record__value">{{ headline.not_started }}</div>
    <div class="label">Not started</div>
  </div>
  <div class="record__cell">
    <div class="record__value">{{ headline.total }}</div>
    <div class="label">Total for {{ period|date:"F Y" }}</div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python manage.py test step.tests.test_admin_views -v 2`
Expected: PASS — all tests so far green.

- [ ] **Step 6: Commit**

```bash
git add step/admin_views.py templates/step/admin/dashboard.html step/tests/test_admin_views.py
git commit -m "Lead the admin dashboard with the action queue and a headline figure"
```

---

### Task 4: The eight analytics widgets, collapsed by default

Uses the chart primitives already committed to `static/css/step.css` §17 — `.bars`/`.bar`,
`.stack-rows`/`.stack-row`/`.stack`, `.donut`, `.trend`, `.legend`, `.chart`/`.chart--selfreported`,
and the `.s-violet`/`.s-teal`/`.s-ochre`/`.s-umber`/`.s-plum`/`.s-ink`/`.s-quiet` series classes.
All percentage and offset arithmetic is computed in the view, per the primitives' contract —
the templates only interpolate values, they never compute them.

**Files:**
- Modify: `step/admin_views.py`
- Modify: `templates/step/admin/dashboard.html`

- [ ] **Step 1: Write the failing test**

```python
class AnalyticsWidgetsTests(TestCase):
    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        user = get_user_model().objects.create_user("admin1", password="pw")
        roles.assign(user, constants.ROLE_ADMIN)
        self.client.login(username="admin1", password="pw")
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
            requires_review=True,
        )
        educator = Educator.objects.create(full_name="Teacher One", region=self.region)
        obligation = Obligation.objects.create(
            type=self.type, educator=educator, period_kind=constants.PERIOD_MONTH,
            period_start=date(2026, 5, 1), due_date=date(2026, 5, 27),
        )
        self.obligation = obligation

    def test_all_widget_context_keys_are_present(self):
        response = self.client.get(reverse("step:admin-dashboard") + "?period=2026-05")
        for key in [
            "region_bars", "rating_donut", "outcome_donut", "trend_points", "trend_width",
            "status_rows", "timeliness", "completeness_rate",
        ]:
            self.assertIn(key, response.context, f"{key} missing from dashboard context")

    def test_a_region_bar_carries_a_precomputed_percent(self):
        response = self.client.get(reverse("step:admin-dashboard") + "?period=2026-05")
        bars = response.context["region_bars"]
        self.assertEqual(bars[0]["percent"], 100.0)

    def test_self_reported_widgets_are_labelled_on_the_page(self):
        response = self.client.get(reverse("step:admin-dashboard") + "?period=2026-05")
        self.assertContains(response, "chart--selfreported")

    def test_donut_segments_have_dasharray_and_dashoffset(self):
        from step import workflow
        workflow.submit(
            self.obligation, user=get_user_model().objects.get(username="admin1"),
            evidence=[], evaluation={"director_rating": 5},
        )
        response = self.client.get(reverse("step:admin-dashboard") + "?period=2026-05")
        segment = response.context["rating_donut"][0]
        self.assertIn("dasharray", segment)
        self.assertIn("dashoffset", segment)

    def test_changing_the_period_changes_the_headline_and_the_widgets_together(self):
        may = self.client.get(reverse("step:admin-dashboard") + "?period=2026-05")
        june = self.client.get(reverse("step:admin-dashboard") + "?period=2026-06")
        self.assertEqual(may.context["headline"]["total"], 1)
        self.assertEqual(june.context["headline"]["total"], 0)
        self.assertNotEqual(len(may.context["trend_points"]), 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test step.tests.test_admin_views.AnalyticsWidgetsTests -v 2`
Expected: FAIL — `AssertionError: 'region_bars' not found in {...}`.

- [ ] **Step 3: Add the computation helpers and wire the widgets into the view**

Add to `step/admin_views.py`:

```python
def _region_bars(rows: list[dict]) -> list[dict]:
    """`analytics.teachers_by_region()`'s rows, with a 0-100 `percent` of the
    largest region added — `.bar__fill`'s width is an inline style per the
    primitive's contract, and that arithmetic belongs here, not in the
    template."""
    maximum = rows[0]["count"] if rows else 0
    return [
        {**row, "percent": round(row["count"] / maximum * 100, 1) if maximum else 0.0}
        for row in rows
    ]


def _status_rows(rows: list[dict]) -> list[dict]:
    """`analytics.status_by_region()`'s rows, with each of the three counts
    turned into a percentage of that row's own total, for `.stack__seg`
    widths."""
    out = []
    for row in rows:
        total = row["submitted"] + row["pending"] + row["not_started"]
        out.append({
            **row,
            "submitted_percent": round(row["submitted"] / total * 100, 1) if total else 0.0,
            "pending_percent": round(row["pending"] / total * 100, 1) if total else 0.0,
            "not_started_percent": round(row["not_started"] / total * 100, 1) if total else 0.0,
        })
    return out


def _donut_segments(parts: list[tuple]) -> list[dict]:
    """`parts` is `[(series_css_class, percent), ...]`. Returns the
    `stroke-dasharray`/`stroke-dashoffset` pairs the `.donut__seg` primitive
    needs. The circle's circumference is exactly 100 (r=15.915), so a segment
    covering `pct` percent of the circle is `dasharray="{pct} {100-pct}"`.
    Offsets start at 25 (12 o'clock) and chain around the circle — this is
    test-generator-16's verified contract for static/css/step.css §17, not an
    independent derivation.
    """
    segments = []
    offset = 25.0
    for series_class, pct in parts:
        segments.append({
            "series": series_class,
            "dasharray": f"{pct} {100 - pct}",
            "dashoffset": round(offset, 2),
        })
        offset = (offset - pct + 100) % 100
    return segments


def _trend_points(points: list[dict]) -> tuple[str, int]:
    """`analytics.submission_trend()`'s points, turned into an SVG
    `points="x,y"` attribute plus the `viewBox` width to pair with it. X is
    the raw day index (0, 1, 2, ...) and y is inverted (100 - percentage);
    `preserveAspectRatio="none"` stretches the box to fit its container, so
    there is no need to scale x to any particular unit.
    """
    coords = " ".join(
        f"{i},{100 - point['cumulative_percent']}" for i, point in enumerate(points)
    )
    width = max(len(points) - 1, 1)
    return coords, width


RATING_SERIES = [(5, "s-violet"), (4, "s-teal"), (3, "s-ochre"), (2, "s-umber"), (1, "s-plum")]
```

Extend `dashboard`'s context in `step/admin_views.py`:

```python
@staff_required
def dashboard(request):
    period = _current_period(request)
    headline = analytics.submission_status(period)
    outstanding_count = (
        Obligation.objects.filter(period_start=period, status=constants.STATUS_NOT_STARTED)
        .values("educator_id").distinct().count()
    )
    review_count = workflow.review_queue().count()

    rating = analytics.rating_distribution(period)
    outcome = analytics.outcome_distribution(period)
    trend_coords, trend_width = _trend_points(analytics.submission_trend(period))

    context = {
        "nav": "dashboard",
        "period": period,
        "headline": headline,
        "outstanding_count": outstanding_count,
        "review_count": review_count,
        "region_bars": _region_bars(analytics.teachers_by_region()),
        "rating_distribution": rating,
        "rating_donut": _donut_segments(
            [(cls, rating["percents"][n]) for n, cls in RATING_SERIES]
        ),
        "outcome_distribution": outcome,
        "outcome_donut": _donut_segments([
            ("s-teal", outcome["percents"][constants.OUTCOME_SATISFACTORY_OR_BETTER]),
            ("s-ochre", outcome["percents"][constants.OUTCOME_NEEDS_IMPROVEMENT]),
        ]),
        "trend_points": trend_coords,
        "trend_width": trend_width,
        "status_rows": _status_rows(analytics.status_by_region(period)),
        "timeliness": analytics.timeliness(period),
        "completeness_rate": analytics.completeness_rate(period),
    }
    context.update(_admin_chrome(request))
    return render(request, "step/admin/dashboard.html", context)
```

- [ ] **Step 4: Add the widgets to the template, collapsed by default**

Append inside `{% block content %}`, after the record strip from Task 3:

```django
<details class="widget-toggle">
  <summary>See the full breakdown</summary>

  <section class="chart">
    <h2>Teachers by region</h2>
    <div class="bars">
      {% for row in region_bars|slice:":8" %}
      <div class="bar s-teal">
        <span class="bar__label">{{ row.region }}</span>
        <span class="bar__track"><span class="bar__fill" style="width:{{ row.percent }}%"></span></span>
        <span class="bar__value">{{ row.count }}</span>
      </div>
      {% endfor %}
    </div>
    {% if region_bars|length > 8 %}
    <details><summary>Show all {{ region_bars|length }} regions</summary>
      <div class="bars">
        {% for row in region_bars|slice:"8:" %}
        <div class="bar s-teal">
          <span class="bar__label">{{ row.region }}</span>
          <span class="bar__track"><span class="bar__fill" style="width:{{ row.percent }}%"></span></span>
          <span class="bar__value">{{ row.count }}</span>
        </div>
        {% endfor %}
      </div>
    </details>
    {% endif %}
  </section>

  <section class="chart chart--selfreported">
    <h2>Performance overview, by director rating</h2>
    <div class="donut">
      <svg class="donut__svg" viewBox="0 0 42 42">
        <circle class="donut__ring" cx="21" cy="21" r="15.915"/>
        {% for seg in rating_donut %}
        <circle class="donut__seg {{ seg.series }}" cx="21" cy="21" r="15.915"
                stroke-dasharray="{{ seg.dasharray }}" stroke-dashoffset="{{ seg.dashoffset }}"/>
        {% endfor %}
      </svg>
      <div class="donut__centre">
        <span class="donut__figure">{{ rating_distribution.total }}</span>
        <span class="donut__caption">rated</span>
      </div>
    </div>
    <ul class="legend">
      <li class="legend__item s-violet"><span class="legend__swatch"></span>5 star: {{ rating_distribution.counts.5 }}</li>
      <li class="legend__item s-teal"><span class="legend__swatch"></span>4 star: {{ rating_distribution.counts.4 }}</li>
      <li class="legend__item s-ochre"><span class="legend__swatch"></span>3 star: {{ rating_distribution.counts.3 }}</li>
      <li class="legend__item s-umber"><span class="legend__swatch"></span>2 star: {{ rating_distribution.counts.2 }}</li>
      <li class="legend__item s-plum"><span class="legend__swatch"></span>1 star: {{ rating_distribution.counts.1 }}</li>
    </ul>
    <p class="chart__note">transcribed by teachers from the stamped paper.</p>
  </section>

  <section class="chart chart--selfreported">
    <h2>Outcome overview</h2>
    <div class="donut">
      <svg class="donut__svg" viewBox="0 0 42 42">
        <circle class="donut__ring" cx="21" cy="21" r="15.915"/>
        {% for seg in outcome_donut %}
        <circle class="donut__seg {{ seg.series }}" cx="21" cy="21" r="15.915"
                stroke-dasharray="{{ seg.dasharray }}" stroke-dashoffset="{{ seg.dashoffset }}"/>
        {% endfor %}
      </svg>
      <div class="donut__centre">
        <span class="donut__figure">{{ outcome_distribution.total }}</span>
        <span class="donut__caption">reported</span>
      </div>
    </div>
    <ul class="legend">
      <li class="legend__item s-teal"><span class="legend__swatch"></span>Satisfactory or better: {{ outcome_distribution.percents.satisfactory_or_better }}%</li>
      <li class="legend__item s-ochre"><span class="legend__swatch"></span>Needs improvement: {{ outcome_distribution.percents.needs_improvement }}%</li>
    </ul>
    <p class="chart__note">transcribed by teachers from the stamped paper.</p>
  </section>

  <section class="chart">
    <h2>Submission trend</h2>
    <div class="trend s-violet">
      <svg class="trend__svg" viewBox="0 0 {{ trend_width }} 100" preserveAspectRatio="none">
        <line class="trend__grid" x1="0" y1="25" x2="{{ trend_width }}" y2="25"/>
        <line class="trend__grid" x1="0" y1="50" x2="{{ trend_width }}" y2="50"/>
        <line class="trend__grid" x1="0" y1="75" x2="{{ trend_width }}" y2="75"/>
        <polyline class="trend__line" points="{{ trend_points }}"/>
      </svg>
      <div class="trend__axis"><span>{{ period|date:"j F" }}</span><span>{{ period|date:"F" }} end</span></div>
    </div>
  </section>

  <section class="chart">
    <h2>Submissions by status and region</h2>
    <div class="stack-rows">
      {% for row in status_rows|slice:":8" %}
      <div class="stack-row">
        <span class="bar__label">{{ row.region }}</span>
        <span class="stack">
          <span class="stack__seg s-teal" style="width:{{ row.submitted_percent }}%"></span>
          <span class="stack__seg s-ochre" style="width:{{ row.pending_percent }}%"></span>
          <span class="stack__seg s-quiet" style="width:{{ row.not_started_percent }}%"></span>
        </span>
        <span class="bar__value">{{ row.submitted_percent }}%</span>
      </div>
      {% endfor %}
    </div>
    <div class="legend">
      <span class="legend__item s-teal"><span class="legend__swatch"></span>Submitted</span>
      <span class="legend__item s-ochre"><span class="legend__swatch"></span>Pending</span>
      <span class="legend__item s-quiet"><span class="legend__swatch"></span>Not started</span>
    </div>
  </section>

  <section class="chart">
    <h2>On-time and late</h2>
    <div class="record">
      <div class="record__cell"><div class="record__value">{{ timeliness.on_time_percent }}%</div><div class="label">On time</div></div>
      <div class="record__cell"><div class="record__value">{{ timeliness.late_percent }}%</div><div class="label">Late</div></div>
      <div class="record__cell"><div class="record__value">{{ timeliness.average_submission_days }}</div><div class="label">Avg. days to submit</div></div>
      <div class="record__cell"><div class="record__value">{{ completeness_rate }}%</div><div class="label">Evidence completeness (provisional)</div></div>
    </div>
  </section>

</details>
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python manage.py test step.tests.test_admin_views -v 2`
Expected: PASS.

- [ ] **Step 6: Manually verify the render**

Run: `python manage.py runserver`, sign in as a seeded staff user, open `/step/admin/`. Confirm:
no server error, "See the full breakdown" is collapsed by default, expanding it shows all eight
widgets, the donuts draw as circles with visibly distinct segments, the trend line draws without
a console error, and no chart uses `--stamp`/`--seal` or an `.s-stamp`/`.s-seal` class anywhere
(there is no such class — if you typed one, it's a mistake to fix, not a missing primitive).

- [ ] **Step 7: Commit**

```bash
git add step/admin_views.py templates/step/admin/dashboard.html step/tests/test_admin_views.py
git commit -m "Add the nine analytics widgets, collapsed behind the action queue"
```

---

### Task 5: Review queue and review-detail screen

**Files:**
- Modify: `step/admin_views.py`
- Modify: `step/admin_urls.py`
- Create: `templates/step/admin/review_queue.html`
- Create: `templates/step/admin/review_detail.html`

- [ ] **Step 1: Write the failing test for the queue list**

```python
class ReviewQueueTests(TestCase):
    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        user = get_user_model().objects.create_user("admin1", password="pw")
        roles.assign(user, constants.ROLE_ADMIN)
        self.client.login(username="admin1", password="pw")
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
        )
        self.educator = Educator.objects.create(full_name="Teacher One", region=self.region)
        self.obligation = Obligation.objects.create(
            type=self.type, educator=self.educator, period_kind=constants.PERIOD_MONTH,
            period_start=date(2026, 5, 1), due_date=date(2026, 5, 27),
            status=constants.STATUS_SUBMITTED,
        )
        from step.models import Submission
        self.submission = Submission.objects.create(obligation=self.obligation, revision=1)

    def test_the_queue_lists_waiting_submissions(self):
        response = self.client.get(reverse("step:admin-review-queue"))
        self.assertContains(response, "Teacher One")

    def test_an_empty_queue_says_so_plainly(self):
        self.submission.delete()
        self.obligation.status = constants.STATUS_ACCEPTED
        self.obligation.save()
        response = self.client.get(reverse("step:admin-review-queue"))
        self.assertContains(response, "Nothing is waiting")

    def test_review_detail_shows_the_evidence_and_the_two_actions(self):
        response = self.client.get(reverse("step:admin-review-detail", args=[self.submission.pk]))
        self.assertContains(response, "Accept")
        self.assertContains(response, "Return")

    def test_accepting_marks_the_obligation_accepted(self):
        self.client.post(
            reverse("step:admin-review-detail", args=[self.submission.pk]),
            {"action": "accept"},
        )
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_ACCEPTED)

    def test_returning_without_a_comment_shows_a_plain_language_error_not_a_500(self):
        response = self.client.post(
            reverse("step:admin-review-detail", args=[self.submission.pk]),
            {"action": "return", "comment": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.obligation.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_SUBMITTED)

    def test_returning_with_a_comment_sends_it_back_to_the_teacher(self):
        self.client.post(
            reverse("step:admin-review-detail", args=[self.submission.pk]),
            {"action": "return", "comment": "Please attach the stamped page."},
        )
        self.obligation.refresh_from_db()
        self.submission.refresh_from_db()
        self.assertEqual(self.obligation.status, constants.STATUS_RETURNED)
        self.assertEqual(self.submission.review_comment, "Please attach the stamped page.")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test step.tests.test_admin_views.ReviewQueueTests -v 2`
Expected: FAIL — `AttributeError: module 'step.admin_views' has no attribute 'review_detail'`
and `NoReverseMatch` for `admin-review-detail`.

- [ ] **Step 3: Implement `review_queue` and `review_detail`**

Add to `step/admin_views.py`:

```python
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect

from step.models import Submission


@staff_required
def review_queue(request):
    context = {"nav": "review", "rows": workflow.review_queue()}
    context.update(_admin_chrome(request))
    return render(request, "step/admin/review_queue.html", context)


@staff_required
def review_detail(request, pk: int):
    submission = get_object_or_404(
        Submission.objects.select_related("obligation", "obligation__type", "obligation__educator"),
        pk=pk,
    )

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "accept":
            workflow.accept(submission, reviewer=request.user)
            messages.success(request, "Accepted.")
            return redirect("step:admin-review-queue")
        if action == "return":
            comment = (request.POST.get("comment") or "").strip()
            try:
                workflow.return_for_correction(submission, reviewer=request.user, comment=comment)
            except ValueError:
                messages.error(
                    request, "Please explain what needs correcting before returning this."
                )
                context = {
                    "nav": "review", "submission": submission,
                    "evidence": submission.evidence.all(),
                    "is_monthly_report": (
                        submission.obligation.type.category == constants.CATEGORY_MONTHLY_REPORTING
                    ),
                }
                context.update(_admin_chrome(request))
                return render(request, "step/admin/review_detail.html", context)
            messages.success(request, "Returned to the teacher.")
            return redirect("step:admin-review-queue")

    context = {
        "nav": "review",
        "submission": submission,
        "evidence": submission.evidence.all(),
        "is_monthly_report": submission.obligation.type.category == constants.CATEGORY_MONTHLY_REPORTING,
    }
    context.update(_admin_chrome(request))
    return render(request, "step/admin/review_detail.html", context)
```

Update `step/admin_urls.py`:

```python
from django.urls import path

from step import admin_views

urlpatterns = [
    path("admin/", admin_views.dashboard, name="admin-dashboard"),
    path("admin/review/", admin_views.review_queue, name="admin-review-queue"),
    path("admin/review/<int:pk>/", admin_views.review_detail, name="admin-review-detail"),
    path("admin/teachers/", admin_views.dashboard, name="admin-teachers"),
]
```

- [ ] **Step 4: Write the two templates**

```django
{% extends "step/base_admin.html" %}
{% block title %}Review queue — STEP Administration{% endblock %}
{% block content %}
<h1>Review queue</h1>
{% if rows %}
<div class="register">
  {% for submission in rows %}
  <a class="entry" href="{% url 'step:admin-review-detail' submission.pk %}">
    <div class="entry__main">
      <div class="entry__title">{{ submission.obligation.display_name }}</div>
      <div class="entry__cat">{{ submission.obligation.educator.full_name }}</div>
    </div>
    <div class="entry__due">Sent {{ submission.submitted_at|date:"j F" }}</div>
  </a>
  {% endfor %}
</div>
{% else %}
<p>Nothing is waiting for review right now.</p>
{% endif %}
{% endblock %}
```

```django
{% extends "step/base_admin.html" %}
{% block title %}{{ submission.obligation.display_name }} — STEP Administration{% endblock %}
{% block content %}
<h1>{{ submission.obligation.display_name }}</h1>
<p class="entry__cat">{{ submission.obligation.educator.full_name }} &middot; {{ submission.obligation.educator.region.name }}</p>

{% if submission.note %}<p>{{ submission.note }}</p>{% endif %}

{% if is_monthly_report %}
<p class="chart__note">Self-reported — transcribed by the teacher from the stamped paper.</p>
{% if submission.director_rating %}<p>Director rating: {{ submission.director_rating }} / 5</p>{% endif %}
{% if submission.outcome %}<p>Outcome: {{ submission.get_outcome_display }}</p>{% endif %}
{% endif %}

<h2>Evidence</h2>
<ul>
  {% for item in evidence %}
  <li>
    {% if item.kind == 'link' %}<a href="{{ item.url }}">{{ item.caption|default:item.url }}</a>
    {% else %}<a href="{{ item.file.url }}">{{ item.caption|default:item.file.name }}</a>{% endif %}
  </li>
  {% empty %}
  <li>No evidence was attached.</li>
  {% endfor %}
</ul>

<form method="post">
  {% csrf_token %}
  <button class="btn btn--primary" type="submit" name="action" value="accept">Accept</button>
  <label for="comment">Comment (required to return)</label>
  <textarea id="comment" name="comment"></textarea>
  <button class="btn btn--quiet" type="submit" name="action" value="return">Return for correction</button>
</form>
{% endblock %}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python manage.py test step.tests.test_admin_views.ReviewQueueTests -v 2`
Expected: PASS — all six tests green.

- [ ] **Step 6: Commit**

```bash
git add step/admin_views.py step/admin_urls.py templates/step/admin/review_queue.html templates/step/admin/review_detail.html step/tests/test_admin_views.py
git commit -m "Add the review queue and the accept/return-for-correction screen"
```

---

### Task 6: Teacher directory and per-teacher file

**Files:**
- Modify: `step/admin_views.py`
- Modify: `step/admin_urls.py`
- Create: `templates/step/admin/teacher_directory.html`
- Create: `templates/step/admin/teacher_detail.html`

- [ ] **Step 1: Write the failing test**

```python
class TeacherDirectoryTests(TestCase):
    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        user = get_user_model().objects.create_user("admin1", password="pw")
        roles.assign(user, constants.ROLE_ADMIN)
        self.client.login(username="admin1", password="pw")
        self.samarkand = Region.objects.create(name="Samarkand", code="samarkand")
        self.tashkent = Region.objects.create(name="Tashkent City", code="tashkent-city")
        Educator.objects.create(full_name="Maria Santos", region=self.samarkand)
        Educator.objects.create(full_name="John Okafor", region=self.tashkent)

    def test_the_directory_lists_all_teachers(self):
        response = self.client.get(reverse("step:admin-teachers"))
        self.assertContains(response, "Maria Santos")
        self.assertContains(response, "John Okafor")

    def test_search_narrows_by_name(self):
        response = self.client.get(reverse("step:admin-teachers") + "?q=Maria")
        self.assertContains(response, "Maria Santos")
        self.assertNotContains(response, "John Okafor")

    def test_region_filter_narrows_results(self):
        response = self.client.get(reverse("step:admin-teachers") + f"?region={self.tashkent.pk}")
        self.assertContains(response, "John Okafor")
        self.assertNotContains(response, "Maria Santos")

    def test_the_outstanding_status_filter_only_shows_teachers_with_something_due(self):
        obligation_type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
        )
        Obligation.objects.create(
            type=obligation_type, educator=Educator.objects.get(full_name="Maria Santos"),
            period_kind=constants.PERIOD_MONTH, period_start=date(2026, 5, 1),
            due_date=date(2026, 5, 27),
        )
        response = self.client.get(
            reverse("step:admin-teachers") + "?status=outstanding&period=2026-05"
        )
        self.assertContains(response, "Maria Santos")
        self.assertNotContains(response, "John Okafor")

    def test_passport_and_pinfl_never_appear(self):
        Educator.objects.create(
            full_name="Secret Person", region=self.samarkand,
            passport_no="AB1234567", pinfl="12345678901234",
        )
        response = self.client.get(reverse("step:admin-teachers"))
        self.assertNotContains(response, "AB1234567")
        self.assertNotContains(response, "12345678901234")

    def test_a_teachers_row_links_to_their_file(self):
        educator = Educator.objects.get(full_name="Maria Santos")
        response = self.client.get(reverse("step:admin-teachers"))
        self.assertContains(response, reverse("step:admin-teacher-detail", args=[educator.pk]))

    def test_the_teacher_file_lists_their_obligations_with_teacher_facing_wording(self):
        obligation_type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
        )
        educator = Educator.objects.get(full_name="Maria Santos")
        Obligation.objects.create(
            type=obligation_type, educator=educator, period_kind=constants.PERIOD_MONTH,
            period_start=date(2026, 5, 1), due_date=date(2020, 1, 1),
        )
        response = self.client.get(reverse("step:admin-teacher-detail", args=[educator.pk]))
        self.assertContains(response, "late")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test step.tests.test_admin_views.TeacherDirectoryTests -v 2`
Expected: FAIL — `NoReverseMatch: Reverse for 'admin-teacher-detail' not found`.

- [ ] **Step 3: Implement `teacher_directory` and `teacher_detail`**

Add to `step/admin_views.py`:

```python
from django.core.paginator import Paginator

from step import presentation
from step.models import Educator, Region


@staff_required
def teacher_directory(request):
    query = (request.GET.get("q") or "").strip()
    region_id = request.GET.get("region") or ""
    status = request.GET.get("status") or ""
    period = _current_period(request)

    educators = Educator.objects.filter(is_active=True).select_related("region", "school")
    if query:
        educators = educators.filter(full_name__icontains=query)
    if region_id:
        educators = educators.filter(region_id=region_id)
    if status == "outstanding":
        outstanding_ids = Obligation.objects.filter(
            period_start=period, status=constants.STATUS_NOT_STARTED
        ).values_list("educator_id", flat=True)
        educators = educators.filter(id__in=outstanding_ids)

    paginator = Paginator(educators, 50)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "nav": "teachers",
        "page": page,
        "query": query,
        "regions": Region.objects.all(),
        "selected_region": region_id,
        "status": status,
        "period": period,
    }
    context.update(_admin_chrome(request))
    return render(request, "step/admin/teacher_directory.html", context)


@staff_required
def teacher_detail(request, pk: int):
    educator = get_object_or_404(Educator.objects.select_related("region", "school"), pk=pk)
    obligations = educator.obligations.select_related("type").order_by("-due_date")
    context = {
        "nav": "teachers",
        "educator": educator,
        "file_ref": presentation.file_reference(educator),
        "items": presentation.decorate_all(obligations, date.today()),
    }
    context.update(_admin_chrome(request))
    return render(request, "step/admin/teacher_detail.html", context)
```

Update `step/admin_urls.py`:

```python
from django.urls import path

from step import admin_views

urlpatterns = [
    path("admin/", admin_views.dashboard, name="admin-dashboard"),
    path("admin/review/", admin_views.review_queue, name="admin-review-queue"),
    path("admin/review/<int:pk>/", admin_views.review_detail, name="admin-review-detail"),
    path("admin/teachers/", admin_views.teacher_directory, name="admin-teachers"),
    path("admin/teachers/<int:pk>/", admin_views.teacher_detail, name="admin-teacher-detail"),
]
```

- [ ] **Step 4: Write the directory and file templates**

```django
{% extends "step/base_admin.html" %}
{% block title %}Teachers — STEP Administration{% endblock %}
{% block content %}
<h1>Teachers</h1>

<form method="get">
  <label for="q">Search by name</label>
  <input type="text" id="q" name="q" value="{{ query }}">
  <label for="region">Region</label>
  <select id="region" name="region">
    <option value="">All regions</option>
    {% for r in regions %}
    <option value="{{ r.pk }}" {% if selected_region == r.pk|stringformat:"s" %}selected{% endif %}>{{ r.name }}</option>
    {% endfor %}
  </select>
  <button class="btn btn--quiet" type="submit">Filter</button>
</form>

<div class="register">
  {% for educator in page %}
  <a class="entry" href="{% url 'step:admin-teacher-detail' educator.pk %}">
    <div class="entry__main">
      <div class="entry__title">{{ educator.full_name }}</div>
      <div class="entry__cat">{{ educator.region.name }}{% if educator.school %} &middot; {{ educator.school.name }}{% endif %}</div>
    </div>
  </a>
  {% empty %}
  <p>No teachers match this search.</p>
  {% endfor %}
</div>

{% if page.has_other_pages %}
<nav aria-label="Pages">
  {% if page.has_previous %}<a href="?page={{ page.previous_page_number }}&q={{ query }}&region={{ selected_region }}">Previous</a>{% endif %}
  <span>Page {{ page.number }} of {{ page.paginator.num_pages }}</span>
  {% if page.has_next %}<a href="?page={{ page.next_page_number }}&q={{ query }}&region={{ selected_region }}">Next</a>{% endif %}
</nav>
{% endif %}
{% endblock %}
```

```django
{% extends "step/base_admin.html" %}
{% block title %}{{ educator.full_name }} — STEP Administration{% endblock %}
{% block content %}
<h1>{{ educator.full_name }}</h1>
<p class="entry__cat">FILE {{ file_ref }} &middot; {{ educator.region.name }}{% if educator.school %} &middot; {{ educator.school.name }}{% endif %}</p>

<div class="register">
  {% for item in items %}
  <div class="entry">
    <div class="entry__main">
      <div class="entry__title">{{ item.obligation.display_name }}</div>
    </div>
    <div class="entry__status mark--{{ item.urgency }}">{{ item.due_phrase }}</div>
  </div>
  {% empty %}
  <p>This teacher has no obligations on record.</p>
  {% endfor %}
</div>
{% endblock %}
```

The teacher file shows `item.due_phrase` (e.g. "1 day late"), not `item.urgency_label`, to match
`test_the_teacher_file_lists_their_obligations_with_teacher_facing_wording`'s check for "late" —
`due_phrase` is `presentation.due_phrase`'s output, already the exact wording the teacher sees on
their own dashboard for the same obligation.

- [ ] **Step 5: Run test to verify it passes**

Run: `python manage.py test step.tests.test_admin_views.TeacherDirectoryTests -v 2`
Expected: PASS — all seven tests green.

- [ ] **Step 6: Commit**

```bash
git add step/admin_views.py step/admin_urls.py templates/step/admin/teacher_directory.html templates/step/admin/teacher_detail.html step/tests/test_admin_views.py
git commit -m "Add the searchable teacher directory and per-teacher file screen"
```

---

### Task 7: Integration check, full suite, and sign-off

**Files:**
- Test: `step/tests/test_admin_views.py`

- [ ] **Step 1: Write the failing (or already-passing) integration test**

```python
class ActionQueueLinkTests(TestCase):
    def setUp(self):
        call_command("seed_roles", stdout=StringIO())
        user = get_user_model().objects.create_user("admin1", password="pw")
        roles.assign(user, constants.ROLE_ADMIN)
        self.client.login(username="admin1", password="pw")
        self.region = Region.objects.create(name="Samarkand", code="samarkand")
        self.type = ObligationType.objects.create(
            name_template="Monthly Report", category=constants.CATEGORY_MONTHLY_REPORTING,
            cadence=constants.CADENCE_MONTHLY, evidence_spec=constants.EVIDENCE_NONE,
        )
        Obligation.objects.create(
            type=self.type,
            educator=Educator.objects.create(full_name="Teacher One", region=self.region),
            period_kind=constants.PERIOD_MONTH, period_start=date(2026, 5, 1),
            due_date=date(2026, 5, 27),
        )

    def test_the_dashboards_outstanding_link_lands_on_a_directory_that_shows_that_teacher(self):
        dashboard = self.client.get(reverse("step:admin-dashboard") + "?period=2026-05")
        self.assertContains(dashboard, "status=outstanding&period=2026-05")
        directory = self.client.get(
            reverse("step:admin-teachers") + "?status=outstanding&period=2026-05"
        )
        self.assertContains(directory, "Teacher One")
```

- [ ] **Step 2: Run it**

Run: `python manage.py test step.tests.test_admin_views.ActionQueueLinkTests -v 2`
Expected: PASS, since Tasks 3 and 6 already built matching querystring conventions. If it fails,
the mismatch is between the querystring the dashboard link builds (Task 3, Step 4) and what
`teacher_directory` reads (Task 6, Step 3) — fix whichever one drifted and re-run.

- [ ] **Step 3: Run the entire project's test suite**

Run: `python manage.py test`
Expected: every test passes, including everything outside `step/` — this plan must not have
broken `diagnostics`, `bank`, or `assembly`. Note the total test count before reporting
completion, and compare it against the baseline noted by `test-generator-16` (528 passing before
this work started, plus whatever else has landed from other sessions in the meantime).

- [ ] **Step 4: Manual walkthrough**

With the dev server running and signed in as a seeded staff user:
1. `/step/admin/` — action queue shows real counts, headline record strip is correct, widgets
   are collapsed, expanding shows all eight, no console/network errors, donuts render as circles.
2. Click into "N teachers have not submitted" — lands on the directory, pre-filtered, shows the
   right teachers.
3. Click into "N submissions waiting" — lands on the review queue.
4. Open one submission, click Accept — redirects to the queue, the submission is gone from it.
5. Submit another (via the teacher-facing screens, or `workflow.submit()` in the Django shell),
   open it, click Return with no comment — see the plain-language error, not a 500. Add a
   comment, click Return — redirects, obligation is now `returned`.
6. `/step/admin/teachers/` — search and region filter both narrow results; a teacher's file opens
   and lists their obligations with the same status wording the teacher-facing screens use.
7. On a phone-width viewport (375px), confirm no horizontal overflow on any of the five screens.

- [ ] **Step 5: Commit if Step 1 needed a fix**

```bash
git add -A
git commit -m "Reconcile the action queue's outstanding link with the directory filter"
```

(Skip this commit if Step 2 already passed with no changes.)

- [ ] **Step 6: Confirm the live URL wiring and tell the peer sessions**

The tests in this plan resolve URLs from `step/admin_urls.py` directly and cannot detect a
missing `include()` line in the real `step/urls.py` (Task 1's coordination step). Confirm it
actually landed:

Run: `python manage.py shell -c "from django.urls import reverse; print(reverse('step:admin-dashboard'))"`
Expected: prints `/step/admin/` with no exception. If it raises `NoReverseMatch`, the include
line from Task 1 is still missing — message whoever owns `step/urls.py` and wait for it before
declaring this plan done.

Once confirmed, message `test-generator-16` (and any other active peer session) that the admin
dashboard is implemented, the full suite is green, and give the new test count.
