from django.test import TestCase

from diagnostics.authored.schema import ContentError, validate_reading


def reading_payload(**overrides):
    payload = {
        "label": "R01",
        "title": "The School Garden",
        "body": " ".join(["word"] * 165),
        "questions": (
            [{"position": n, "subtype": "true_false_ng", "stem": f"s{n}",
              "options": ["TRUE", "FALSE", "NOT GIVEN"], "answer": "TRUE"}
             for n in range(1, 6)]
            + [{"position": n, "subtype": "mcq", "stem": f"s{n}",
                "options": ["a", "b", "c", "d"], "answer": "B"}
               for n in range(6, 9)]
            + [{"position": n, "subtype": "completion", "stem": f"s{n}",
                "options": [], "answer": "height"}
               for n in range(9, 11)]
        ),
    }
    payload.update(overrides)
    return payload


class ReadingValidationTests(TestCase):
    def test_valid_payload_passes(self):
        validate_reading(reading_payload())

    def test_short_passage_is_rejected(self):
        with self.assertRaisesMessage(ContentError, "150-300 words"):
            validate_reading(reading_payload(body="too short"))

    def test_wrong_question_count_is_rejected(self):
        payload = reading_payload()
        payload["questions"] = payload["questions"][:9]
        with self.assertRaisesMessage(ContentError, "exactly 10"):
            validate_reading(payload)

    def test_any_mix_of_valid_subtypes_is_accepted(self):
        payload = reading_payload()
        payload["questions"][0]["subtype"] = "mcq"
        payload["questions"][0]["options"] = ["a", "b", "c", "d"]
        payload["questions"][0]["answer"] = "A"
        validate_reading(payload)  # must not raise

    def test_heading_matching_and_paragraph_matching_are_accepted(self):
        payload = reading_payload()
        payload["questions"][0]["subtype"] = "heading_matching"
        payload["questions"][0]["options"] = ["i", "ii", "iii", "iv", "v", "vi"]
        payload["questions"][0]["answer"] = "iii"
        payload["questions"][1]["subtype"] = "paragraph_matching"
        payload["questions"][1]["options"] = []
        payload["questions"][1]["answer"] = "C"
        validate_reading(payload)  # must not raise

    def test_still_requires_exactly_ten_questions(self):
        payload = reading_payload()
        payload["questions"] = payload["questions"][:9]
        with self.assertRaisesMessage(ContentError, "exactly 10"):
            validate_reading(payload)

    def test_mcq_answer_must_be_a_listed_option_letter(self):
        payload = reading_payload()
        payload["questions"][5]["answer"] = "E"
        with self.assertRaisesMessage(ContentError, "option letter"):
            validate_reading(payload)

    def test_completion_answer_is_at_most_two_words(self):
        payload = reading_payload()
        payload["questions"][8]["answer"] = "far too many words"
        with self.assertRaisesMessage(ContentError, "two words"):
            validate_reading(payload)

    def test_missing_label_is_rejected(self):
        payload = reading_payload()
        del payload["label"]
        with self.assertRaisesMessage(ContentError, "label"):
            validate_reading(payload)

    def test_unknown_subtype_is_rejected(self):
        payload = reading_payload()
        payload["questions"][0]["subtype"] = "not_a_real_subtype"
        with self.assertRaisesMessage(ContentError, "unknown subtype"):
            validate_reading(payload)

    def test_heading_matching_answer_matches_case_and_whitespace_insensitively(self):
        payload = reading_payload()
        payload["questions"][0]["subtype"] = "heading_matching"
        payload["questions"][0]["options"] = ["i", "ii", "iii", "iv", "v", "vi"]
        payload["questions"][0]["answer"] = "  III  "  # different case, extra whitespace
        validate_reading(payload)  # must not raise
