"""Every real formatting quirk found in the source file gets a test."""

from django.test import TestCase

from diagnostics.extraction.keys import parse_gap_fill_key, parse_letter_key


class LetterKeyTests(TestCase):
    def test_colon_before_the_first_number(self):
        # Clip 1: "**Answers :1** C   **2** B ..."
        blob = "**Answers :1** C   **2** B   **3** A   **4** B   **5** C"
        self.assertEqual(parse_letter_key(blob), ["C", "B", "A", "B", "C"])

    def test_key_on_the_line_after_the_marker(self):
        # Clip 2
        blob = "##### **Answers:**\n\n**1 A   2 C   3 B   4 C   5 B**"
        self.assertEqual(parse_letter_key(blob), ["A", "C", "B", "C", "B"])

    def test_missing_space_between_number_and_letter(self):
        # Clip 20: "3A"
        blob = "### **Answers:1 B  2 B  3A  4 B  5 A**"
        self.assertEqual(parse_letter_key(blob), ["B", "B", "A", "B", "A"])

    def test_uses_the_last_answers_marker_only(self):
        blob = "A stray 1 A in the question text.\n**Answers:1 C 2 C 3 C 4 C 5 C**"
        self.assertEqual(parse_letter_key(blob), ["C", "C", "C", "C", "C"])

    def test_raises_when_five_answers_are_not_found(self):
        with self.assertRaises(ValueError):
            parse_letter_key("**Answers:1 A  2 B**")


class GapFillKeyTests(TestCase):
    def test_simple_numbered_key(self):
        # Clip 3
        blob = r"**Answers : 1.rope   2\. 20/twenty  3\. Tall 4\. band  5\. ice(-)cream**"
        self.assertEqual(
            parse_gap_fill_key(blob),
            ["rope", "20/twenty", "Tall", "band", "ice(-)cream"],
        )

    def test_missing_separator_between_answers(self):
        # Clip 7: "...six/6 months3.(a) receptionist..."
        blob = (r"**Answers: 1.(a) family 2\. six/6 months3.(a) receptionist"
                r"4.(a) bakery / baker's 5\. four**")
        parsed = parse_gap_fill_key(blob)
        self.assertEqual(len(parsed), 5)
        self.assertEqual(parsed[0], "(a) family")
        self.assertEqual(parsed[2], "(a) receptionist")

    def test_answer_that_itself_contains_a_digit(self):
        # Clip 19: answer 4 is "5 / five", which must not be read as marker 5.
        blob = "**Answers:1 hills  2 sunset   3 cushion 4 5 / five   5 CITYENTS**"
        self.assertEqual(
            parse_gap_fill_key(blob),
            ["hills", "sunset", "cushion", "5 / five", "CITYENTS"],
        )

    def test_raises_when_an_answer_is_empty(self):
        with self.assertRaises(ValueError):
            parse_gap_fill_key("**Answers:1 a 2 b 3 4 d 5 e**")


class AlternativesTests(TestCase):
    def test_slash_separated_alternatives_are_split(self):
        from diagnostics.extraction.keys import split_alternatives

        self.assertEqual(split_alternatives("20/twenty"), ["20", "twenty"])
        self.assertEqual(
            split_alternatives("(a) bakery / baker's"), ["(a) bakery", "baker's"]
        )
        self.assertEqual(split_alternatives("hills"), ["hills"])
