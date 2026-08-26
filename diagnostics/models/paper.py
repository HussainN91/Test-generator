"""The forty-eight fixed diagnostic papers (spec 4.2, paper layer; Design
Revision 2).

Listening (2 clips) and Reading (1 passage) are still single foreign keys —
each paper picks exactly one fixed component. Writing and Speaking moved to a
shared-bank-plus-sampled-selection model (Design Revision 1 section 5): each
paper picks 10 WritingQuestion rows and 5 SpeakingPrompt rows out of a shared
pool, recorded via PaperWritingQuestion/PaperSpeakingPrompt.

clean() originally enforced a rule the client called inviolable — the four
variants within a grade share nothing. Design Revision 2 widened each grade
to sixteen variants, at which point zero-sharing is arithmetically
unsatisfiable (five picture clips against sixteen slots, ten speaking
prompts per task against sixteen slots, and so on). That reversal is
deliberate and documented: clean() now enforces a per-component reuse cap
(REUSE_CAPS) instead, checked at the level of individual sampled items for
writing/speaking, not just at the container level.

Note: clean() is only invoked by an explicit full_clean() call (as the tests
do) or a ModelForm — plain .save()/.create()/update_or_create() skip it, as
will the bulk sampling commands that populate real papers. That is why a
separate check_papers command re-derives the same cap rule independently
from what is actually stored (diagnostics/verification.py).
"""

from collections import Counter

from django.core.exceptions import ValidationError
from django.db import models

from diagnostics.constants import GRADES, PICTURE_CLIPS, REUSE_CAPS, VARIANTS
from diagnostics.models.content import (
    AudioClip, ReadingPassage, SpeakingPrompt, WritingQuestion,
)


class Paper(models.Model):
    grade = models.PositiveSmallIntegerField(choices=[(g, f"Grade {g}") for g in GRADES])
    variant = models.CharField(max_length=1, choices=[(v, v) for v in VARIANTS])

    listening_clip_1 = models.ForeignKey(
        AudioClip, on_delete=models.PROTECT, related_name="papers_as_first"
    )
    listening_clip_2 = models.ForeignKey(
        AudioClip, on_delete=models.PROTECT, related_name="papers_as_second"
    )
    reading_passage = models.ForeignKey(
        ReadingPassage, on_delete=models.PROTECT, related_name="papers"
    )
    writing_questions = models.ManyToManyField(
        WritingQuestion, through="PaperWritingQuestion", related_name="papers"
    )
    speaking_prompts = models.ManyToManyField(
        SpeakingPrompt, through="PaperSpeakingPrompt", related_name="papers"
    )

    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ["grade", "variant"]
        constraints = [
            models.UniqueConstraint(fields=["grade", "variant"], name="unique_grade_variant")
        ]

    def __str__(self):
        return f"G{self.grade}-{self.variant}"

    def shared_components(self):
        """Every capped component this paper occupies, as (cap key, pk).

        Cap keys match REUSE_CAPS. The listening clips are distinguished by
        task type because they carry different caps: only five picture clips
        exist against sixteen variants, so they are allowed four uses each,
        while the fifteen rotating clips are allowed two.
        """
        pairs = []
        for clip in (self.listening_clip_1, self.listening_clip_2):
            if clip is None:
                continue
            key = (
                "picture_clip"
                if clip.number in PICTURE_CLIPS
                else "rotating_clip"
            )
            pairs.append((key, clip.pk))
        if self.reading_passage_id:
            pairs.append(("reading_passage", self.reading_passage_id))
        if self.pk:
            pairs += [
                ("writing_question", pk)
                for pk in self.writing_questions.values_list("pk", flat=True)
            ]
            pairs += [
                ("speaking_prompt", pk)
                for pk in self.speaking_prompts.values_list("pk", flat=True)
            ]
        return pairs

    def clean(self):
        if self.listening_clip_1_id and self.listening_clip_1_id == self.listening_clip_2_id:
            raise ValidationError(
                {"listening_clip_2": "A paper cannot use the same clip twice."}
            )

        siblings = Paper.objects.filter(grade=self.grade).exclude(pk=self.pk)
        used = Counter()
        for sibling in siblings:
            used.update(sibling.shared_components())

        for key, pk in self.shared_components():
            cap = REUSE_CAPS[key]
            if used[(key, pk)] >= cap:
                raise ValidationError(
                    f"Grade {self.grade}: this {key.replace('_', ' ')} is "
                    f"already used by {used[(key, pk)]} variants, and the "
                    f"reuse cap is {cap}."
                )


class PaperWritingQuestion(models.Model):
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="writing_slots")
    question = models.ForeignKey(WritingQuestion, on_delete=models.PROTECT)
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["paper", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["paper", "position"], name="unique_paper_writing_position"
            ),
            models.UniqueConstraint(
                fields=["paper", "question"], name="unique_paper_writing_question"
            ),
        ]


class PaperSpeakingPrompt(models.Model):
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="speaking_slots")
    prompt = models.ForeignKey(SpeakingPrompt, on_delete=models.PROTECT)
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["paper", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["paper", "position"], name="unique_paper_speaking_position"
            ),
            models.UniqueConstraint(
                fields=["paper", "prompt"], name="unique_paper_speaking_prompt"
            ),
        ]
