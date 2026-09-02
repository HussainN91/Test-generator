"""Template helpers for the listening bank page."""

import re

from django import template
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

register = template.Library()

#: The transcripts are authored as markdown and imported verbatim, so the
#: only formatting they carry is `**bold**` on each question's heading -
#: "**3. Where does the woman work?**". Those headings are what lets a
#: reviewer find the passage a question is drawn from, which is the whole
#: job of showing the transcript, so they are worth rendering.
#:
#: Deliberately not DOTALL and not multiline: a heading never spans lines,
#: and a stray unmatched `**` should render as itself rather than swallow
#: the rest of the transcript into one bold run.
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


@register.filter(needs_autoescape=True)
def transcript_bold(text, autoescape=True):
    """Render a transcript's `**bold**` headings as real bold.

    Escapes first and substitutes second, so a transcript can never inject
    markup: by the time the pattern is applied, any `<` in the source is
    already `&lt;` and the only tags in the result are the ones added here.

    One pattern rather than a markdown dependency - the files use nothing
    else, and pulling in a parser to handle two asterisks would be more
    machinery than the problem deserves.
    """
    escaped = conditional_escape(text or "") if autoescape else (text or "")
    return mark_safe(BOLD_RE.sub(r"<strong>\1</strong>", escaped))
