"""Unit tests for gallery cards, trash/restore, download and delete."""
import json

from pathlib import Path

from fastapi import HTTPException

from app.services import gallery
from gallery_fixture import GalleryTestCase


class GalleryCardTests(GalleryTestCase):
    def test_active_cards_have_expected_fields(self):
        self.make_pdf_folder()
        cards = gallery.gallery_cards()
        self.assertEqual(len(cards), 2)
        card = sorted(cards, key=lambda c: c["page"])[0]
        self.assertEqual(card["name"], "001 Load 1.jpg")
        self.assertEqual(card["pdf"], "Load 1.pdf")
        self.assertEqual(card["date"], "2026-01-02")
        self.assertFalse(card["trash"])
        self.assertEqual(card["image"], "PDFs/Load 1/Images/001 Load 1.jpg")
        self.assertEqual(card["searchable_pdf"], "PDFs/Load 1/Load 1 Searchable.pdf")
        self.assertEqual(card["pdf_folder"], "PDFs/Load 1")

    def test_query_is_case_insensitive_over_ocr_text_and_details(self):
        self.make_pdf_folder()
        self.assertEqual([c["page"] for c in gallery.gallery_cards(query="BETA")], [2])
        self.assertEqual(len(gallery.gallery_cards(query="load 1.pdf")), 2)
        self.assertEqual(gallery.gallery_cards(query="nothing-here"), [])

    def test_trash_view_separates_cards(self):
        folder = self.make_pdf_folder()
        image = folder / "Images" / "001 Load 1.jpg"
        image.rename(folder / "Images" / "Trash" / image.name)
        self.assertEqual([c["page"] for c in gallery.gallery_cards()], [2])
        trashed = gallery.gallery_cards(trash=True)
        self.assertEqual([c["page"] for c in trashed], [1])
        self.assertTrue(trashed[0]["trash"])

    def test_missing_jpg_and_corrupt_manifest_are_skipped(self):
        folder = self.make_pdf_folder()
        (folder / "Images" / "002 Load 1.jpg").unlink()
        broken = self.pdfs / "Broken"
        broken.mkdir()
        (broken / "ocr-results.json").write_text("{bad")
        self.assertEqual([c["page"] for c in gallery.gallery_cards()], [1])

    def test_text_truncated_without_include_text_unless_searching(self):
        self.make_pdf_folder(pages=("x" * 2000,))
        self.assertEqual(len(gallery.gallery_cards(include_text=False)[0]["text"]), 600)
        self.assertEqual(len(gallery.gallery_cards(include_text=True)[0]["text"]), 2000)
        self.assertEqual(len(gallery.gallery_cards(query="xxx", include_text=False)[0]["text"]), 2000)

    def test_searchable_pdf_fallback_when_manifest_name_is_wrong(self):
        folder = self.make_pdf_folder()
        manifest_path = folder / "ocr-results.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["searchable_pdf"] = "missing.pdf"
        manifest_path.write_text(json.dumps(manifest))
        self.assertEqual(gallery.gallery_cards()[0]["searchable_pdf"], "PDFs/Load 1/Load 1 Searchable.pdf")


class TrashRestoreTests(GalleryTestCase):
    def setUp(self):
        super().setUp()
        self.folder = self.make_pdf_folder()
        self.rel = "PDFs/Load 1/Images/001 Load 1.jpg"
        self.trash_rel = "PDFs/Load 1/Images/Trash/001 Load 1.jpg"

    def test_trash_then_restore_moves_file_without_deleting(self):
        self.assertEqual(gallery.move_to_trash(self.rel), {"status": "moved to trash"})
        self.assertFalse((self.root / self.rel).exists())
        self.assertEqual((self.root / self.trash_rel).read_bytes(), b"\xff\xd8jpg")
        self.assertEqual(gallery.move_to_trash(self.trash_rel), {"status": "already in trash"})
        self.assertEqual(gallery.restore_from_trash(self.trash_rel), {"status": "restored"})
        self.assertTrue((self.root / self.rel).is_file())
        self.assertFalse((self.root / self.trash_rel).exists())
        self.assertEqual(gallery.restore_from_trash(self.rel), {"status": "already restored"})

    def test_trash_conflict_returns_409_and_keeps_both_files(self):
        (self.root / self.trash_rel).write_bytes(b"old")
        with self.assertRaises(HTTPException) as caught:
            gallery.move_to_trash(self.rel)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertTrue((self.root / self.rel).is_file())
        self.assertEqual((self.root / self.trash_rel).read_bytes(), b"old")

    def test_restore_conflict_returns_409(self):
        (self.root / self.trash_rel).write_bytes(b"trashed")
        with self.assertRaises(HTTPException) as caught:
            gallery.restore_from_trash(self.trash_rel)
        self.assertEqual(caught.exception.status_code, 409)


class PathSafetyTests(GalleryTestCase):
    def setUp(self):
        super().setUp()
        self.make_pdf_folder()
        (self.root.parent / "secret.jpg").write_bytes(b"secret")

    def test_local_image_rejects_traversal_and_non_images(self):
        for bad in ["../secret.jpg", "PDFs/Load 1/Load 1.pdf", "PDFs/Load 1/Images/nope.jpg", "PDFs"]:
            with self.assertRaises(HTTPException) as caught:
                gallery.local_image(bad)
            self.assertEqual(caught.exception.status_code, 404, bad)

    def test_download_is_attachment_for_jpg_and_pdf(self):
        jpg = gallery.download_response("PDFs/Load 1/Images/001 Load 1.jpg")
        self.assertTrue(jpg.headers["content-disposition"].startswith("attachment;"))
        self.assertEqual(jpg.media_type, "image/jpeg")
        pdf = gallery.download_response("PDFs/Load 1/Load 1 Searchable.pdf")
        self.assertEqual(pdf.media_type, "application/pdf")
        self.assertIn("Load%201", pdf.headers["content-disposition"])

    def test_download_rejects_traversal_and_other_types(self):
        for bad in ["../secret.jpg", "PDFs/Load 1/ocr-results.json"]:
            with self.assertRaises(HTTPException):
                gallery.download_response(bad)


class DeletePdfTests(GalleryTestCase):
    def test_rejects_outside_pdfs_and_non_output_folders(self):
        (self.root / "Elsewhere").mkdir()
        (self.pdfs / "Plain").mkdir()
        for bad in ["Elsewhere", "PDFs/Plain", "PDFs/missing", "../"]:
            with self.assertRaises(HTTPException) as caught:
                gallery.delete_pdf_output(bad)
            self.assertEqual(caught.exception.status_code, 404, bad)
        self.assertTrue((self.root / "Elsewhere").is_dir())

    def test_deletes_only_selected_folder(self):
        from unittest.mock import patch
        keep = self.make_pdf_folder("Keep", source_sha256="k")
        gone = self.make_pdf_folder("Gone", source_sha256="g")
        with patch("app.services.integrity.delete_database_record") as record:
            result = gallery.delete_pdf_output("PDFs/Gone")
        record.assert_called_once_with("g")
        self.assertEqual(result["status"], "deleted")
        self.assertFalse(gone.exists())
        self.assertTrue(keep.is_dir())


class ManifestCacheTests(GalleryTestCase):
    def test_changed_manifest_is_reread_and_removed_one_dropped(self):
        folder = self.make_pdf_folder()
        self.assertEqual(len(gallery.gallery_cards()), 2)
        manifest_path = folder / "ocr-results.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["pages"] = manifest["pages"][:1] + [{"page": 3, "image": "001 Load 1.jpg", "searchable_text": "a much longer replacement"}]
        manifest_path.write_text(json.dumps(manifest))
        self.assertEqual(sorted(c["page"] for c in gallery.gallery_cards()), [1, 3])
        manifest_path.unlink()
        self.assertEqual(gallery.gallery_cards(), [])


class ThumbnailTests(GalleryTestCase):
    def setUp(self):
        super().setUp()
        import pymupdf as fitz  # PyMuPDF 1.28+ has no 'fitz' module
        folder = self.make_pdf_folder()
        pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 1700, 2200), False)
        pixmap.clear_with(200)
        self.image = folder / "Images" / "001 Load 1.jpg"
        pixmap.save(str(self.image), output="jpeg", jpg_quality=95)
        self.rel = "PDFs/Load 1/Images/001 Load 1.jpg"

    def test_thumbnail_is_small_cached_and_reused(self):
        import pymupdf as fitz  # PyMuPDF 1.28+ has no 'fitz' module
        response = gallery.thumbnail_response(self.rel)
        thumbs = list((self.root / "_AppData" / "thumbs").glob("*.jpg"))
        self.assertEqual(len(thumbs), 1)
        self.assertEqual(Path(response.path), thumbs[0])
        self.assertLess(thumbs[0].stat().st_size, self.image.stat().st_size / 4)
        self.assertEqual(fitz.Pixmap(str(thumbs[0])).width, 425)
        self.assertIn("max-age", response.headers["cache-control"])
        modified = thumbs[0].stat().st_mtime_ns
        gallery.thumbnail_response(self.rel)
        self.assertEqual(thumbs[0].stat().st_mtime_ns, modified)
        self.assertEqual(len(list((self.root / "_AppData" / "thumbs").iterdir())), 1)

    def test_thumbnail_rejects_traversal_and_pdfs(self):
        for bad in ["../x.jpg", "PDFs/Load 1/Load 1.pdf"]:
            with self.assertRaises(HTTPException):
                gallery.thumbnail_response(bad)

    def test_unreadable_image_falls_back_to_original(self):
        # make_pdf_folder's page 2 is a stub, not a decodable JPEG
        response = gallery.thumbnail_response("PDFs/Load 1/Images/002 Load 1.jpg")
        self.assertEqual(Path(response.path).name, "002 Load 1.jpg")


if __name__ == "__main__":
    import unittest
    unittest.main()
