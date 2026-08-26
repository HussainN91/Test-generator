"""Teacher views: build a batch, preview it with answer keys, export it."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from assembly.export import batch_to_docx, docx_available
from assembly.forms import TestBuilderForm
from assembly.models import TestBatch
from assembly.services import (
    AssemblyError,
    bank_summary,
    build_plan,
    resolve_type_mix,
    save_plan,
)
from bank.models import QuestionType, ReviewStatus
from content.models import Grade, Unit


def _selected_grade(request) -> Grade | None:
    raw = request.POST.get("grade") or request.GET.get("grade")
    if raw:
        return Grade.objects.filter(pk=raw).first()
    return Grade.objects.order_by("number").first()


def _units_with_counts(grade: Grade | None):
    """Units for a grade, each annotated with how many approved items it holds."""
    if grade is None:
        return Unit.objects.none()
    return (
        Unit.objects.filter(grade=grade)
        .select_related("grammar_point")
        .annotate(
            approved_items=Count(
                "items", filter=Q(items__review_status=ReviewStatus.APPROVED), distinct=True
            )
        )
        .order_by("number")
    )


def _selected_unit_ids(request) -> set[int]:
    """Units shaded in the posted form, so a rejected submission keeps them shaded."""
    ids = set()
    for raw in request.POST.getlist("units"):
        try:
            ids.add(int(raw))
        except (TypeError, ValueError):
            continue
    return ids


def _carried_initial(request) -> dict:
    """Numbers already typed into the form, preserved across a grade switch."""
    if request.method != "POST":
        return {}
    carried = {
        name: request.POST[name]
        for name in ("question_count", "variant_count")
        if request.POST.get(name)
    }
    if request.POST.get("customize_mix"):
        carried["customize_mix"] = True
    for name, value in request.POST.items():
        if name.startswith("weight_") and value:
            carried[name] = value
    return carried


@login_required
def builder(request):
    """Grade + unit picker; on POST, samples a batch and redirects to its preview."""
    grade = _selected_grade(request)

    if request.method == "POST" and "generate" in request.POST:
        form = TestBuilderForm(request.POST, grade=grade)
        if form.is_valid():
            units = list(form.cleaned_data["units"])
            unit_ids = [unit.pk for unit in units]
            question_count = form.cleaned_data["question_count"]
            variant_count = form.cleaned_data["variant_count"]
            weights = form.cleaned_weights()
            mix = resolve_type_mix(question_count, weights) if weights else None

            try:
                plan = build_plan(unit_ids, question_count, variant_count, type_mix=mix)
            except AssemblyError as error:
                messages.error(request, str(error))
            else:
                if plan.actual_per_variant == 0:
                    messages.error(
                        request,
                        "The selected units have no approved items yet. Import or seed a bank first.",
                    )
                else:
                    batch = TestBatch.objects.create(
                        grade=form.cleaned_data["grade"],
                        created_by=request.user,
                        question_count=question_count,
                        variant_count=variant_count,
                        type_mix=mix or {},
                    )
                    batch.units.set(units)
                    save_plan(plan, batch)

                    if plan.unavailable_types:
                        messages.info(
                            request,
                            "Drawn from the types these units actually hold. Not in the "
                            "bank yet, so left out of the mix: "
                            + ", ".join(plan.unavailable_types) + ".",
                        )
                    for shortfall in plan.shortfalls:
                        messages.warning(request, f"Not enough items — {shortfall}")
                    if plan.actual_per_variant < question_count:
                        messages.warning(
                            request,
                            f"Each variant has {plan.actual_per_variant} questions "
                            f"instead of {question_count}.",
                        )
                    return redirect("batch_preview", pk=batch.pk)
        else:
            # The builder is a long page and the submit button sits at the
            # bottom of it. Without this the page just reloads, scrolled back to
            # the top, with the only clue a small red line halfway down — which
            # reads as "the button does nothing".
            for field_errors in form.errors.values():
                for error in field_errors:
                    messages.error(request, error)
    else:
        # A grade switch re-posts the page. Carry the numbers the teacher already
        # typed across, or they silently reset every time the grade changes.
        form = TestBuilderForm(grade=grade, initial=_carried_initial(request))

    units = _units_with_counts(grade)
    summary = bank_summary([unit.pk for unit in units])

    return render(
        request,
        "assembly/builder.html",
        {
            "form": form,
            "grades": Grade.objects.order_by("number"),
            "grade": grade,
            "units": units,
            "summary": [
                (question_type.label, summary.get(question_type.value, 0))
                for question_type in QuestionType
            ],
            "total_items": sum(summary.values()),
            "selected_unit_ids": _selected_unit_ids(request),
            "recent_batches": TestBatch.objects.filter(created_by=request.user)[:5],
        },
    )


@login_required
def batch_preview(request, pk: int):
    """Every variant with its answer key, before export (spec 7.3)."""
    batch = get_object_or_404(
        TestBatch.objects.select_related("grade").prefetch_related("units"), pk=pk
    )
    variants = batch.variants.prefetch_related("questions__item__unit").all()
    return render(
        request,
        "assembly/preview.html",
        {"batch": batch, "variants": variants, "docx_available": docx_available()},
    )


@login_required
def batch_print(request, pk: int):
    """Printable HTML — works with no extra dependencies, via the browser's print dialog."""
    batch = get_object_or_404(TestBatch.objects.select_related("grade"), pk=pk)
    variants = batch.variants.prefetch_related("questions__item").all()
    with_answers = request.GET.get("answers") == "1"
    return render(
        request,
        "assembly/print.html",
        {"batch": batch, "variants": variants, "with_answers": with_answers},
    )


@login_required
def batch_docx(request, pk: int):
    """Download the batch as a .docx (tests followed by answer keys)."""
    if not docx_available():
        raise Http404("python-docx is not installed on this server.")
    batch = get_object_or_404(TestBatch.objects.select_related("grade"), pk=pk)
    stream = batch_to_docx(batch)
    response = HttpResponse(
        stream.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    filename = f"grade-{batch.grade.number}-tests-batch-{batch.pk}.docx"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
