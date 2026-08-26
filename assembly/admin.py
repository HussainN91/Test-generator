"""Admin for generated batches — mainly for traceability after export."""

from django.contrib import admin

from assembly.models import TestBatch, TestQuestion, TestVariant


class TestVariantInline(admin.TabularInline):
    model = TestVariant
    extra = 0
    show_change_link = True
    fields = ("label",)


@admin.register(TestBatch)
class TestBatchAdmin(admin.ModelAdmin):
    list_display = ("__str__", "grade", "created_by", "question_count", "variant_count", "created_at")
    list_filter = ("grade", "created_by")
    inlines = (TestVariantInline,)
    filter_horizontal = ("units",)


class TestQuestionInline(admin.TabularInline):
    model = TestQuestion
    extra = 0
    fields = ("position", "item")
    readonly_fields = ("position", "item")


@admin.register(TestVariant)
class TestVariantAdmin(admin.ModelAdmin):
    list_display = ("__str__", "batch")
    inlines = (TestQuestionInline,)
