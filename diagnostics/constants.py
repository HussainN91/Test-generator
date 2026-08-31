"""Verified static facts about the diagnostic test content and its fixed patterns.

The clip/task-type/paper-allocation facts were checked against the client's
source files on 2026-08-24. The subtype-count and word-bound constants encode
the fixed question pattern from the client's diagnostic spec. None of this is
guessed or re-derived at runtime — it is fixed content and a fixed pattern.
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

#: The 25 images appear in the .docx in document order, five per picture clip,
#: in ascending clip order. Index -> (clip number, question position).
IMAGE_SLOTS = [
    (clip, position)
    for clip in (1, 5, 9, 13, 15)
    for position in (1, 2, 3, 4, 5)
]

GRADES = (9, 10, 11)

#: Sixteen variants per grade (Design Revision 2, section 2.1), up from four.
#: Single characters only - Paper.variant is max_length=1.
VARIANTS = tuple("ABCDEFGHIJKLMNOP")

#: How many times one component may repeat within a single grade
#: (Design Revision 2, section 2). This REPLACES the original
#: "variants within a grade share zero content" rule, which is
#: arithmetically unsatisfiable at 16 variants - the bank holds 20 clips,
#: 15 passages and 10 prompts per task against 32/16/16 slots needed.
#:
#: Caps are scoped per grade; cross-grade reuse remains unrestricted.
#: Writing keeps a cap of 1 (genuine zero reuse) because its pool of 50
#: per subtype supports it - expressed as a cap rather than a special case
#: so one code path covers every component.
REUSE_CAPS = {
    "picture_clip": 4,      # 5 in the bank x 4 = 20 slots, 16 needed
    "rotating_clip": 2,     # 15 in the bank x 2 = 30 slots, 16 needed
    "reading_passage": 2,   # 15 in the bank x 2 = 30 slots, 16 needed
    "speaking_prompt": 2,   # 10 per task x 2 = 20 slots, 16 needed
    "writing_question": 1,  # 50 per subtype, at most 48 needed
}

#: The five picture clips carry all 25 images in the bank. Every paper takes
#: exactly one, so every paper gets exactly five photo questions - this is
#: what fixes the uneven photo distribution (Design Revision 2, section 3).
PICTURE_CLIPS = tuple(
    number for number, task in CLIP_TASK_TYPES.items() if task == TaskType.PICTURE
)

#: Question sets per clip. Two variants sit in one room hearing one
#: recording, so one recording must carry two different question papers -
#: which is exactly two sets, no more. Picture clips can only just support
#: this (seven recorded items against 5 + 5 slots, so 3 items appear in both
#: sets); a third set is arithmetically impossible without new audio.
SETS_PER_CLIP = 2

#: The other fifteen clips, grouped by task type so a future allocator can
#: rotate evenly across the three non-picture types.
ROTATING_CLIPS_BY_TYPE = {
    task: tuple(
        number for number, clip_task in CLIP_TASK_TYPES.items() if clip_task == task
    )
    for task in (TaskType.MCQ3, TaskType.GAP_FILL, TaskType.TRUE_FALSE)
}

#: Option letters used by every four-option question type.
OPTION_LETTERS = ["A", "B", "C", "D"]

#: Widened 2026-08-24 to match the real content bank (203-274 words across
#: 15 passages) rather than the client's aspirational 150-180 stated pattern
#: — see Design Revision 1, spec section 2.
MIN_PASSAGE_WORDS = 150
MAX_PASSAGE_WORDS = 300

#: Required question counts per subtype, per set (spec 3.3).
#: Defined here once; both the models and the authored-content validators
#: import them, so the two can never disagree about the pattern.
READING_SUBTYPE_COUNTS = {"true_false_ng": 5, "mcq": 3, "completion": 2}
WRITING_SUBTYPE_COUNTS = {"grammar": 3, "vocabulary": 2, "jumbled": 3, "fill_blank": 2}
SPEAKING_TASK_ORDER = ["introduction", "experience", "description", "role_play", "opinion"]
