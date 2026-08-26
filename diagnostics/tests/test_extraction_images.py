from django.conf import settings
from django.test import TestCase

from diagnostics.extraction.docx_images import extract_images_in_document_order

LISTENING_DOCX = settings.DIAGNOSTICS_SOURCE_DIR / "Listening Question Bank -2026 EC.docx"


class ImageExtractionTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not LISTENING_DOCX.exists():
            raise AssertionError(
                f"Source file missing: {LISTENING_DOCX}. Set DIAGNOSTICS_SOURCE_DIR."
            )
        cls.images = extract_images_in_document_order(LISTENING_DOCX)

    def test_extracts_twenty_five_images(self):
        self.assertEqual(len(self.images), 25)

    def test_images_are_jpeg_bytes(self):
        for name, data in self.images:
            self.assertTrue(data.startswith(b"\xff\xd8"), f"{name} is not a JPEG")

    def test_document_order_differs_from_filename_order(self):
        names = [name for name, _ in self.images]
        self.assertEqual(names[0], "media/image6.jpg")
        self.assertNotEqual(names, sorted(names))

    def test_every_image_is_distinct(self):
        self.assertEqual(len({name for name, _ in self.images}), 25)
