"""Read-oriented admin for the syllabus. Content is owned by the source guides:
edit the .txt and re-run `import_guide` rather than hand-editing rows here.
"""

from django.contrib import admin

from content.models import (
    Grade,
    GrammarPoint,
    SampleSentence,
    Unit,
    VocabularyCategory,
    VocabularyEntry,
)


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ("number", "source_file", "unit_count")
    search_fields = ("number",)

    @admin.display(description="Units")
    def unit_count(self, grade):
        return grade.units.count()


class VocabularyEntryInline(admin.TabularInline):
    model = VocabularyEntry
    extra = 0
    fields = ("word", "part_of_speech", "category", "definition")
    show_change_link = True


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("__str__", "grade", "number", "vocabulary_count", "item_count")
    list_filter = ("grade",)
    search_fields = ("title", "theme", "number")
    inlines = (VocabularyEntryInline,)

    @admin.display(description="Vocabulary")
    def vocabulary_count(self, unit):
        return unit.vocabulary.count()

    @admin.display(description="Bank items")
    def item_count(self, unit):
        return unit.items.count()


@admin.register(VocabularyEntry)
class VocabularyEntryAdmin(admin.ModelAdmin):
    list_display = ("word", "part_of_speech", "unit", "cefr_level", "definition")
    list_filter = ("part_of_speech", "cefr_level", "unit__grade")
    search_fields = ("word", "lemma", "definition")
    list_select_related = ("unit", "unit__grade")


class SampleSentenceInline(admin.TabularInline):
    model = SampleSentence
    extra = 0


@admin.register(GrammarPoint)
class GrammarPointAdmin(admin.ModelAdmin):
    list_display = ("name", "unit")
    list_filter = ("unit__grade",)
    search_fields = ("name", "body")
    inlines = (SampleSentenceInline,)


admin.site.register(VocabularyCategory)
admin.site.site_header = "English Test Generator"
admin.site.site_title = "Test Generator admin"
admin.site.index_title = "Content, item bank and review queue"
