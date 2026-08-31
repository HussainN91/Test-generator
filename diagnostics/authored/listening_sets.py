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
