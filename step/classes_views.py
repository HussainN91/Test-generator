"""Screens for a teacher's own classes, students and checkpoint scoring.

Kept out of step/views.py deliberately: that file, step/urls.py, and
templates/step/base.html are owned by another session's teacher-panel work
this round, and every route here is new — only the checkpoint branch inside
the existing obligation page (see step/views.py's obligation view once that
coordination lands) has to live in the shared file.
"""

import re
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from step import constants, presentation, workflow
from step.models import (
    AcademicYear, Educator, Obligation, ProgressEntry, Student, TeachingClass,
)


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


#: "9A", "11 c", "10-2" - a grade, then the class within it.
CLASS_NAME = re.compile(r"(\d{1,2})\s*[-\s]?\s*([A-Za-z]|[0-9])")


def _slot_letters() -> list:
    """A, B, C, D - one letter per class pack the programme runs per grade."""
    return [chr(ord("A") + index) for index in range(constants.TEACHING_SLOTS_PER_GRADE)]


def example_class_names() -> list:
    """What to show a teacher as a pattern to copy.

    Derived from the grades and slot count rather than written out, so a
    programme that grows a grade or a fifth class does not leave a stale
    example on the form.
    """
    letters = _slot_letters()
    grades = constants.TEACHING_GRADES
    return [
        f"{grades[0]}{letters[0]}",
        f"{grades[0]}{letters[1]}",
        f"{grades[-1]}{letters[-1]}",
    ]


def parse_class_name(raw: str):
    """Turn what a teacher types - "9A", "11 c" - into (grade, slot, error).

    The teacher types the name they already use for the class and the grade
    and class-pack number are read out of it, rather than being asked for as
    two more questions. Diagnostics labels the pack with this same name
    (diagnostics/navigation.py), so naming a class here is what renames the
    pack there.

    Errors are instructions a teacher can act on, never the rule that failed.
    """
    text = (raw or "").strip()
    if not text:
        return None, None, "Enter a name for the class, like %s." % example_class_names()[0]

    match = CLASS_NAME.fullmatch(text)
    if match is None:
        return None, None, (
            "Write the grade and then the class letter, like %s."
            % " or ".join(example_class_names()[:2])
        )

    grade = int(match.group(1))
    if grade not in constants.TEACHING_GRADES:
        return None, None, (
            "This programme runs grades %s, so a class name starts with one of those."
            % ", ".join(str(g) for g in constants.TEACHING_GRADES)
        )

    token = match.group(2)
    slot = int(token) if token.isdigit() else ord(token.upper()) - ord("A") + 1
    letters = _slot_letters()
    if not (1 <= slot <= constants.TEACHING_SLOTS_PER_GRADE):
        return None, None, (
            "Each grade has %d classes, %s to %s."
            % (constants.TEACHING_SLOTS_PER_GRADE, letters[0], letters[-1])
        )

    return grade, slot, None


@login_required
def class_create(request):
    educator = _educator(request)

    context = {
        "nav": "classes",
        "examples": example_class_names(),
        "slot_letters": _slot_letters(),
        "grades": constants.TEACHING_GRADES,
        "form": {},
    }

    if request.method == "POST":
        typed = (request.POST.get("display_name") or "").strip()
        grade, slot, error = parse_class_name(typed)
        # Stored upper-case: the field is styled upper-case and the live
        # readout promises upper-case, so keeping "9b" as typed would show a
        # different name on the diagnostics pack than the teacher just saw.
        display_name = typed.upper()

        if error is None:
            try:
                with transaction.atomic():
                    teaching_class = TeachingClass.objects.create(
                        educator=educator, grade=grade, slot=slot, display_name=display_name
                    )
            except IntegrityError:
                error = (
                    "Grade %d, class %s already belongs to another teacher."
                    % (grade, _slot_letters()[slot - 1])
                )
            else:
                messages.success(
                    request,
                    "%s has been added. Its diagnostic pack is now called %s too."
                    % (display_name, display_name),
                )
                return redirect("step:class_detail", pk=teaching_class.pk)

        messages.error(request, error)
        context["form"] = {"display_name": typed}
        context.update(_chrome(educator))
        return render(request, "step/classes/create.html", context)

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


def _academic_months(year) -> list:
    """Every month of the academic year, as that month's first day.

    The sheet's columns are months of the *school* year, so this walks
    September to May rather than January to December.
    """
    months, cursor = [], date(year.start.year, year.start.month, 1)
    last = date(year.end.year, year.end.month, 1)
    while cursor <= last:
        months.append(cursor)
        cursor = date(cursor.year + cursor.month // 12, cursor.month % 12 + 1, 1)
    return months


def _selected_month(request, months: list):
    """Which month the sheet is showing.

    A malformed or out-of-year `?month=` 404s rather than quietly showing a
    different month: a teacher entering marks against the wrong column is
    worse than an obvious error page.
    """
    if not months:
        return None

    raw = (request.GET.get("month") or "").strip()
    if not raw:
        opened = date.today().replace(day=1)
        return opened if opened in months else months[0]

    try:
        year_part, month_part = raw.split("-")
        wanted = date(int(year_part), int(month_part), 1)
    except (ValueError, TypeError) as exc:
        raise Http404("That is not a month this sheet understands.") from exc
    if wanted not in months:
        raise Http404("That month is not part of this academic year.")
    return wanted


def _read_score(raw):
    """(score, acceptable). Out of range is refused, never silently dropped —
    the min/max on the input is client-side only."""
    raw = (raw or "").strip()
    if not raw:
        return None, True
    if not raw.isdigit() or not (0 <= int(raw) <= 100):
        return None, False
    return int(raw), True


def _save_monthly_marks(request, teaching_class, month):
    """One mark per student, per skill, for the open month.

    A cleared box deletes the mark rather than storing a null: an empty cell
    and a recorded zero are different claims about a child.
    """
    saved = refused = 0
    for student in teaching_class.students.all():
        for skill, _label in constants.SKILL_CHOICES:
            score, ok = _read_score(request.POST.get("m_%s_%s" % (student.pk, skill)))
            if not ok:
                refused += 1
                continue
            cell = ProgressEntry.objects.filter(student=student, period=month, skill=skill)
            if score is None:
                cell.delete()
                continue
            ProgressEntry.objects.update_or_create(
                student=student, period=month, skill=skill,
                defaults={"score": score, "checkpoint": ""},
            )
            saved += 1
    return saved, refused


def _save_checkpoint_marks(request, teaching_class):
    """The three BOY/MOY/EOY marks, editable here so a teacher never has to
    leave the class to satisfy the obligation.

    A blank box is left alone rather than deleted: clearing a mark here would
    silently un-settle an obligation an administrator may already have seen.
    """
    saved = refused = 0
    touched = set()
    for student in teaching_class.students.all():
        for checkpoint, _label in constants.CHECKPOINT_CHOICES:
            score, ok = _read_score(request.POST.get("c_%s_%s" % (student.pk, checkpoint)))
            if not ok:
                refused += 1
                continue
            if score is None:
                continue
            ProgressEntry.objects.update_or_create(
                student=student, checkpoint=checkpoint, defaults={"score": score},
            )
            touched.add(checkpoint)
            saved += 1

    for checkpoint in touched:
        workflow.sync_checkpoint(teaching_class, checkpoint)
    return saved, refused


@login_required
def class_detail(request, pk: int):
    educator = _educator(request)
    teaching_class = get_object_or_404(TeachingClass, pk=pk, educator=educator)

    year = AcademicYear.objects.filter(is_current=True).first()
    months = _academic_months(year) if year else []
    month = _selected_month(request, months)

    if request.method == "POST":
        if request.POST.get("form") == "checkpoints":
            saved, refused = _save_checkpoint_marks(request, teaching_class)
        elif month is None:
            saved, refused = 0, 0
            messages.error(
                request,
                "No academic year is set up yet, so there is nowhere to file a monthly mark.",
            )
        else:
            saved, refused = _save_monthly_marks(request, teaching_class, month)

        if refused:
            messages.error(
                request,
                "%d mark(s) were not saved - a score must be a whole number from 0 to 100." % refused,
            )
        if saved:
            messages.success(request, "%d mark(s) saved." % saved)

        destination = reverse("step:class_detail", args=[teaching_class.pk])
        if month:
            destination = "%s?month=%s" % (destination, month.strftime("%Y-%m"))
        return redirect(destination)

    students = list(teaching_class.students.all())
    monthly = {}
    if month:
        monthly = {
            (entry.student_id, entry.skill): entry
            for entry in ProgressEntry.objects.filter(
                student__teaching_class=teaching_class, period=month
            )
        }
    checkpoint_marks = {
        (entry.student_id, entry.checkpoint): entry
        for entry in ProgressEntry.objects.filter(
            student__teaching_class=teaching_class
        ).exclude(checkpoint="")
    }

    rows = []
    for student in students:
        cells = [
            {"skill": skill, "label": label, "entry": monthly.get((student.pk, skill))}
            for skill, label in constants.SKILL_CHOICES
        ]
        marks = [c["entry"].score for c in cells if c["entry"] and c["entry"].score is not None]
        rows.append({
            "student": student,
            "cells": cells,
            # A reading aid, never stored: an average of four skills is not
            # itself a mark anyone awarded.
            "average": round(sum(marks) / len(marks)) if marks else None,
            "checkpoints": [
                {
                    "checkpoint": key,
                    "label": label,
                    "entry": checkpoint_marks.get((student.pk, key)),
                }
                for key, label in constants.CHECKPOINT_CHOICES
            ],
        })

    position = months.index(month) if month in months else -1
    context = {
        "nav": "classes",
        "teaching_class": teaching_class,
        "students": students,
        "rows": rows,
        "skills": constants.SKILL_CHOICES,
        "checkpoint_columns": constants.CHECKPOINT_CHOICES,
        "months": months,
        "month": month,
        "previous_month": months[position - 1] if position > 0 else None,
        "next_month": months[position + 1] if 0 <= position < len(months) - 1 else None,
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
    """One child's year, read down the page.

    The flat reverse-chronological list this replaced could not answer the
    question a teacher actually asks - "how is this one doing, month by
    month" - because a mark and a note sat in the same undifferentiated feed.
    """
    educator = _educator(request)
    student = get_object_or_404(Student, pk=pk, teaching_class__educator=educator)

    year = AcademicYear.objects.filter(is_current=True).first()
    months = _academic_months(year) if year else []

    entries = list(student.progress_entries.select_related("grammar_point").all())
    monthly = {(entry.period, entry.skill): entry for entry in entries if entry.period}
    by_checkpoint = {entry.checkpoint: entry for entry in entries if entry.checkpoint}
    # A note is the leftover: no checkpoint, no month. Kept separate so a
    # comment can never be mistaken for a mark.
    notes = [entry for entry in entries if not entry.checkpoint and entry.period is None]

    month_rows = []
    for month in months:
        cells = [
            {"skill": skill, "label": label, "entry": monthly.get((month, skill))}
            for skill, label in constants.SKILL_CHOICES
        ]
        marks = [c["entry"].score for c in cells if c["entry"] and c["entry"].score is not None]
        month_rows.append({
            "month": month,
            "cells": cells,
            "average": round(sum(marks) / len(marks)) if marks else None,
            "marked": bool(marks),
        })

    context = {
        "nav": "classes",
        "student": student,
        "skills": constants.SKILL_CHOICES,
        "month_rows": month_rows,
        "checkpoint_rows": [
            {"checkpoint": key, "label": label, "entry": by_checkpoint.get(key)}
            for key, label in constants.CHECKPOINT_CHOICES
        ],
        "notes": notes,
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
