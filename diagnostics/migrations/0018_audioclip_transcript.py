"""Give AudioClip somewhere to keep its transcript.

Until now the transcripts lived only in
media/diagnostics/audio/transcripts-full.md, which is gitignored and, for
clips 11-20, the sole copy in existence. Importing them into the database
also puts them inside the server's ordinary backup routine.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("diagnostics", "0017_paper_listening_sets")]

    operations = [
        migrations.AddField(
            model_name="audioclip",
            name="transcript",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "The full spoken text of the recording, imported from "
                    "media/diagnostics/audio/transcripts-full.md. Kept on the "
                    "clip rather than the question set because both sets ask "
                    "about the same audio and are checked against the same words."
                ),
            ),
            preserve_default=False,
        ),
    ]
