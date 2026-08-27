"""Screens for a teacher's own classes, students and checkpoint scoring.

Kept out of step/views.py deliberately: that file, step/urls.py, and
templates/step/base.html are owned by another session's teacher-panel work
this round, and every route here is new — only the checkpoint branch inside
the existing obligation page (see step/views.py's obligation view once that
coordination lands) has to live in the shared file.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from step import constants, presentation
from step.models import Educator, Obligation, ProgressEntry, Student, TeachingClass


def _educator(request) -> Educator:
    educator = Educator.objects.filter(user=request.user).select_related("region", "school").first()
    if educator is None:
        raise Http404("This account is not linked to a teacher record yet.")
    return educator


def _chrome(educator) -> dict:
    return {
        "educator": educator,
        "file_ref": presentation.file_reference(educator),
        "categories": constants.CATEGORY_CHOICES,
        "returned_count": educator.obligations.filter(status=constants.STATUS_RETURNED).count(),
    }


@login_required
def class_list(request):
    educator = _educator(request)
    context = {"nav": "classes", "classes": educator.classes.all()}
    context.update(_chrome(educator))
    return render(request, "step/classes/list.html", context)


@login_required
def class_create(request):
    educator = _educator(request)

    if request.method == "POST":
        grade_raw = (request.POST.get("grade") or "").strip()
        slot_raw = (request.POST.get("slot") or "").strip()
        display_name = (request.POST.get("display_name") or "").strip()

        error = None
        grade = slot = None
        if not grade_raw.isdigit() or int(grade_raw) not in constants.TEACHING_GRADES:
            error = f"Choose a grade from {', '.join(str(g) for g in constants.TEACHING_GRADES)}."
        elif not slot_raw.isdigit() or not (1 <= int(slot_raw) <= constants.TEACHING_SLOTS_PER_GRADE):
            error = f"Choose a class number from 1 to {constants.TEACHING_SLOTS_PER_GRADE}."
        elif not display_name:
            error = "Give the class a name."
        else:
            grade, slot = int(grade_raw), int(slot_raw)

        if error is None:
            try:
                with transaction.atomic():
                    teaching_class = TeachingClass.objects.create(
                        educator=educator, grade=grade, slot=slot, display_name=display_name
                    )
            except IntegrityError:
                error = f"Grade {grade}, class {slot} already belongs to another teacher."
            else:
                messages.success(request, f"{display_name} has been added.")
                return redirect("step:class_detail", pk=teaching_class.pk)

        messages.error(request, error)
        context = {
            "nav": "classes",
            "grades": constants.TEACHING_GRADES,
            "slots": range(1, constants.TEACHING_SLOTS_PER_GRADE + 1),
            "form": {"grade": grade_raw, "slot": slot_raw, "display_name": display_name},
        }
        context.update(_chrome(educator))
        return render(request, "step/classes/create.html", context)

    context = {
        "nav": "classes",
        "grades": constants.TEACHING_GRADES,
        "slots": range(1, constants.TEACHING_SLOTS_PER_GRADE + 1),
        "form": {},
    }
    context.update(_chrome(educator))
    return render(request, "step/classes/create.html", context)


def _checkpoint_summary(teaching_class) -> list[dict]:
    total = teaching_class.students.count()
    summary = []
    for value, label in constants.CHECKPOINT_CHOICES:
        done = (
            ProgressEntry.objects.filter(student__teaching_class=teaching_class, checkpoint=value)
            .values("student").distinct().count()
        )
        name_template = constants.CHECKPOINT_OBLIGATION_NAME_TEMPLATES[value]
        obligation = Obligation.objects.filter(
            teaching_class=teaching_class, type__name_template=name_template
        ).first()
        summary.append({
            "checkpoint": value, "label": label, "done": done, "total": total,
            "obligation": obligation,
        })
    return summary


@login_required
def class_detail(request, pk: int):
    educator = _educator(request)
    teaching_class = get_object_or_404(TeachingClass, pk=pk, educator=educator)

    context = {
        "nav": "classes",
        "teaching_class": teaching_class,
        "students": teaching_class.students.all(),
        "checkpoints": _checkpoint_summary(teaching_class),
    }
    context.update(_chrome(educator))
    return render(request, "step/classes/detail.html", context)


@login_required
def student_create(request, pk: int):
    educator = _educator(request)
    teaching_class = get_object_or_404(TeachingClass, pk=pk, educator=educator)

    if request.method == "POST":
        full_name = (request.POST.get("full_name") or "").strip()
        if not full_name:
            messages.error(request, "Enter the student's name.")
        else:
            Student.objects.create(teaching_class=teaching_class, full_name=full_name)
            messages.success(request, f"{full_name} has been added to {teaching_class.display_name}.")
            return redirect("step:class_detail", pk=teaching_class.pk)

    context = {"nav": "classes", "teaching_class": teaching_class}
    context.update(_chrome(educator))
    return render(request, "step/classes/student_create.html", context)


@login_required
def student_detail(request, pk: int):
    educator = _educator(request)
    student = get_object_or_404(Student, pk=pk, teaching_class__educator=educator)

    context = {
        "nav": "classes",
        "student": student,
        "entries": student.progress_entries.select_related("grammar_point").all(),
    }
    context.update(_chrome(educator))
    return render(request, "step/classes/student_detail.html", context)


@login_required
def note_create(request, pk: int):
    educator = _educator(request)
    student = get_object_or_404(Student, pk=pk, teaching_class__educator=educator)

    if request.method == "POST":
        comment = (request.POST.get("comment") or "").strip()
        skill = request.POST.get("skill") or ""
        if not comment:
            messages.error(request, "Write what you want to note before saving.")
        else:
            ProgressEntry.objects.create(student=student, skill=skill, comment=comment)
            messages.success(request, "Note added.")
            return redirect("step:student_detail", pk=student.pk)

    context = {"nav": "classes", "student": student, "skills": constants.SKILL_CHOICES}
    context.update(_chrome(educator))
    return render(request, "step/classes/note_create.html", context)
