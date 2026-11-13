"""Shared disposable gallery tree for unit and integration tests."""
import gc
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import gallery, storage_layout


class GalleryTestCase(unittest.TestCase):
    """Points every module that caches gallery paths at a temp directory."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.temp.name) / "BOL images"
        self.root.mkdir()
        self.pdfs = self.root / "PDFs"
        self.patches = [
            patch.object(gallery, "GALLERY_DIR", self.root),
            patch.object(gallery, "PDFS", self.pdfs),
            patch.object(gallery, "_last_migration", 0.0),
            patch.object(storage_layout, "ROOT", self.root),
            patch.object(storage_layout, "PDFS", self.pdfs),
            patch.object(storage_layout, "IMAGES", self.root / "Images"),
            patch.object(storage_layout, "SPREADSHEETS", self.root / "Spreadsheets"),
        ]
        for item in self.patches:
            item.start()
        self.pdfs.mkdir()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        # The app's `with sqlite3.connect()` blocks never close the handle, which
        # blocks deleting jobs.db on Windows until the connection is collected.
        gc.collect()
        self.temp.cleanup()

    def make_pdf_folder(self, name="Load 1", pages=("alpha text", "Beta TEXT"), source_sha256="abc123"):
        """Create PDFs/<name>/ with Images/, a manifest, and page JPG stubs."""
        folder = self.pdfs / name
        images = folder / "Images"
        (images / "Trash").mkdir(parents=True)
        (folder / f"{name}.pdf").write_bytes(b"%PDF-1.4 stub")
        (folder / f"{name} Searchable.pdf").write_bytes(b"%PDF-1.4 searchable")
        entries = []
        for number, text in enumerate(pages, start=1):
            image_name = f"{number:03d} {name}.jpg"
            (images / image_name).write_bytes(b"\xff\xd8jpg")
            entries.append({"page": number, "image": image_name, "raw_ocr": text,
                            "pdf_text": "", "searchable_text": text})
        manifest = {
            "source_pdf": f"{name}.pdf",
            "source_sha256": source_sha256,
            "images_folder": images.relative_to(self.root).as_posix(),
            "processed_at": "2026-01-02T03:04:05+00:00",
            "searchable_pdf": f"{name} Searchable.pdf",
            "pages": entries,
        }
        (folder / "ocr-results.json").write_text(json.dumps(manifest), encoding="utf-8")
        return folder
