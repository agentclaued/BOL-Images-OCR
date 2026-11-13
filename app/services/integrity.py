"""Low-priority validation and repair for completed BOL PDF output."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pymupdf as fitz  # PyMuPDF 1.28+ has no 'fitz' module

from .gallery import GALLERY_DIR
from .storage_layout import PDFS

APP_DATA_DIR = GALLERY_DIR / "_AppData"
DATABASE_PATH = APP_DATA_DIR / "jobs.db"
LOG_DIR = APP_DATA_DIR / "logs"
_worker_lock = threading.Lock()
_status_lock = threading.Lock()
_status: dict[str, object] = {"state": "idle", "repair": False, "checked": 0, "total": 0, "needs_repair": 0, "message": "No validation has run."}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_schema() -> None:
    with _connect() as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS processed_pdfs (
            source_sha256 TEXT PRIMARY KEY, source_pdf TEXT NOT NULL,
            output_folder TEXT NOT NULL, company TEXT NOT NULL,
            page_count INTEGER NOT NULL, searchable_pdf TEXT NOT NULL,
            validation_status TEXT NOT NULL, last_action TEXT NOT NULL,
            last_checked TEXT NOT NULL, last_error TEXT NOT NULL DEFAULT ''
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS processed_pages (
            source_sha256 TEXT NOT NULL, page_number INTEGER NOT NULL,
            image_name TEXT NOT NULL, image_exists INTEGER NOT NULL,
            ocr_exists INTEGER NOT NULL, last_checked TEXT NOT NULL,
            PRIMARY KEY (source_sha256, page_number)
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS processed_pdfs_checked ON processed_pdfs(last_checked)")


def _log(event: str, message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"integrity-{datetime.now().strftime('%Y-%m-%d')}.log"
    path.open("a", encoding="utf-8").write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {event} | {message}\n")


def user_job_is_active() -> bool:
    """Never compete with a panel job, including a held job awaiting a choice."""
    try:
        with _connect() as connection:
            return connection.execute("SELECT 1 FROM jobs WHERE state IN ('queued', 'running', 'held') LIMIT 1").fetchone() is not None
    except sqlite3.Error:
        return False


def _text_exists(page: dict[str, object]) -> bool:
    return bool(str(page.get("raw_ocr", "")).strip() or str(page.get("pdf_text", "")).strip() or str(page.get("searchable_text", "")).strip())


def _searchable_path(folder: Path, manifest: dict[str, object]) -> Path:
    named = folder / str(manifest.get("searchable_pdf", ""))
    if named.is_file():
        return named
    candidates = sorted(folder.glob("* Searchable.pdf"))
    return candidates[0] if len(candidates) == 1 else named


def _image_folder(folder: Path, manifest: dict[str, object]) -> Path:
    configured = GALLERY_DIR / str(manifest.get("images_folder", ""))
    return configured if configured.is_dir() else folder


def _record(manifest_path: Path, manifest: dict[str, object], source_sha256: str, page_count: int, status: str, action: str, error: str = "") -> None:
    folder = manifest_path.parent
    image_folder = _image_folder(folder, manifest)
    searchable = _searchable_path(folder, manifest)
    checked = _now()
    with _connect() as connection:
        connection.execute("""INSERT INTO processed_pdfs
            (source_sha256, source_pdf, output_folder, company, page_count, searchable_pdf, validation_status, last_action, last_checked, last_error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_sha256) DO UPDATE SET
              source_pdf=excluded.source_pdf, output_folder=excluded.output_folder, company=excluded.company,
              page_count=excluded.page_count, searchable_pdf=excluded.searchable_pdf,
              validation_status=excluded.validation_status, last_action=excluded.last_action,
              last_checked=excluded.last_checked, last_error=excluded.last_error
        """, (source_sha256, str(manifest.get("source_pdf", "")), str(folder.relative_to(GALLERY_DIR)), "", page_count, searchable.name if searchable.is_file() else "", status, action, checked, error))
        connection.execute("DELETE FROM processed_pages WHERE source_sha256=?", (source_sha256,))
        records = {int(item.get("page", 0)): item for item in manifest.get("pages", []) if int(item.get("page", 0)) > 0}
        for number in range(1, page_count + 1):
            page = records.get(number, {})
            image_name = str(page.get("image", ""))
            stored_name = (image_folder / image_name).relative_to(GALLERY_DIR).as_posix() if image_name else ""
            connection.execute("INSERT INTO processed_pages VALUES (?, ?, ?, ?, ?, ?)", (source_sha256, number, stored_name, int(bool(image_name and (image_folder / image_name).is_file())), int(_text_exists(page)), checked))


def record_manifest(manifest_path: Path) -> None:
    """Record a newly completed PDF immediately, without a background scan."""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_sha256 = str(manifest.get("source_sha256", ""))
        source = manifest_path.parent / Path(str(manifest.get("source_pdf", ""))).name
        if not source_sha256 or not source.is_file():
            return
        with fitz.open(source) as document:
            _record(manifest_path, manifest, source_sha256, len(document), "valid", "processed")
    except (OSError, json.JSONDecodeError, fitz.FileDataError):
        return


def is_database_pdf_valid(source_sha256: str) -> bool:
    """Fast duplicate check: DB record and all recorded final files must exist."""
    try:
        with _connect() as connection:
            pdf = connection.execute("SELECT * FROM processed_pdfs WHERE source_sha256=? AND validation_status='valid'", (source_sha256,)).fetchone()
            if pdf is None:
                return False
            folder = GALLERY_DIR / pdf["output_folder"]
            original = folder / pdf["source_pdf"]
            searchable = folder / pdf["searchable_pdf"]
            pages = connection.execute("SELECT image_name FROM processed_pages WHERE source_sha256=?", (source_sha256,)).fetchall()
            return original.is_file() and searchable.is_file() and len(pages) == int(pdf["page_count"]) and all((folder / row["image_name"]).is_file() for row in pages)
    except sqlite3.Error:
        return False


def delete_database_record(source_sha256: str) -> None:
    """Remove registry data only after the user confirmed deletion of output."""
    if not source_sha256:
        return
    ensure_schema()
    with _connect() as connection:
        connection.execute("DELETE FROM processed_pages WHERE source_sha256=?", (source_sha256,))
        connection.execute("DELETE FROM processed_pdfs WHERE source_sha256=?", (source_sha256,))


def _create_searchable_pdf(source: Path, target: Path) -> None:
    from .ocr import build_searchable_pdf
    build_searchable_pdf(source, target)


def validate_and_repair(manifest_path: Path, repair: bool = False) -> str:
    """Validate one final output folder and repair only missing page artifacts."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    folder = manifest_path.parent
    image_folder = _image_folder(folder, manifest)
    source = folder / Path(str(manifest.get("source_pdf", ""))).name
    source_sha256 = str(manifest.get("source_sha256", ""))
    if not source.is_file():
        key = source_sha256 or f"missing:{folder.relative_to(GALLERY_DIR).as_posix()}"
        _record(manifest_path, manifest, key, len(manifest.get("pages", [])), "needs_source", "checked", "Preserved original PDF is missing.")
        return "needs source PDF"

    from .batch_pdf_to_images import pdf_sha256, safe_name
    from .ocr import extract_rapidocr_text

    source_sha256 = pdf_sha256(source)
    changed, repaired, missing = False, [], []
    with fitz.open(source) as document:
        page_count = len(document)
        records = {int(item.get("page", 0)): item for item in manifest.get("pages", []) if int(item.get("page", 0)) > 0}
        searchable = _searchable_path(folder, manifest)
        if not searchable.is_file():
            missing.append("searchable PDF")
            if not repair:
                searchable = folder / f"{safe_name(source.stem)} Searchable.pdf"
            else:
                try:
                    _create_searchable_pdf(source, folder / f"{safe_name(source.stem)} Searchable.pdf")
                    searchable = folder / f"{safe_name(source.stem)} Searchable.pdf"
                    manifest["searchable_pdf"] = searchable.name
                    changed = True
                    repaired.append("searchable PDF")
                except Exception as error:
                    _record(manifest_path, manifest, source_sha256, page_count, "needs_ocr_dependency", "checked", str(error))
                    return "searchable PDF needs OCR dependency"
        for number in range(1, page_count + 1):
            if user_job_is_active():
                raise InterruptedError("user processing job became active")
            record = records.get(number, {})
            image_name = str(record.get("image", "")) or f"{number:03d} {safe_name(source.stem)}.jpg"
            image = image_folder / image_name
            page = document[number - 1]
            if not image.is_file():
                missing.append(f"page {number} JPG")
                if repair:
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(200 / 72, 200 / 72), alpha=False)
                    pixmap.save(image, output="jpeg", jpg_quality=90)
                    repaired.append(f"page {number} JPG")
                    changed = True
            if not _text_exists(record):
                missing.append(f"page {number} OCR")
                if repair:
                    if not image.is_file():
                        continue
                    record["raw_ocr"] = extract_rapidocr_text(image)
                    record["pdf_text"] = page.get_text().strip()
                    record["searchable_text"] = record["raw_ocr"] or record["pdf_text"]
                    repaired.append(f"page {number} OCR")
                    changed = True
            record.update(page=number, image=image_name)
            record.pop("detected_company", None)
            records[number] = record
    manifest["source_sha256"] = source_sha256
    manifest["pages"] = [records[number] for number in sorted(records) if number <= page_count]
    if missing and not repair:
        _record(manifest_path, manifest, source_sha256, page_count, "needs_repair", "validated", ", ".join(missing))
        return "needs repair: " + ", ".join(missing)
    if changed:
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    _record(manifest_path, manifest, source_sha256, page_count, "valid", "repaired" if repaired else "checked")
    return "repaired " + ", ".join(repaired) if repaired else "valid"


def _wait_until_idle() -> None:
    announced = False
    while user_job_is_active():
        if not announced:
            _log("PAUSED", "User processing job is active or held.")
            announced = True
        time.sleep(3)


def integrity_status() -> dict[str, object]:
    with _status_lock:
        return dict(_status)


def _set_status(**changes: object) -> None:
    with _status_lock:
        _status.update(changes)


def _run_integrity_worker(repair: bool, initial_delay: int = 0) -> None:
    try:
        ensure_schema()
        _set_status(state="running", repair=repair, checked=0, total=0, needs_repair=0, message="Checking processed PDFs in the background...")
        _log("START", "Manual repair started." if repair else "Manual validation started.")
        if initial_delay:
            time.sleep(initial_delay)
        manifests = list(PDFS.rglob("ocr-results.json"))
        _set_status(total=len(manifests))
        for index, manifest_path in enumerate(manifests, start=1):
            _wait_until_idle()
            try:
                outcome = validate_and_repair(manifest_path, repair=repair)
                _log("CHECK", f"{index}/{len(manifests)} | {manifest_path.parent.name} | {outcome}")
                _set_status(checked=index, needs_repair=int(_status.get("needs_repair", 0)) + int(outcome.startswith("needs repair") or outcome == "needs source PDF"), message=outcome)
            except InterruptedError:
                _log("PAUSED", f"{manifest_path.parent.name} | user job started")
                continue
            except Exception as error:
                _log("ERROR", f"{manifest_path.parent.name} | {error}")
            if index % 5 == 0:
                time.sleep(1)
        _log("COMPLETE", f"Background validation finished: {len(manifests)} PDF record(s).")
        _set_status(state="complete", checked=len(manifests), message="Repair completed." if repair else "Validation completed.")
        from .batch_pdf_to_images import generate_gallery
        generate_gallery()
    finally:
        _worker_lock.release()


def start_background_integrity_check() -> None:
    """Run one low-priority startup pass without blocking FastAPI startup."""
    if not _worker_lock.acquire(blocking=False):
        return
    threading.Thread(target=_run_integrity_worker, args=(False, 10), name="bol-integrity-check", daemon=True).start()


def start_manual_integrity_check(repair: bool = False) -> dict[str, object]:
    """Start a user-requested pass; it still pauses when a panel job is active."""
    if not _worker_lock.acquire(blocking=False):
        return integrity_status()
    threading.Thread(target=_run_integrity_worker, args=(repair,), name="bol-integrity-manual", daemon=True).start()
    return integrity_status()
