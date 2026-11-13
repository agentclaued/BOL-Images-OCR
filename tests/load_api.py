"""Local concurrency check for read endpoints against a seeded temp gallery.

Run: python tests/load_api.py [workers] [requests_per_worker]
"""
import gc
import statistics
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app import main
from app.services import processing
from gallery_fixture import GalleryTestCase

ENDPOINTS = ["/health", "/api/gallery", "/api/gallery?query=beta", "/api/process/status"]


class LoadTest(GalleryTestCase):
    workers = 20
    per_worker = 25

    def test_concurrent_reads(self):
        app_data = self.root / "_AppData"
        with patch.object(processing, "DATABASE_PATH", app_data / "jobs.db"), \
             patch.object(main, "clean_unshown_data", lambda: {}):
            processing._initialize()
            for n in range(25):
                self.make_pdf_folder(f"Load {n}", source_sha256=f"h{n}")
            client = TestClient(main.app)

            def worker(index):
                times, failures = [], 0
                for i in range(self.per_worker):
                    url = ENDPOINTS[(index + i) % len(ENDPOINTS)]
                    start = time.perf_counter()
                    status = client.get(url).status_code
                    times.append(time.perf_counter() - start)
                    failures += status != 200
                return times, failures

            started = time.perf_counter()
            with ThreadPoolExecutor(self.workers) as pool:
                results = list(pool.map(worker, range(self.workers)))
            elapsed = time.perf_counter() - started
            client.close()
        times = sorted(t for r in results for t in r[0])
        failures = sum(r[1] for r in results)
        print(f"\n{len(times)} requests, {self.workers} workers, {elapsed:.1f}s "
              f"({len(times) / elapsed:.0f} req/s) p50={statistics.median(times) * 1000:.0f}ms "
              f"p95={times[int(len(times) * 0.95)] * 1000:.0f}ms max={times[-1] * 1000:.0f}ms failures={failures}")
        gc.collect()
        self.assertEqual(failures, 0)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        LoadTest.workers = int(sys.argv[1])
    if len(sys.argv) > 2:
        LoadTest.per_worker = int(sys.argv[2])
    unittest.main(argv=[sys.argv[0]])
