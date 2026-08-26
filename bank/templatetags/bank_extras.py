"""Template helpers for rendering bank items."""

from django import template

from bank.presentation import render_variant

register = template.Library()


@register.filter
def rendered(variant):
    """Yield (position, RenderedQuestion) pairs for a TestVariant."""
    return render_variant(variant)
