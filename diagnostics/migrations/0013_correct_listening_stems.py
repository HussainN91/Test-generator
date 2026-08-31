"""Replay the four stem corrections over rows imported before the importer
learned about them. Idempotent and reversible: each row is matched on the
exact wrong text, so a row already carrying the right text is left alone."""

from django.db import migrations

from diagnostics.constants import STEM_CORRECTIONS


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
