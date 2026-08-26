"""The importer must guess what a column means without being told.

These are the header spellings actually seen in the wild for this kind of
sheet. The proposal is always shown for confirmation before anything is
written (spec §4.2), so a wrong guess is cheap; a missing guess is not.
"""

from django.test import SimpleTestCase

from step.roster import mapping


class NormaliseTests(SimpleTestCase):
    def test_case_punctuation_and_spacing_are_ignored(self):
        self.assertEqual(mapping.normalise("  Full  Name! "), "fullname")
        self.assertEqual(mapping.normalise("E-mail"), "email")
        self.assertEqual(mapping.normalise("PINFL / ПИНФЛ"), "pinflпинфл")


class ProposeMappingTests(SimpleTestCase):
    def test_recognises_common_name_headers(self):
        for header in ["Full Name", "Teacher Name", "Name", "FULL NAME"]:
            proposed = mapping.propose_mapping([header])
            self.assertEqual(proposed[header], "full_name", f"failed on {header!r}")

    def test_recognises_email_headers(self):
        for header in ["Email", "E-mail", "Email Address", "Gmail"]:
            self.assertEqual(mapping.propose_mapping([header])[header], "email")

    def test_recognises_region_headers(self):
        for header in ["Region", "Viloyat", "Province", "Oblast"]:
            self.assertEqual(mapping.propose_mapping([header])[header], "region")

    def test_recognises_district_school_passport_and_pinfl(self):
        proposed = mapping.propose_mapping(["District", "School", "Passport Number", "PINFL"])
        self.assertEqual(proposed["District"], "district")
        self.assertEqual(proposed["School"], "school")
        self.assertEqual(proposed["Passport Number"], "passport_no")
        self.assertEqual(proposed["PINFL"], "pinfl")

    def test_unknown_headers_map_to_none(self):
        proposed = mapping.propose_mapping(["Contract Type", "Intake Cohort"])
        self.assertIsNone(proposed["Contract Type"])
        self.assertIsNone(proposed["Intake Cohort"])

    def test_a_header_is_never_mapped_to_two_fields(self):
        proposed = mapping.propose_mapping(["Name", "Full Name"])
        mapped = [v for v in proposed.values() if v is not None]
        self.assertEqual(len(mapped), len(set(mapped)), f"duplicate targets in {proposed}")

    def test_blank_headers_are_ignored(self):
        proposed = mapping.propose_mapping(["Name", "", None, "  "])
        self.assertEqual(list(proposed), ["Name"])


class SufficiencyTests(SimpleTestCase):
    def test_a_mapping_with_an_identity_key_and_a_region_is_sufficient(self):
        ok, missing = mapping.check_sufficiency({"Email": "email", "Region": "region"})
        self.assertTrue(ok)
        self.assertEqual(missing, [])

    def test_a_mapping_with_no_geographic_anchor_is_insufficient(self):
        ok, missing = mapping.check_sufficiency({"Email": "email"})
        self.assertFalse(ok)
        self.assertIn("a geographic anchor (region, district or school)", missing)

    def test_a_mapping_with_no_identity_key_is_insufficient(self):
        ok, missing = mapping.check_sufficiency({"Region": "region"})
        self.assertFalse(ok)
        self.assertIn("an identity key (email, passport_no or pinfl)", missing)

    def test_district_alone_satisfies_the_geographic_anchor(self):
        ok, _ = mapping.check_sufficiency({"PINFL": "pinfl", "District": "district"})
        self.assertTrue(ok)
