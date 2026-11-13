"""HTTP-level integration tests over a disposable gallery tree."""
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import main
from app.services import processing
from gallery_fixture import GalleryTestCase

IMG = "PDFs/Load 1/Images/001 Load 1.jpg"
TRASHED = "PDFs/Load 1/Images/Trash/001 Load 1.jpg"


class ApiIntegrationTests(GalleryTestCase):
    def setUp(self):
        super().setUp()
        app_data = self.root / "_AppData"
        extra = [
            patch.object(processing, "APP_DATA_DIR", app_data),
            patch.object(processing, "UPLOAD_DIR", app_data / "uploads"),
            patch.object(processing, "DATABASE_PATH", app_data / "jobs.db"),
            patch.object(main, "UPLOAD_DIR", app_data / "uploads"),
            # Pruning would touch the real spreadsheet store; it is covered separately.
            patch.object(main, "clean_unshown_data", lambda: {}),
        ]
        for item in extra:
            item.start()
            self.patches.append(item)
        processing._initialize()
        self.make_pdf_folder()
        # No lifespan/startup: do not rebuild the real gallery or start repair threads.
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()
        super().tearDown()

    def test_health(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})

    def test_gallery_listing_search_and_validation(self):
        cards = self.client.get("/api/gallery").json()
        self.assertEqual(len(cards), 2)
        self.assertEqual([c["page"] for c in self.client.get("/api/gallery", params={"query": "beta"}).json()], [2])
        self.assertEqual(self.client.get("/api/gallery", params={"trash": "maybe"}).status_code, 422)

    def test_trash_restore_round_trip_keeps_file(self):
        self.assertEqual(self.client.post("/api/trash", params={"file": IMG}).json(), {"status": "moved to trash"})
        self.assertEqual(len(self.client.get("/api/gallery").json()), 1)
        trashed = self.client.get("/api/gallery", params={"trash": True}).json()
        self.assertEqual([c["image"] for c in trashed], [TRASHED])
        self.assertTrue((self.root / TRASHED).is_file())
        self.assertEqual(self.client.post("/api/restore", params={"file": TRASHED}).json(), {"status": "restored"})
        self.assertEqual(len(self.client.get("/api/gallery").json()), 2)
        self.assertEqual(self.client.get("/api/gallery", params={"trash": True}).json(), [])

    def test_trash_missing_and_traversal_are_404(self):
        for bad in ["PDFs/Load 1/Images/nope.jpg", "../x.jpg"]:
            self.assertEqual(self.client.post("/api/trash", params={"file": bad}).status_code, 404)
        self.assertEqual(self.client.post("/api/trash").status_code, 422)

    def test_download_is_attachment(self):
        response = self.client.get("/api/download", params={"file": IMG})
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers["content-disposition"])
        self.assertEqual(response.content, b"\xff\xd8jpg")
        self.assertEqual(self.client.get("/api/download", params={"file": "../x.jpg"}).status_code, 404)

    def test_pdf_delete_removes_only_that_folder(self):
        other = self.make_pdf_folder("Load 2", source_sha256="zzz")
        with patch("app.services.integrity.delete_database_record"):
            response = self.client.post("/api/pdf/delete", params={"folder": "PDFs/Load 1"})
        self.assertEqual(response.json()["status"], "deleted")
        self.assertFalse((self.pdfs / "Load 1").exists())
        self.assertTrue(other.is_dir())
        self.assertEqual(self.client.post("/api/pdf/delete", params={"folder": ""}).status_code, 422)

    def test_process_status_idle(self):
        body = self.client.get("/api/process/status").json()
        self.assertEqual(body["state"], "idle")
        self.assertEqual(body["held_jobs"], [])

    def test_custom_slots_require_password(self):
        response = self.client.post("/api/process/path", params={"source_path": "C:/nope", "slots": 3})
        self.assertEqual(response.status_code, 403)
        response = self.client.post("/api/process/path", params={"source_path": "C:/nope", "slots": 0})
        self.assertEqual(response.status_code, 422)
        with patch.object(main, "start_processing", return_value={"state": "queued"}) as start:
            response = self.client.post("/api/process/path", params={"source_path": '"C:/in"', "slots": 3},
                                        headers={"X-Slot-Password": "moreslots"})
        self.assertEqual(response.status_code, 200)
        start.assert_called_once_with(Path("C:/in"), slots=3)

    def test_upload_rejects_non_pdf_and_duplicates(self):
        files = {"files": ("notes.txt", b"hi")}
        self.assertEqual(self.client.post("/api/process/upload", files=files).status_code, 409)
        with patch.object(main, "start_processing", return_value={"state": "queued"}) as start, \
             patch.object(main, "duplicate_pdf_names", return_value=[]):
            both = [("files", ("a.pdf", b"same")), ("files", ("b.pdf", b"same"))]
            body = self.client.post("/api/process/upload", files=both).json()
        self.assertEqual(start.call_count, 1)
        self.assertEqual(body["duplicates"], [{"uploaded": "b.pdf", "existing": ["a.pdf"]}])
        with patch.object(main, "duplicate_pdf_names", return_value=["old.pdf"]):
            response = self.client.post("/api/process/upload", files={"files": ("a.pdf", b"x")})
        self.assertEqual(response.status_code, 409)

    def test_image_upload_requires_supported_type(self):
        response = self.client.post("/api/process/images", files={"files": ("a.txt", b"x")})
        self.assertEqual(response.status_code, 400)

    def test_gallery_paging_total_header_and_order(self):
        self.make_pdf_folder("Load 2", pages=("one", "two", "three"), source_sha256="zzz")
        response = self.client.get("/api/gallery", params={"limit": 2})
        self.assertEqual(response.headers["x-total-count"], "5")
        self.assertEqual(len(response.json()), 2)
        rest = self.client.get("/api/gallery", params={"limit": 2, "offset": 2}).json()
        everything = self.client.get("/api/gallery").json()
        self.assertEqual(len(everything), 5)
        paged = response.json() + rest + self.client.get("/api/gallery", params={"limit": 2, "offset": 4}).json()
        self.assertEqual(sorted(c["image"] for c in paged), sorted(c["image"] for c in everything))
        self.assertEqual(self.client.get("/api/gallery", params={"limit": 0}).status_code, 422)

    def test_gallery_gzip_matches_plain_json(self):
        plain = self.client.get("/api/gallery", headers={"Accept-Encoding": "identity"})
        self.assertNotIn("content-encoding", plain.headers)
        raw = self.client.get("/api/gallery", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(raw.headers["content-encoding"], "gzip")
        self.assertEqual(raw.json(), plain.json())

    def test_media_is_not_recompressed(self):
        response = self.client.get("/media/" + IMG, headers={"Accept-Encoding": "gzip"})
        self.assertNotIn("content-encoding", response.headers)

    def test_thumb_endpoint(self):
        self.assertEqual(self.client.get("/api/thumb", params={"file": "../x.jpg"}).status_code, 404)
        self.assertEqual(self.client.get("/api/thumb", params={"file": IMG}).status_code, 200)

    def test_prune_is_throttled(self):
        calls = []
        with patch.object(main, "clean_unshown_data", lambda: calls.append(1)), patch.object(main, "_last_prune", 0.0):
            self.client.get("/api/gallery")
            self.client.get("/api/gallery")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    import unittest
    unittest.main()
