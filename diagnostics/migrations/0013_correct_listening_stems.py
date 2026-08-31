"""Replay the four listening stem corrections over rows imported before the
importer learned about them. Idempotent and reversible: each row is matched
on the exact wrong text, so a row already carrying the right text is left
alone.

The wrong/right pairs are hardcoded here rather than imported from
diagnostics.constants or diagnostics.extraction.listening_content: a
migration is a frozen historical record and must stay self-contained and
reproducible regardless of later edits to application code."""

from django.db import migrations

#: Keyed by (clip number, question position); see
#: diagnostics.extraction.listening_content.STEM_CORRECTIONS for the live
#: version of this same data, applied going forward by the importer.
STEM_CORRECTIONS = {
    (1, 4): (
        "What will the girl take with her on holiday?",
        "What will the boy take with him on holiday?",
    ),
    (5, 4): (
        "Which pictures shows what happened?",
        "Which picture shows what happened?",
    ),
    (6, 5): (
        "What does the festival programme offer at lckworth?",
        "What does the festival programme offer at Ickworth?",
    ),
    (13, 3): (
        "Why will drives have problems this morning?",
        "Why will drivers have problems this morning?",
    ),
}


def _swap(apps, forwards):
    ListeningQuestion = apps.get_model("diagnostics", "ListeningQuestion")
    for (number, position), (wrong, right) in STEM_CORRECTIONS.items():
        source, target = (wrong, right) if forwards else (right, wrong)
        ListeningQuestion.objects.filter(
            clip__number=number, position=position, stem=source
        ).update(stem=target)


def apply_corrections(apps, schema_editor):
    _swap(apps, forwards=True)


def undo_corrections(apps, schema_editor):
    _swap(apps, forwards=False)


class Migration(migrations.Migration):

    dependencies = [("diagnostics", "0012_alter_generationevent_export_format")]

    operations = [
        migrations.RunPython(apply_corrections, undo_corrections),
    ]
