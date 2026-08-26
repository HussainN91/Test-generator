"""Content layer (spec 3.1): the syllabus source of truth.

Grade -> Unit -> (VocabularyEntry*, GrammarPoint) is populated by the
`import_guide` management command from the Prepare-based study guides.
Nothing here is generated; it is transcribed syllabus data.
"""

from django.db import models


class PartOfSpeech(models.TextChoices):
    NOUN = "noun", "Noun"
    VERB = "verb", "Verb"
    ADJECTIVE = "adjective", "Adjective"
    ADVERB = "adverb", "Adverb"
    PREPOSITION = "preposition", "Preposition"
    CONJUNCTION = "conjunction", "Conjunction"
    DETERMINER = "determiner", "Determiner"
    PRONOUN = "pronoun", "Pronoun"
    PHRASAL_VERB = "phrasal_verb", "Phrasal verb"
    PHRASE = "phrase", "Phrase"
    VERB_PHRASE = "verb_phrase", "Verb phrase"
    OTHER = "other", "Other"


class CEFRLevel(models.TextChoices):
    A1 = "A1", "A1"
    A2 = "A2", "A2"
    B1 = "B1", "B1"
    B2 = "B2", "B2"
    C1 = "C1", "C1"
    C2 = "C2", "C2"


class Grade(models.Model):
    """A school grade (9, 10, 11), each backed by one source guide."""

    number = models.PositiveSmallIntegerField(unique=True)
    source_file = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return f"Grade {self.number}"


class Unit(models.Model):
    """One unit of a grade's syllabus: a vocabulary set plus a grammar focus."""

    grade = models.ForeignKey(Grade, on_delete=models.CASCADE, related_name="units")
    number = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=255, blank=True)
    theme = models.CharField(
        max_length=255,
        blank=True,
        help_text="Thematic tag used to keep generated items coherent within a unit.",
    )

    class Meta:
        ordering = ["grade__number", "number"]
        constraints = [
            models.UniqueConstraint(fields=["grade", "number"], name="unique_unit_per_grade"),
        ]

    def __str__(self):
        return f"G{self.grade.number} Unit {self.number}: {self.title or self.theme or ''}".strip()


class VocabularyCategory(models.Model):
    """A named vocabulary grouping inside a unit ("Describing People", "Phrasal Verbs")."""

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=255)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["unit", "order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["unit", "name"], name="unique_category_per_unit"),
        ]
        verbose_name_plural = "vocabulary categories"

    def __str__(self):
        return f"{self.unit} / {self.name}"


class VocabularyEntry(models.Model):
    """A single vocabulary item as taught in a unit.

    `word` is stored exactly as written in the guide (including multi-word
    entries such as "send sth back"); `lemma` holds a normalised lookup form.
    """

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="vocabulary")
    category = models.ForeignKey(
        VocabularyCategory,
        on_delete=models.CASCADE,
        related_name="entries",
        null=True,
        blank=True,
    )
    word = models.CharField(max_length=120)
    lemma = models.CharField(max_length=120, db_index=True)
    part_of_speech = models.CharField(
        max_length=20, choices=PartOfSpeech.choices, default=PartOfSpeech.OTHER
    )
    definition = models.TextField(blank=True)
    sense_note = models.CharField(
        max_length=255,
        blank=True,
        help_text='Disambiguating gloss from the guide, e.g. "= transport" for "change".',
    )
    cefr_level = models.CharField(
        max_length=2,
        choices=CEFRLevel.choices,
        blank=True,
        help_text="Cross-referenced against the Cambridge English Vocabulary Profile (populated separately).",
    )
    word_family = models.CharField(
        max_length=120,
        blank=True,
        db_index=True,
        help_text="Shared key for related forms (achieve/achievement), used by word-formation items.",
    )

    class Meta:
        ordering = ["unit", "word", "part_of_speech"]
        constraints = [
            models.UniqueConstraint(
                fields=["unit", "word", "part_of_speech", "sense_note"],
                name="unique_entry_per_unit_sense",
            ),
        ]
        verbose_name_plural = "vocabulary entries"

    def __str__(self):
        return f"{self.word} ({self.get_part_of_speech_display()})"


class GrammarPoint(models.Model):
    """The grammar focus of a unit, with the guide's explanatory body kept verbatim.

    `body` is the raw guide text: it is the few-shot reference material handed
    to the offline generation pipeline (spec 3.2), never shown to students.
    """

    unit = models.OneToOneField(Unit, on_delete=models.CASCADE, related_name="grammar_point")
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, db_index=True)
    body = models.TextField(blank=True)

    class Meta:
        ordering = ["unit"]

    def __str__(self):
        return f"{self.unit} — {self.name}"


class SampleSentence(models.Model):
    """An example sentence lifted from the guide.

    Used *only* as a structural pattern reference during generation (spec 3.1);
    it must never be reused verbatim in a generated item.
    """

    grammar_point = models.ForeignKey(
        GrammarPoint, on_delete=models.CASCADE, related_name="sample_sentences"
    )
    text = models.TextField()

    class Meta:
        ordering = ["grammar_point", "id"]

    def __str__(self):
        return self.text[:80]
