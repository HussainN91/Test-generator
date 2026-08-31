"""Admin registration for the diagnostics app.

The admin doubles as the review queue (config/urls.py), so everything the
import pipeline produces has to be visible here. Two decisions worth stating:

1. Questions are shown as inlines on their parent (clip, passage, paper)
   rather than only as separate changelists. A reviewer's unit of work is a
   whole clip or a whole paper, not one question, and paging between twelve
   separate changelists to read one paper is not review, it is archaeology.

2. The four imported content banks (AudioClip, ReadingPassage,
   WritingQuestion, SpeakingPrompt) have add and delete switched off. They are
   regenerated wholesale by the import_* management commands, so anything typed
   in here is overwritten without warning on the next import. Turning the
   buttons off makes that structural instead of a footnote. Papers and the
   tracking models are hand-managed and stay fully editable.
"""

from django.contrib import admin

from diagnostics.models import (
    AudioClip, GenerationEvent, GenerationWindow, KeyVerification,
    ListeningQuestion, ListeningQuestionSet, Paper, PaperSpeakingPrompt,
    PaperWritingQuestion, ReadingPassage, ReadingQuestion, SpeakingPrompt,
    SpeakingRubric, TeacherGradeAssignment, WritingQuestion,
)


class ImportedContentAdmin(admin.ModelAdmin):
    """Base for banks rebuilt by the import commands: browse, do not create.

    Editing an existing row is still allowed — a reviewer fixing one typo
    before a re-import is a legitimate act — but adding or deleting rows would
    put the bank out of step with its source file, and the next import would
    silently undo it.
    """

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ListeningQuestionSetInline(admin.TabularInline):
    model = ListeningQuestionSet
    extra = 0
    fields = ("number",)
    ordering = ("number",)
    verbose_name = "question set"
    verbose_name_plural = "question sets on this recording"


class ListeningQuestionInline(admin.TabularInline):
    model = ListeningQuestion
    extra = 0
    fields = ("position", "stem", "options", "image", "answer", "acceptable_answers")
    ordering = ("position",)
    verbose_name = "question"
    verbose_name_plural = "questions in this set"


@admin.register(AudioClip)
class AudioClipAdmin(ImportedContentAdmin):
    list_display = ("number", "task_type", "set_count", "question_count", "has_audio")
    list_filter = ("task_type",)
    search_fields = ("number", "intro_text")
    ordering = ("number",)
    inlines = [ListeningQuestionSetInline]

    @admin.display(description="sets")
    def set_count(self, obj):
        return obj.question_sets.count()

    @admin.display(description="questions")
    def question_count(self, obj):
        return ListeningQuestion.objects.filter(question_set__clip=obj).count()

    @admin.display(boolean=True, description="audio file")
    def has_audio(self, obj):
        return bool(obj.audio_file)


@admin.register(ListeningQuestionSet)
class ListeningQuestionSetAdmin(ImportedContentAdmin):
    list_display = ("__str__", "clip", "number", "question_count")
    list_filter = ("number", "clip__task_type")
    ordering = ("clip__number", "number")
    list_select_related = ("clip",)
    inlines = [ListeningQuestionInline]

    @admin.display(description="questions")
    def question_count(self, obj):
        return obj.questions.count()


@admin.register(ListeningQuestion)
class ListeningQuestionAdmin(ImportedContentAdmin):
    list_display = ("__str__", "question_set", "position", "answer", "has_image")
    list_filter = ("question_set__number", "question_set__clip__task_type",
                   "question_set__clip__number")
    search_fields = ("stem", "answer")
    ordering = ("question_set__clip__number", "question_set__number", "position")
    list_select_related = ("question_set__clip",)

    @admin.display(boolean=True, description="image")
    def has_image(self, obj):
        return bool(obj.image)


class ReadingQuestionInline(admin.TabularInline):
    model = ReadingQuestion
    extra = 0
    fields = ("position", "subtype", "stem", "options", "answer", "acceptable_answers")
    ordering = ("position",)
    verbose_name = "question"
    verbose_name_plural = "questions on this passage"


@admin.register(ReadingPassage)
class ReadingPassageAdmin(ImportedContentAdmin):
    list_display = ("label", "title", "word_count", "question_count")
    search_fields = ("label", "title", "body")
    ordering = ("label",)
    readonly_fields = ("word_count",)
    inlines = [ReadingQuestionInline]

    @admin.display(description="questions")
    def question_count(self, obj):
        return obj.questions.count()


@admin.register(ReadingQuestion)
class ReadingQuestionAdmin(ImportedContentAdmin):
    list_display = ("__str__", "passage", "position", "subtype", "answer")
    list_filter = ("subtype", "passage__label")
    search_fields = ("stem", "answer")
    ordering = ("passage__label", "position")
    list_select_related = ("passage",)


@admin.register(WritingQuestion)
class WritingQuestionAdmin(ImportedContentAdmin):
    list_display = ("pk", "subtype", "short_stem", "answer")
    list_filter = ("subtype",)
    search_fields = ("stem",)
    ordering = ("subtype", "pk")

    @admin.display(description="stem")
    def short_stem(self, obj):
        return obj.stem[:80]


@admin.register(SpeakingPrompt)
class SpeakingPromptAdmin(ImportedContentAdmin):
    list_display = ("pk", "task", "short_prompt", "marks")
    list_filter = ("task",)
    search_fields = ("prompt",)
    ordering = ("task", "pk")

    @admin.display(description="prompt")
    def short_prompt(self, obj):
        return obj.prompt[:80]


@admin.register(SpeakingRubric)
class SpeakingRubricAdmin(admin.ModelAdmin):
    """Marking guidance is authored here, not imported — stays editable."""

    list_display = ("task", "marks", "indicators")
    ordering = ("task",)


class PaperWritingQuestionInline(admin.TabularInline):
    model = PaperWritingQuestion
    extra = 0
    ordering = ("position",)
    autocomplete_fields = ("question",)
    verbose_name = "writing question"
    verbose_name_plural = "writing questions (10 per paper, in order)"


class PaperSpeakingPromptInline(admin.TabularInline):
    model = PaperSpeakingPrompt
    extra = 0
    ordering = ("position",)
    autocomplete_fields = ("prompt",)
    verbose_name = "speaking prompt"
    verbose_name_plural = "speaking prompts (5 per paper, in order)"


@admin.register(Paper)
class PaperAdmin(admin.ModelAdmin):
    list_display = (
        "__str__", "grade", "variant", "listening_clip_1", "listening_clip_2",
        "reading_passage", "is_published",
    )
    list_filter = ("grade", "variant", "is_published")
    list_select_related = ("listening_clip_1", "listening_clip_2", "reading_passage")
    ordering = ("grade", "variant")
    fields = (
        "grade", "variant", "listening_clip_1", "listening_clip_2",
        "reading_passage", "is_published",
    )
    inlines = [PaperWritingQuestionInline, PaperSpeakingPromptInline]


@admin.register(PaperWritingQuestion)
class PaperWritingQuestionAdmin(admin.ModelAdmin):
    list_display = ("paper", "position", "question")
    list_filter = ("paper__grade",)
    list_select_related = ("paper", "question")
    ordering = ("paper", "position")


@admin.register(PaperSpeakingPrompt)
class PaperSpeakingPromptAdmin(admin.ModelAdmin):
    list_display = ("paper", "position", "prompt")
    list_filter = ("paper__grade",)
    list_select_related = ("paper", "prompt")
    ordering = ("paper", "position")


@admin.register(KeyVerification)
class KeyVerificationAdmin(admin.ModelAdmin):
    list_display = ("verified_by", "verified_at", "is_current")
    readonly_fields = ("verified_at",)

    @admin.display(boolean=True, description="still valid")
    def is_current(self, obj):
        return obj.fingerprint == KeyVerification.current_fingerprint()


@admin.register(GenerationWindow)
class GenerationWindowAdmin(admin.ModelAdmin):
    list_display = ("__str__", "is_open", "updated_at")
    readonly_fields = ("updated_at",)


@admin.register(TeacherGradeAssignment)
class TeacherGradeAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "grade")
    list_filter = ("grade",)
    search_fields = ("user__username",)
    ordering = ("user__username", "grade")
    list_select_related = ("user",)


@admin.register(GenerationEvent)
class GenerationEventAdmin(admin.ModelAdmin):
    list_display = ("user", "paper", "generated_at", "export_format")
    list_filter = ("paper__grade", "export_format")
    search_fields = ("user__username",)
    date_hierarchy = "generated_at"
    ordering = ("-generated_at",)
    list_select_related = ("user", "paper")
