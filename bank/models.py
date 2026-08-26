"""Item bank (spec 3.4-3.5): reviewed, ready-to-sample questions.

Items are produced by the *offline* pipeline and imported here. The deployed
app only ever reads from this table — it never calls an LLM (spec 6).

Type-specific payload lives in `payload` (JSON) rather than in six sparse
column sets; `QUESTION_TYPE_FIELDS` documents the expected keys per type and
`clean()` enforces them.
"""

from django.core.exceptions import ValidationError
from django.db import models

from content.models import GrammarPoint, Unit, VocabularyEntry


class QuestionType(models.TextChoices):
    GAP_FILL = "gap_fill", "Gap-fill (contextual)"
    WORD_FORMATION = "word_formation", "Word formation"
    KEY_WORD_TRANSFORMATION = "key_word_transformation", "Key word transformation"
    ERROR_CORRECTION = "error_correction", "Error correction"
    MATCHING = "matching", "Matching"
    MULTIPLE_CHOICE = "multiple_choice", "Multiple choice"
    # "Which word does not belong?" Split from MULTIPLE_CHOICE because the two
    # test different things (recall of a definition vs. spotting a semantic
    # outlier) even though they render identically.
    ODD_ONE_OUT = "odd_one_out", "Odd one out"


#: Required payload keys per question type, mirroring the spec 3.5 table.
QUESTION_TYPE_FIELDS = {
    QuestionType.GAP_FILL: ["sentence_with_gap", "target_word"],
    QuestionType.WORD_FORMATION: ["sentence_with_gap", "root_word", "correct_form", "target_pos"],
    QuestionType.KEY_WORD_TRANSFORMATION: ["original_sentence", "keyword", "acceptable_answers"],
    QuestionType.ERROR_CORRECTION: ["sentence_with_error", "error_type", "corrected_word_phrase"],
    QuestionType.MATCHING: ["item_set"],
    QuestionType.MULTIPLE_CHOICE: ["sentence", "options", "correct_option"],
    QuestionType.ODD_ONE_OUT: ["sentence", "options", "correct_option"],
}


class ReviewStatus(models.TextChoices):
    DRAFT = "draft", "Draft (not yet validated)"
    FLAGGED = "flagged", "Flagged for human review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class Item(models.Model):
    """One reviewed question. Only APPROVED items are eligible for assembly."""

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="items")
    grammar_point = models.ForeignKey(
        GrammarPoint, on_delete=models.SET_NULL, null=True, blank=True, related_name="items"
    )
    target_vocabulary = models.ForeignKey(
        VocabularyEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name="items"
    )

    question_type = models.CharField(max_length=32, choices=QuestionType.choices, db_index=True)
    payload = models.JSONField(
        help_text="Type-specific fields; see QUESTION_TYPE_FIELDS.",
    )
    model_answer = models.TextField(
        help_text="The single fixed answer a teacher ticks against (spec priority 2)."
    )
    acceptable_answers = models.JSONField(
        default=list,
        blank=True,
        help_text="Short list of alternative correct answers, for transformations.",
    )

    review_status = models.CharField(
        max_length=16, choices=ReviewStatus.choices, default=ReviewStatus.DRAFT, db_index=True
    )
    review_notes = models.TextField(blank=True)

    # Validation-layer results (spec 3.3), recorded so a reviewer sees *why* an
    # item was flagged rather than re-deriving it.
    spacy_validated = models.BooleanField(default=False)
    llm_validated = models.BooleanField(default=False)
    gap_uniqueness_checked = models.BooleanField(
        default=False,
        help_text="Gap-fill only: verified that no other eligible unit word fits the blank.",
    )

    generation_batch = models.CharField(max_length=64, blank=True, db_index=True)
    content_hash = models.CharField(
        max_length=64, unique=True, help_text="Deduplicates identical items across runs."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["unit", "question_type", "id"]
        indexes = [models.Index(fields=["unit", "question_type", "review_status"])]

    def __str__(self):
        return f"[{self.get_question_type_display()}] {self.model_answer[:40]}"

    def clean(self):
        missing = [
            key
            for key in QUESTION_TYPE_FIELDS.get(self.question_type, [])
            if key not in (self.payload or {})
        ]
        if missing:
            raise ValidationError(
                {"payload": f"{self.question_type} requires payload keys: {', '.join(missing)}"}
            )
