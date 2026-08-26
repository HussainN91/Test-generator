"""Admin as the item-review queue (spec 6).

The default changelist is filtered to items that still need a human decision,
because that is what an admin opens this page to do.
"""

from django.contrib import admin, messages
from django.utils.html import format_html

from bank.models import Item, QuestionType, ReviewStatus
from bank.presentation import render_question


class NeedsReviewFilter(admin.SimpleListFilter):
    title = "review queue"
    parameter_name = "queue"

    def lookups(self, request, model_admin):
        return [("pending", "Needs a decision"), ("all", "Everything")]

    def queryset(self, request, queryset):
        if self.value() in (None, "pending"):
            return queryset.filter(review_status__in=[ReviewStatus.DRAFT, ReviewStatus.FLAGGED])
        return queryset


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("question_preview", "question_type", "model_answer", "unit", "review_status")
    list_filter = (NeedsReviewFilter, "review_status", "question_type", "unit__grade", "generation_batch")
    search_fields = ("model_answer", "payload", "review_notes")
    list_select_related = ("unit", "unit__grade")
    readonly_fields = ("content_hash", "created_at", "rendered_preview")
    autocomplete_fields = ("unit", "target_vocabulary")
    actions = ("approve_items", "reject_items", "flag_items")
    list_per_page = 50

    fieldsets = (
        (None, {"fields": ("unit", "grammar_point", "target_vocabulary", "question_type")}),
        ("Question", {"fields": ("rendered_preview", "payload", "model_answer", "acceptable_answers")}),
        ("Review", {"fields": ("review_status", "review_notes")}),
        (
            "Validation (offline pipeline)",
            {
                "classes": ("collapse",),
                "fields": ("spacy_validated", "llm_validated", "gap_uniqueness_checked"),
            },
        ),
        ("Provenance", {"classes": ("collapse",), "fields": ("generation_batch", "content_hash", "created_at")}),
    )

    @admin.display(description="Question")
    def question_preview(self, item: Item) -> str:
        question = render_question(item)
        text = question.prompt or question.instruction
        return (text[:90] + "…") if len(text) > 90 else text

    @admin.display(description="Preview")
    def rendered_preview(self, item: Item):
        question = render_question(item)
        parts = [f"<em>{question.instruction}</em>", f"<p>{question.prompt}</p>"]
        if question.options:
            parts.append(
                "<p>" + " &nbsp; ".join(f"{l}. {o}" for l, o in question.lettered_options) + "</p>"
            )
        for row in question.matching_rows:
            parts.append(f"<div>{row['number']}. {row['left']} — {row['letter']}. {row['right']}</div>")
        parts.append(f"<p><strong>Answer:</strong> {question.answer}</p>")
        return format_html("".join(parts))

    def _set_status(self, request, queryset, status, verb):
        updated = queryset.update(review_status=status)
        self.message_user(request, f"{updated} item(s) {verb}.", messages.SUCCESS)

    @admin.action(description="Approve — make available to teachers")
    def approve_items(self, request, queryset):
        self._set_status(request, queryset, ReviewStatus.APPROVED, "approved")

    @admin.action(description="Reject — keep out of every test")
    def reject_items(self, request, queryset):
        self._set_status(request, queryset, ReviewStatus.REJECTED, "rejected")

    @admin.action(description="Flag for another look")
    def flag_items(self, request, queryset):
        self._set_status(request, queryset, ReviewStatus.FLAGGED, "flagged")
