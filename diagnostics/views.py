"""Teacher-facing views: browse the papers, preview one, download its files.

Mirrors assembly/views.py's shape (login_required functions, get_object_or_404,
render/HttpResponse) rather than introducing a second pattern into the same
project. What is diagnostics-specific: a paper is fixed content, never
assembled on the fly, so there is no builder form here — only a catalogue.

Visibility rule: staff (is_staff) see every published paper, across all
three grades, plus the two staff-only pages (issue register isn't built
yet — see the design doc). An ordinary teacher sees only papers for the
grades TeacherGradeAssignment says they teach. No assignment means no
papers, not every paper — the whole point of the assignment model (spec
4.2) is that absence is meaningful, and defaulting an unassigned teacher to
"sees everything" would erase that on day one.
"""

from __future__ import annotations

import io
import os

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render

from django.db.models import Count, Q

from diagnostics.constants import GRADES
from diagnostics.export import (
    answer_key_docx, docx_available, examiner_docx, student_docx,
)
from diagnostics.listening_bank import key_balance, set_usage, usage_title
from diagnostics.models import (
    GenerationEvent,
    GenerationWindow,
    ListeningQuestion,
    ListeningQuestionSet,
    Paper,
    TeacherGradeAssignment,
)
from diagnostics.navigation import (
    CLASSES_PER_GRADE,
    CLASS_NUMBERS,
    VARIANTS_PER_CLASS,
    class_for_variant,
    display_name_for,
    variant_span,
    variants_for_class,
)
from diagnostics.rendering import (
    answer_key,
    needs_inline_blank,
    option_rows,
    paper_sections,
    reading_groups,
)


def _visible_grades(user):
    """Which grades this user may see papers for. Staff see all three."""
    if user.is_staff:
        return list(GRADES)
    return list(TeacherGradeAssignment.grades_for(user))


def _get_visible_paper(user, grade, variant):
    if grade not in _visible_grades(user):
        raise Http404("No paper here.")
    return get_object_or_404(
        Paper.objects.select_related(
            "listening_set_1__clip", "listening_set_2__clip", "reading_passage"
        ),
        grade=grade, variant=variant, is_published=True,
    )


def _pack_papers(user, grade, number):
    """The published papers of one class pack, in variant order."""
    if grade not in _visible_grades(user):
        raise Http404("No papers here.")
    return list(
        Paper.objects.filter(
            grade=grade, is_published=True, variant__in=variants_for_class(number)
        )
        .select_related("listening_set_1__clip", "listening_set_2__clip", "reading_passage")
        .order_by("variant")
    )


@login_required
def paper_index(request):
    """Step one: which grade. This used to be the whole register — every
    visible grade's sixteen variants in one table. At forty-eight rows that
    stopped being a register and became a haystack, so the register moved
    down to the class pack (where four rows is the whole of it) and this
    screen became the gate in front of it.

    A visible grade with no published papers still appears, showing 0/0: an
    assigned grade that is empty is a fact worth seeing, and silently
    dropping it would read as "you aren't assigned this grade".
    """
    grades = sorted(_visible_grades(request.user))
    stats = {
        row["grade"]: row
        for row in (
            Paper.objects.filter(grade__in=grades, is_published=True)
            .values("grade")
            .annotate(
                paper_count=Count("id", distinct=True),
                issued_count=Count(
                    "id", filter=Q(generations__isnull=False), distinct=True
                ),
            )
        )
    }
    return render(
        request,
        "diagnostics/paper_index.html",
        {
            "grades": [
                {
                    "number": grade,
                    "pack_count": CLASSES_PER_GRADE,
                    "paper_count": stats.get(grade, {}).get("paper_count", 0),
                    "issued_count": stats.get(grade, {}).get("issued_count", 0),
                }
                for grade in grades
            ],
            "classes_per_grade": CLASSES_PER_GRADE,
            "variants_per_class": VARIANTS_PER_CLASS,
            "generation_open": GenerationWindow.load().is_open,
        },
    )


@login_required
def grade_detail(request, grade: int):
    """Step two: which class. Four packs, each holding four of the grade's
    sixteen variants."""
    if grade not in _visible_grades(request.user):
        raise Http404("No papers here.")

    by_variant = {
        paper.variant: paper
        for paper in Paper.objects.filter(grade=grade, is_published=True).annotate(
            issue_count=Count("generations")
        )
    }
    packs = []
    for number in CLASS_NUMBERS:
        members = [
            by_variant[letter]
            for letter in variants_for_class(number)
            if letter in by_variant
        ]
        packs.append(
            {
                "number": number,
                "display_name": display_name_for(grade, number),
                "span": variant_span(number),
                "paper_count": len(members),
                "issued_count": sum(1 for paper in members if paper.issue_count),
            }
        )

    return render(
        request,
        "diagnostics/grade_detail.html",
        {
            "grade": grade,
            "packs": packs,
            "paper_count": len(by_variant),
            "variants_per_class": VARIANTS_PER_CLASS,
            "generation_open": GenerationWindow.load().is_open,
        },
    )


@login_required
def class_pack(request, grade: int, number: int):
    """Step three: the register, narrowed to one class's four papers."""
    if number not in CLASS_NUMBERS:
        raise Http404("No such class.")
    return render(
        request,
        "diagnostics/class_pack.html",
        {
            "grade": grade,
            "class_number": number,
            "class_display_name": display_name_for(grade, number),
            "span": variant_span(number),
            "papers": _pack_papers(request.user, grade, number),
            "prev_class": number - 1 if number > 1 else None,
            "next_class": number + 1 if number < CLASSES_PER_GRADE else None,
            "generation_open": GenerationWindow.load().is_open,
        },
    )


def _annotate_for_display(listening, reading, writing):
    """Attach template-friendly extras to the question/clip dicts and model
    instances paper_sections() returns, without adding a real model field
    for something only this screen needs: lettered options, a running
    question number across both recordings, and a stripped filename in
    place of the full media path.

    Mutates the model instances in place (a transient attribute, not a
    save) — consistent with rendering.py's own stance that a renderer
    needing something extra from a question should be able to reach for
    it directly rather than have a new field plumbed through first.
    """
    for clip_index, clip in enumerate(listening["clips"]):
        clip["audio_name"] = os.path.basename(clip["audio"].name) if clip["audio"] else ""
        for question in clip["questions"]:
            question.display_number = clip_index * 5 + question.position
            question.option_rows = option_rows(question.options or [])
            question.inline_blank = needs_inline_blank(question.stem, question.options)
            question.image_name = os.path.basename(question.image.name) if question.image else ""

    for question in reading["questions"]:
        question.option_rows = option_rows(question.options or [])
        question.inline_blank = needs_inline_blank(question.stem, question.options)

    for question in writing["questions"]:
        question.option_rows = option_rows(question.options or [])
        question.inline_blank = needs_inline_blank(question.stem, question.options)


@login_required
def paper_detail(request, grade: int, variant: str):
    """One paper on screen. Answers show only for staff — a teacher without
    staff rights sees the same paper with a blank answer column; the key
    travels inside the downloaded pack instead, which is what they actually
    administer from."""
    paper = _get_visible_paper(request.user, grade, variant)
    listening, reading, writing, speaking = paper_sections(paper)
    _annotate_for_display(listening, reading, writing)
    return render(
        request,
        "diagnostics/paper_detail.html",
        {
            "paper": paper,
            "listening": listening,
            "reading": reading,
            "reading_groups": reading_groups(reading["questions"]),
            "writing": writing,
            "speaking": speaking,
            "answer_key": answer_key(paper) if request.user.is_staff else None,
            "generation_open": GenerationWindow.load().is_open,
            "docx_available": docx_available(),
            "class_number": class_for_variant(paper.variant),
        },
    )


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
        raise Http404("Downloads are currently closed.")

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
    seen_clips = set()
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
        # Only the first set of each clip carries the anchor: the index
        # above lists clips, not sets, and two sets of the same clip would
        # otherwise claim the same id.
        clip = question_set.clip
        anchor = "" if clip.number in seen_clips else f"clip-{clip.number}"
        seen_clips.add(clip.number)

        entries.append({
            "question_set": question_set,
            "clip": clip,
            "pairs": pairs,
            "title": usage_title(pairs),
            "questions": questions,
            "anchor": anchor,
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
            "clip_numbers": sorted(seen_clips),
            "balance": key_balance(
                ListeningQuestion.objects.filter(question_set_id__in=visible_ids)
            ),
        },
    )
