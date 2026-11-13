"""Unit tests for filename-safe naming and unique PDF folder selection."""
import json
import tempfile
import unittest
from pathlib import Path

from app.services import batch_pdf_to_images as batch
from app.services.storage_layout import safe_name, unique_folder


class SafeNameTests(unittest.TestCase):
    def test_replaces_illegal_characters_and_collapses_whitespace(self):
        self.assertEqual(safe_name('A<B>:"C"/D\\E|F?G*  H'), "A B C D E F G H")

    def test_strips_edge_dots_and_spaces(self):
        self.assertEqual(safe_name("  name.. "), "name")

    def test_empty_becomes_unknown(self):
        self.assertEqual(safe_name(""), "Unknown")
        self.assertEqual(safe_name(" . "), "Unknown")

    def test_batch_and_layout_agree(self):
        for value in ["BOL 001", 'a:b', "x  y", "", "..."]:
            self.assertEqual(batch.safe_name(value), safe_name(value))


class UniqueFolderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_free_name_returned_unchanged(self):
        self.assertEqual(unique_folder(self.root, "Load"), self.root / "Load")

    def test_same_hash_reuses_existing_folder(self):
        (self.root / "Load").mkdir()
        (self.root / "Load" / "ocr-results.json").write_text(json.dumps({"source_sha256": "h1"}))
        self.assertEqual(unique_folder(self.root, "Load", "h1"), self.root / "Load")

    def test_different_hash_gets_suffix(self):
        (self.root / "Load").mkdir()
        (self.root / "Load" / "ocr-results.json").write_text(json.dumps({"source_sha256": "h1"}))
        self.assertEqual(unique_folder(self.root, "Load", "h2" * 8), self.root / "Load [h2h2h2h2h2h2] 2")

    def test_collision_counter_increments(self):
        (self.root / "Load").mkdir()
        (self.root / "Load 2").mkdir()
        self.assertEqual(unique_folder(self.root, "Load"), self.root / "Load 3")

    def test_corrupt_manifest_does_not_crash(self):
        (self.root / "Load").mkdir()
        (self.root / "Load" / "ocr-results.json").write_text("{not json")
        self.assertEqual(unique_folder(self.root, "Load", "h1"), self.root / "Load [h1] 2")


class BatchHelperTests(unittest.TestCase):
    def test_pdf_sha256_and_processing_key(self):
        with tempfile.TemporaryDirectory() as temp:
            pdf = Path(temp) / "a b.pdf"
            pdf.write_bytes(b"hello")
            digest = batch.pdf_sha256(pdf)
            self.assertEqual(digest, "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824")
            self.assertEqual(batch.processing_key(pdf, digest), f"a b [{digest[:12]}]")

    def test_generated_gallery_pdfs_are_not_processable_but_uploads_are(self):
        generated = batch.OUTPUT_ROOT / "PDFs" / "x" / "x.pdf"
        upload = batch.UPLOAD_ROOT / "2026" / "x.pdf"
        self.assertFalse(batch.is_processable_source_pdf(generated))
        self.assertTrue(batch.is_processable_source_pdf(upload))
        self.assertTrue(batch.is_processable_source_pdf(Path(tempfile.gettempdir()) / "x.pdf"))


if __name__ == "__main__":
    unittest.main()
