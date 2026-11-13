"""End-to-end PDF -> JPG + OCR manifest + searchable PDF, with OCR stubbed."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf as fitz  # PyMuPDF 1.28+ has no 'fitz' module

from app.services import batch_pdf_to_images as batch
from app.services import ocr, storage_layout

# RapidOCR line format used by build_searchable_pdf: (x0, y0, x1, y1, text)
FAKE_LINES = [[10, 10, 300, 40, "BOL SCANNED TEXT"]]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.out = base / "BOL images"
        self.out.mkdir()
        self.src = base / "incoming"
        self.src.mkdir()
        self.pdf = self.src / "Load A.pdf"
        document = fitz.open()
        for _ in range(2):
            document.new_page(width=300, height=200)  # blank: forces the OCR path
        document.save(self.pdf)
        document.close()
        self.original = self.pdf.read_bytes()
        patches = [
            patch.object(batch, "OUTPUT_ROOT", self.out),
            patch.object(batch, "UPLOAD_ROOT", self.out / "_AppData" / "uploads"),
            patch.object(batch, "PDFS", self.out / "PDFs"),
            patch.object(batch, "IMAGES", self.out / "Images"),
            patch.object(storage_layout, "ROOT", self.out),
            patch.object(storage_layout, "PDFS", self.out / "PDFs"),
            patch.object(ocr, "extract_rapidocr_lines", lambda image: FAKE_LINES),
            patch("app.services.integrity.record_manifest"),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        (self.out / "PDFs").mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def run_pipeline(self):
        batch.process_pdf(self.pdf, "rapidocr", "", 72)
        return self.out / "PDFs" / "Load A"

    def test_outputs_match_layout(self):
        folder = self.run_pipeline()
        self.assertEqual(self.pdf.read_bytes(), self.original)  # source untouched
        self.assertEqual((folder / "Load A.pdf").read_bytes(), self.original)
        self.assertTrue((folder / "Load A Searchable.pdf").is_file())
        self.assertTrue((folder / "Images" / "Trash").is_dir())
        self.assertEqual(sorted(p.name for p in (folder / "Images").glob("*.jpg")),
                         ["001 Load A.jpg", "002 Load A.jpg"])
        self.assertFalse((self.out / "_Processing" / f"Load A [{batch.pdf_sha256(self.pdf)[:12]}]").exists())

    def test_manifest_contents(self):
        folder = self.run_pipeline()
        manifest = json.loads((folder / "ocr-results.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["source_pdf"], "Load A.pdf")
        self.assertEqual(manifest["source_sha256"], batch.pdf_sha256(self.pdf))
        self.assertEqual(manifest["ocr_provider"], "rapidocr")
        self.assertEqual(manifest["searchable_pdf"], "Load A Searchable.pdf")
        self.assertEqual([p["page"] for p in manifest["pages"]], [1, 2])
        for page in manifest["pages"]:
            self.assertEqual(page["raw_ocr"], "BOL SCANNED TEXT")
            self.assertEqual(page["searchable_text"], "BOL SCANNED TEXT")
            self.assertTrue((folder / "Images" / page["image"]).is_file())

    def test_searchable_pdf_has_text_layer_and_original_does_not(self):
        folder = self.run_pipeline()
        with fitz.open(folder / "Load A Searchable.pdf") as searchable:
            self.assertEqual(len(searchable), 2)
            self.assertIn("BOL SCANNED TEXT", searchable[0].get_text())
        with fitz.open(folder / "Load A.pdf") as original:
            self.assertEqual(original[0].get_text().strip(), "")

    def test_reprocessing_same_pdf_reuses_folder(self):
        self.run_pipeline()
        self.run_pipeline()
        self.assertEqual([p.name for p in (self.out / "PDFs").iterdir()], ["Load A"])

    def test_born_digital_page_skips_ocr(self):
        pdf = self.src / "Digital.pdf"
        document = fitz.open()
        document.new_page(width=400, height=200).insert_text((20, 50), "Real embedded text for the carrier shipment")
        document.save(pdf)
        document.close()
        with patch.object(ocr, "extract_rapidocr_lines", side_effect=AssertionError("OCR must be skipped")):
            batch.process_pdf(pdf, "rapidocr", "", 72)
        manifest = json.loads((self.out / "PDFs" / "Digital" / "ocr-results.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["pages"][0]["raw_ocr"], "")
        self.assertIn("Real embedded text", manifest["pages"][0]["searchable_text"])


if __name__ == "__main__":
    unittest.main()
