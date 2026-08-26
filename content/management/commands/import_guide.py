"""Import the grade 9/10/11 study guides into the content layer.

Idempotent: re-running replaces a grade's parsed content in a single
transaction, so fixing the source .txt and re-importing is safe.

    python manage.py import_guide                 # all grades found in the dir
    python manage.py import_guide --grade 9
    python manage.py import_guide --file path/to/guide.txt --grade 11
    python manage.py import_guide --dry-run
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from content.models import (
    Grade,
    GrammarPoint,
    SampleSentence,
    Unit,
    VocabularyCategory,
    VocabularyEntry,
)
from content.parsing.guide_parser import ParsedUnit, parse_guide

GUIDE_FILENAME = "grade-{grade}-vocabulary-and-grammar-guide.txt"
RE_GUIDE_FILENAME = re.compile(r"grade-(\d+)-vocabulary-and-grammar-guide\.txt$", re.IGNORECASE)


def normalise_lemma(word: str) -> str:
    """Lowercase, strip punctuation and placeholder tokens used in the guides."""
    lemma = word.lower().strip()
    lemma = re.sub(r"\b(sth|sb|someone|something)\b", "", lemma)
    lemma = re.sub(r"[^\w\s'-]", " ", lemma)
    return re.sub(r"\s+", " ", lemma).strip()


class Command(BaseCommand):
    help = "Parse the vocabulary/grammar guides and load them into the database."

    def add_arguments(self, parser):
        parser.add_argument("--grade", type=int, action="append", dest="grades")
        parser.add_argument("--file", type=str, help="Explicit path (requires --grade).")
        parser.add_argument("--dir", type=str, help="Directory to scan for guide files.")
        parser.add_argument("--dry-run", action="store_true", help="Parse and report; write nothing.")

    def handle(self, *args, **options):
        targets = self._resolve_targets(options)
        if not targets:
            raise CommandError("No guide files found. Pass --dir or --file.")

        totals = {"units": 0, "entries": 0, "grammar": 0, "samples": 0}
        for grade_number, path in targets:
            counts = self._import_one(grade_number, path, dry_run=options["dry_run"])
            for key in totals:
                totals[key] += counts[key]

        verb = "Would import" if options["dry_run"] else "Imported"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {totals['units']} units, {totals['entries']} vocabulary entries, "
                f"{totals['grammar']} grammar points, {totals['samples']} sample sentences."
            )
        )

    # -- target resolution ---------------------------------------------------

    def _resolve_targets(self, options) -> list[tuple[int, Path]]:
        if options["file"]:
            if not options["grades"] or len(options["grades"]) != 1:
                raise CommandError("--file requires exactly one --grade.")
            path = Path(options["file"])
            if not path.exists():
                raise CommandError(f"No such file: {path}")
            return [(options["grades"][0], path)]

        directory = Path(options["dir"]) if options["dir"] else Path(settings.GUIDE_SOURCE_DIR)
        if not directory.is_dir():
            raise CommandError(f"Not a directory: {directory}")

        wanted = set(options["grades"] or [])
        found: list[tuple[int, Path]] = []
        for candidate in sorted(directory.glob("*.txt")):
            match = RE_GUIDE_FILENAME.search(candidate.name)
            if not match:
                continue
            number = int(match.group(1))
            if wanted and number not in wanted:
                continue
            found.append((number, candidate))
        return found

    # -- import --------------------------------------------------------------

    def _import_one(self, grade_number: int, path: Path, *, dry_run: bool) -> dict[str, int]:
        text = path.read_text(encoding="utf-8")
        units = parse_guide(text)
        if not units:
            self.stdout.write(self.style.WARNING(f"Grade {grade_number}: no units found in {path.name}"))
            return {"units": 0, "entries": 0, "grammar": 0, "samples": 0}

        counts = {
            "units": len(units),
            "entries": sum(len(u.entries) for u in units),
            "grammar": sum(1 for u in units if u.grammar),
            "samples": sum(len(u.grammar.sample_sentences) for u in units if u.grammar),
        }

        self.stdout.write(
            f"Grade {grade_number} ({path.name}): {counts['units']} units, "
            f"{counts['entries']} entries, {counts['grammar']} grammar points."
        )
        for unit in units:
            if not unit.entries:
                self.stdout.write(
                    self.style.WARNING(f"  Unit {unit.number}: no vocabulary parsed (grammar-only?)")
                )
            if not unit.grammar:
                self.stdout.write(self.style.WARNING(f"  Unit {unit.number}: no grammar point parsed"))

        if dry_run:
            return counts

        with transaction.atomic():
            grade, _ = Grade.objects.update_or_create(
                number=grade_number, defaults={"source_file": path.name}
            )
            # Replace wholesale: the guide file is the source of truth. Items in
            # the bank reference units, so units themselves are preserved by
            # number and only their content is rebuilt.
            for parsed in units:
                self._write_unit(grade, parsed)

        return counts

    def _write_unit(self, grade: Grade, parsed: ParsedUnit) -> None:
        unit, _ = Unit.objects.update_or_create(
            grade=grade,
            number=parsed.number,
            defaults={"title": parsed.title[:255], "theme": parsed.theme[:255]},
        )

        unit.categories.all().delete()
        unit.vocabulary.all().delete()

        categories: dict[str, VocabularyCategory] = {}
        for parsed_category in parsed.categories:
            categories[parsed_category.name] = VocabularyCategory.objects.create(
                unit=unit, name=parsed_category.name[:255], order=parsed_category.order
            )

        entries = []
        for parsed_entry in parsed.entries:
            entries.append(
                VocabularyEntry(
                    unit=unit,
                    category=categories.get(parsed_entry.category),
                    word=parsed_entry.word[:120],
                    lemma=normalise_lemma(parsed_entry.word)[:120],
                    part_of_speech=parsed_entry.part_of_speech,
                    definition=parsed_entry.definition,
                    sense_note=parsed_entry.sense_note[:255],
                    word_family=parsed_entry.word_family[:120],
                )
            )
        VocabularyEntry.objects.bulk_create(entries)

        if parsed.grammar:
            grammar, _ = GrammarPoint.objects.update_or_create(
                unit=unit,
                defaults={
                    "name": parsed.grammar.name[:255],
                    "slug": slugify(parsed.grammar.name)[:255],
                    "body": parsed.grammar.body,
                },
            )
            grammar.sample_sentences.all().delete()
            SampleSentence.objects.bulk_create(
                [SampleSentence(grammar_point=grammar, text=text) for text in parsed.grammar.sample_sentences]
            )
