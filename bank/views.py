"""Bank coverage view (spec 7.1): which grade x unit cells actually have items."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import render

from bank.models import Item, QuestionType, ReviewStatus
from content.models import Grade, Unit


@login_required
def coverage(request):
    """A grade x unit grid showing approved item counts and what still needs review."""
    units = (
        Unit.objects.select_related("grade", "grammar_point")
        .annotate(
            approved=Count("items", filter=Q(items__review_status=ReviewStatus.APPROVED), distinct=True),
            pending=Count("items", filter=Q(items__review_status=ReviewStatus.FLAGGED), distinct=True),
            vocabulary_count=Count("vocabulary", distinct=True),
        )
        .order_by("grade__number", "number")
    )

    grades: dict[int, list[Unit]] = {}
    pending_total = 0
    for unit in units:
        grades.setdefault(unit.grade.number, []).append(unit)
        pending_total += unit.pending

    approved_by_type = dict(
        Item.objects.filter(review_status=ReviewStatus.APPROVED)
        .values_list("question_type")
        .order_by()
        .annotate(total=Count("id"))
    )
    type_totals = [
        (question_type.label, approved_by_type.get(question_type.value, 0))
        for question_type in QuestionType
    ]
    # The coverage bars are drawn relative to the largest type, so an empty
    # bank never divides by zero and a lopsided one still reads as lopsided.
    type_counts = [count for _, count in type_totals]
    approved_total = sum(type_counts)
    type_peak = max(type_counts) or 1

    return render(
        request,
        "bank/coverage.html",
        {
            "grades": sorted(grades.items()),
            "type_totals": type_totals,
            "type_peak": type_peak,
            "approved_total": approved_total,
            "pending_total": pending_total,
            "grade_objects": Grade.objects.order_by("number"),
        },
    )
