"""Geography is reference data, not user data.

The seed command must be idempotent because it runs on every deployment, and
the fixture must carry all 14 top-level divisions even though the client's
mockup only shows the 11 that currently have teachers (spec §4.1).
"""

from io import StringIO

from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase

from step.models import District, Region


class RegionTests(TestCase):
    def test_region_code_is_unique(self):
        Region.objects.create(name="Samarkand", code="samarkand")
        with self.assertRaises(IntegrityError):
            Region.objects.create(name="Samarqand", code="samarkand")

    def test_str_is_the_name(self):
        region = Region.objects.create(name="Bukhara", code="bukhara")
        self.assertEqual(str(region), "Bukhara")


class DistrictTests(TestCase):
    def test_district_code_is_unique_within_a_region_only(self):
        a = Region.objects.create(name="Fergana", code="fergana")
        b = Region.objects.create(name="Andijan", code="andijan")
        District.objects.create(region=a, name="Centre", code="centre")
        # Same code under a different region is fine.
        District.objects.create(region=b, name="Centre", code="centre")
        with self.assertRaises(IntegrityError):
            District.objects.create(region=a, name="Centre again", code="centre")

    def test_str_includes_the_region(self):
        region = Region.objects.create(name="Jizzakh", code="jizzakh")
        district = District.objects.create(region=region, name="Zomin", code="zomin")
        self.assertEqual(str(district), "Zomin, Jizzakh")


class SeedGeographyTests(TestCase):
    def test_seeds_all_fourteen_top_level_divisions(self):
        call_command("seed_geography", stdout=StringIO())
        self.assertEqual(Region.objects.count(), 14)

    def test_tashkent_city_is_flagged_as_a_city(self):
        call_command("seed_geography", stdout=StringIO())
        self.assertTrue(Region.objects.get(code="tashkent-city").is_city)

    def test_tashkent_city_and_tashkent_region_are_separate(self):
        call_command("seed_geography", stdout=StringIO())
        self.assertTrue(Region.objects.filter(code="tashkent-city").exists())
        self.assertTrue(Region.objects.filter(code="tashkent-region").exists())

    def test_running_twice_does_not_duplicate(self):
        call_command("seed_geography", stdout=StringIO())
        call_command("seed_geography", stdout=StringIO())
        self.assertEqual(Region.objects.count(), 14)

    def test_every_region_has_at_least_one_district(self):
        call_command("seed_geography", stdout=StringIO())
        without = [r.name for r in Region.objects.all() if not r.districts.exists()]
        self.assertEqual(without, [], f"regions with no districts: {without}")
