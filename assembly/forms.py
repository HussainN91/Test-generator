"""Teacher-facing test builder form (spec 7.2)."""

from __future__ import annotations

from django import forms

from assembly.services import DEFAULT_TYPE_WEIGHTS, MAX_VARIANTS
from bank.models import QuestionType
from content.models import Grade, Unit


class TestBuilderForm(forms.Form):
    grade = forms.ModelChoiceField(
        queryset=Grade.objects.all(),
        empty_label=None,
        widget=forms.Select(attrs={"data-autosubmit": "grade"}),
    )
    units = forms.ModelMultipleChoiceField(
        queryset=Unit.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Select at least one unit."},
    )
    question_count = forms.IntegerField(min_value=1, max_value=60, initial=10)
    variant_count = forms.IntegerField(min_value=1, max_value=MAX_VARIANTS, initial=2)
    customize_mix = forms.BooleanField(required=False, label="Customise the question mix")

    def __init__(self, *args, grade=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Units are grade-scoped; the form is re-rendered when the grade changes.
        if grade is not None:
            self.fields["units"].queryset = (
                Unit.objects.filter(grade=grade).select_related("grade").order_by("number")
            )
            self.fields["grade"].initial = grade

        for question_type in QuestionType:
            self.fields[f"weight_{question_type.value}"] = forms.IntegerField(
                required=False,
                min_value=0,
                max_value=20,
                initial=DEFAULT_TYPE_WEIGHTS.get(question_type, 0),
                label=question_type.label,
            )

    @property
    def weight_fields(self):
        """The per-type weight inputs, for rendering the customise panel."""
        return [self[f"weight_{question_type.value}"] for question_type in QuestionType]

    def cleaned_weights(self) -> dict[str, int] | None:
        """Custom weights when the teacher asked for them, else None (use defaults)."""
        if not self.cleaned_data.get("customize_mix"):
            return None
        weights = {
            question_type.value: self.cleaned_data.get(f"weight_{question_type.value}") or 0
            for question_type in QuestionType
        }
        return weights if sum(weights.values()) > 0 else None
