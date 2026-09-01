"""Authored and extracted diagnostic content (spec 4.2, content layer).

Static: written once by the offline pipeline, read-only at runtime.
"""

import hashlib

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from diagnostics.constants import (
    MAX_PASSAGE_WORDS, MIN_PASSAGE_WORDS, SETS_PER_CLIP, TaskType,
)


def _position_validators(maximum):
    return [MinValueValidator(1), MaxValueValidator(maximum)]


class AudioClip(models.Model):
    """One of the client's 20 listening clips."""

    number = models.PositiveSmallIntegerField(unique=True)
    task_type = models.CharField(max_length=16, choices=TaskType.choices)
    intro_text = models.TextField(
        blank=True, help_text='The "You will hear..." framing read before the clip.'
    )
    audio_file = models.FileField(upload_to="diagnostics/audio/", blank=True)
    transcript = models.TextField(
        blank=True,
        help_text=(
            "The full spoken text of the recording, imported from "
            "media/diagnostics/audio/transcripts-full.md. Kept on the clip "
            "rather than the question set because both sets ask about the "
            "same audio and are checked against the same words."
        ),
    )

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return f"Clip {self.number} ({TaskType(self.task_type).label})"


class ListeningQuestionSet(models.Model):
    """One paper's worth of questions about one recording.

    The layer this model adds is what lets the two variants sitting in the
    same room hear the same audio and answer different questions. Before it,
    ListeningQuestion hung off AudioClip directly under unique(clip,
    position), so a clip had exactly one set of five questions and pairing
    the audio per group would have produced two byte-identical papers.

    Two sets per clip, no more (SETS_PER_CLIP). The rotating clips get two
    fully distinct sets; the five picture clips only have seven recorded
    items between their two sets, so three items are shared - an accepted,
    documented limitation, not something a third set could fix.
    """

    clip = models.ForeignKey(
        AudioClip, on_delete=models.CASCADE, related_name="question_sets"
    )
    number = models.PositiveSmallIntegerField(
        validators=_position_validators(SETS_PER_CLIP),
        help_text="1 or 2. Which of the recording's two question papers this is.",
    )

    class Meta:
        ordering = ["clip__number", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["clip", "number"], name="unique_listening_set_number"
            )
        ]

    def __str__(self):
        return f"Clip {self.clip.number} set {self.number}"


class ListeningQuestion(models.Model):
    question_set = models.ForeignKey(
        ListeningQuestionSet, on_delete=models.CASCADE, related_name="questions"
    )
    position = models.PositiveSmallIntegerField(validators=_position_validators(5))
    stem = models.TextField()
    options = models.JSONField(
        default=list, blank=True,
        help_text="Option texts for mcq3/true_false. Empty for picture and gap-fill.",
    )
    image = models.ImageField(
        upload_to="diagnostics/listening/", blank=True,
        help_text="Picture clips only: the A/B/C option strip for this question.",
    )
    answer = models.CharField(max_length=200)
    acceptable_answers = models.JSONField(
        default=list, blank=True, help_text="Alternative correct answers for gap-fill."
    )

    class Meta:
        ordering = ["question_set__clip__number", "question_set__number", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["question_set", "position"], name="unique_listening_position"
            )
        ]

    def __str__(self):
        return f"{self.question_set} Q{self.position}"

    @property
    def clip(self):
        """The recording this question is about.

        Kept as a read-only property because the extraction and verification
        code reads `question.clip.number` in a dozen places and none of it
        cares which set the question came from.
        """
        return self.question_set.clip


class ReadingSubtype(models.TextChoices):
    TRUE_FALSE_NG = "true_false_ng", "TRUE / FALSE / NOT GIVEN"
    MCQ = "mcq", "Four-option multiple choice"
    COMPLETION = "completion", "Sentence completion (max two words)"
    HEADING_MATCHING = "heading_matching", "Match paragraph to heading"
    PARAGRAPH_MATCHING = "paragraph_matching", "Match statement to paragraph"


class ReadingPassage(models.Model):
    label = models.CharField(max_length=8, unique=True, help_text="R01..R15")
    title = models.CharField(max_length=255)
    body = models.TextField()
    word_count = models.PositiveSmallIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["label"]

    def __str__(self):
        return f"{self.label} — {self.title}"

    def save(self, *args, **kwargs):
        self.word_count = len(self.body.split())
        super().save(*args, **kwargs)

    def clean(self):
        count = len(self.body.split())
        if not MIN_PASSAGE_WORDS <= count <= MAX_PASSAGE_WORDS:
            raise ValidationError(
                {"body": f"Passage must be {MIN_PASSAGE_WORDS}-{MAX_PASSAGE_WORDS} "
                         f"words; this one is {count}."}
            )


class ReadingQuestion(models.Model):
    passage = models.ForeignKey(
        ReadingPassage, on_delete=models.CASCADE, related_name="questions"
    )
    position = models.PositiveSmallIntegerField(validators=_position_validators(10))
    #: max_length=20: longest current subtype value is "paragraph_matching"
    #: (18 chars) — only 2 chars of headroom. A longer subtype name will need
    #: a migration to widen this.
    subtype = models.CharField(max_length=20, choices=ReadingSubtype.choices)
    stem = models.TextField()
    options = models.JSONField(default=list, blank=True)
    answer = models.CharField(max_length=200)
    acceptable_answers = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["passage__label", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["passage", "position"], name="unique_reading_position"
            )
        ]

    def __str__(self):
        return f"{self.passage.label} Q{self.position}"


class WritingSubtype(models.TextChoices):
    GRAMMAR = "grammar", "Grammar"
    VOCABULARY = "vocabulary", "Vocabulary"
    JUMBLED = "jumbled", "Jumbled paragraph"
    FILL_BLANK = "fill_blank", "Fill in the blanks"


class WritingQuestion(models.Model):
    """One item in the shared 200-question writing bank (Design Revision 1).

    No longer a child of a fixed WritingSet — each Paper selects 10 of these
    via PaperWritingQuestion (diagnostics/models/paper.py).
    """

    subtype = models.CharField(max_length=16, choices=WritingSubtype.choices)
    stem = models.TextField()
    options = models.JSONField(default=list)
    answer = models.CharField(max_length=8, help_text="Option letter A-D.")

    class Meta:
        ordering = ["subtype", "pk"]

    def __str__(self):
        return f"{self.get_subtype_display()}: {self.stem[:40]}"


class SpeakingTask(models.TextChoices):
    INTRODUCTION = "introduction", "Personal introduction and familiar topic"
    EXPERIENCE = "experience", "Describe an experience or event"
    DESCRIPTION = "description", "Topic description and comparison"
    ROLE_PLAY = "role_play", "Role play / problem solving"
    OPINION = "opinion", "Opinion and discussion"


class SpeakingPrompt(models.Model):
    """One item in the shared 50-prompt speaking bank (Design Revision 1).

    No longer a child of a fixed SpeakingSet — each Paper selects 5 of these
    (one per task type) via PaperSpeakingPrompt (diagnostics/models/paper.py).
    """

    task = models.CharField(max_length=16, choices=SpeakingTask.choices)
    prompt = models.TextField()
    bullets = models.JSONField(default=list, blank=True)
    marks = models.PositiveSmallIntegerField(default=2)

    class Meta:
        ordering = ["task", "pk"]

    def __str__(self):
        return f"{self.get_task_display()}: {self.prompt[:40]}"


class SpeakingRubric(models.Model):
    """Fixed marking guidance per task type (Design Revision 1 section 4).

    One row per SpeakingTask value, shared across every prompt of that task -
    not per-prompt, since the rubric describes the task, not the specific
    question.
    """

    task = models.CharField(max_length=16, choices=SpeakingTask.choices, unique=True)
    marks = models.PositiveSmallIntegerField(default=2)
    indicators = models.TextField()

    class Meta:
        ordering = ["task"]

    def __str__(self):
        return f"{self.get_task_display()} rubric"


class KeyVerification(models.Model):
    """Records that a human checked all 100 listening answers (spec 9).

    The fingerprint is a hash of every answer. If any answer changes after
    sign-off, the fingerprint stops matching and the sign-off lapses — so a
    re-import silently invalidates stale approval instead of inheriting it.
    """

    verified_by = models.CharField(max_length=120)
    verified_at = models.DateTimeField(auto_now=True)
    fingerprint = models.CharField(max_length=64)

    class Meta:
        verbose_name = "listening key verification"

    def __str__(self):
        return f"verified by {self.verified_by} at {self.verified_at:%Y-%m-%d}"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @staticmethod
    def current_fingerprint():
        """Hash every answer in the bank, set number included.

        The set number is part of the key: without it, clip 3 set 1 Q2 and
        clip 3 set 2 Q2 hash into the same slot and a swapped pair of answers
        between the two sets would leave the fingerprint unchanged.

        Adding the second sets necessarily changes this digest, so an
        existing sign-off lapses and must be re-done by a human. That is the
        intended behaviour, not a bug to route around.
        """
        rows = ListeningQuestion.objects.order_by(
            "question_set__clip__number", "question_set__number", "position"
        ).values_list(
            "question_set__clip__number", "question_set__number", "position", "answer"
        )
        digest = hashlib.sha256()
        for clip_number, set_number, position, answer in rows:
            digest.update(f"{clip_number}:{set_number}:{position}:{answer}\n".encode("utf-8"))
        return digest.hexdigest()

    @classmethod
    def load(cls):
        return cls.objects.filter(pk=1).first()

    @classmethod
    def is_signed_off(cls):
        record = cls.load()
        return bool(record) and record.fingerprint == cls.current_fingerprint()
