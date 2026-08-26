"""Who may generate, who did, and whether generation is open (spec 4.2).

`TeacherGradeAssignment` is what makes "who has *not* generated" answerable:
without a declared expected set, absence cannot be distinguished from
irrelevance. At Expert Council merge time this is replaced by a resolver
backed by that system's roster (spec 7).
"""

from django.conf import settings
from django.db import models

from diagnostics.constants import GRADES
from diagnostics.models.paper import Paper


class GenerationWindow(models.Model):
    """Singleton switch letting admins open or close test generation."""

    is_open = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "generation window"

    def __str__(self):
        return "open" if self.is_open else "closed"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        window, _created = cls.objects.get_or_create(pk=1)
        return window


class TeacherGradeAssignment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="diagnostic_grades",
    )
    grade = models.PositiveSmallIntegerField(choices=[(g, f"Grade {g}") for g in GRADES])

    class Meta:
        ordering = ["user__username", "grade"]
        constraints = [
            models.UniqueConstraint(fields=["user", "grade"], name="unique_teacher_grade")
        ]

    def __str__(self):
        return f"{self.user} — Grade {self.grade}"

    @classmethod
    def grades_for(cls, user):
        return cls.objects.filter(user=user).values_list("grade", flat=True)


class ExportFormat(models.TextChoices):
    STUDENT = "student", "Test paper"
    ANSWER_KEY = "answer_key", "Answer key"
    EXAMINER = "examiner", "Speaking pack"
    AUDIO_1 = "audio_1", "Audio, recording 1"
    AUDIO_2 = "audio_2", "Audio, recording 2"


class GenerationEvent(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="diagnostic_generations",
    )
    paper = models.ForeignKey(Paper, on_delete=models.PROTECT, related_name="generations")
    generated_at = models.DateTimeField(auto_now_add=True)
    export_format = models.CharField(
        max_length=16, choices=ExportFormat.choices, default=ExportFormat.STUDENT,
    )

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self):
        return f"{self.user} generated {self.paper} at {self.generated_at:%Y-%m-%d %H:%M}"
