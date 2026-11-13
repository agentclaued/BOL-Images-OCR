"""Persistent, recoverable browser-started PDF conversion jobs."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pymupdf as fitz  # PyMuPDF 1.28+ has no 'fitz' module
from fastapi import HTTPException

from .gallery import GALLERY_DIR, PROJECT_DIR
from .storage_layout import PDFS

BATCH_SCRIPT = PROJECT_DIR / "app" / "services" / "batch_pdf_to_images.py"
# Keep transferable app state beside the BOL documents, not in a separate
# project-level storage folder. _AppData is ignored by the gallery manifests.
APP_DATA_DIR = GALLERY_DIR / "_AppData"
UPLOAD_DIR = APP_DATA_DIR / "uploads"
DATABASE_PATH = APP_DATA_DIR / "jobs.db"
LEGACY_STORAGE_DIR = PROJECT_DIR / "storage"
LEGACY_DATABASE_PATH = LEGACY_STORAGE_DIR / "jobs.db"
LEGACY_UPLOAD_DIR = LEGACY_STORAGE_DIR / "uploads"
_lock = threading.RLock()
PDF_SLOTS = 1
_processes: dict[str, subprocess.Popen[str]] = {}
_workers: list[threading.Thread] = []
_dashboard: threading.Thread | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def _move_legacy_uploads() -> None:
    """Move old upload inputs into BOL images without overwriting a file."""
    if not LEGACY_UPLOAD_DIR.is_dir():
        return
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for source in LEGACY_UPLOAD_DIR.iterdir():
        destination = UPLOAD_DIR / source.name
        if destination.exists():
            number = 2
            while (UPLOAD_DIR / f"{source.name}-migrated-{number}").exists():
                number += 1
            destination = UPLOAD_DIR / f"{source.name}-migrated-{number}"
        shutil.move(str(source), str(destination))
    try:
        LEGACY_UPLOAD_DIR.rmdir()
    except OSError:
        pass


def _migrate_legacy_storage() -> None:
    """One-time safe migration from storage/ to BOL images/_AppData/."""
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    old_upload_root = str(LEGACY_UPLOAD_DIR.resolve()) if LEGACY_UPLOAD_DIR.exists() else str(LEGACY_UPLOAD_DIR)
    new_upload_root = str(UPLOAD_DIR.resolve())
    if LEGACY_DATABASE_PATH.is_file() and not DATABASE_PATH.exists():
        shutil.move(str(LEGACY_DATABASE_PATH), str(DATABASE_PATH))
    elif LEGACY_DATABASE_PATH.is_file() and DATABASE_PATH.is_file():
        # Preserve both histories when a copied app already has a newer DB.
        backup = APP_DATA_DIR / f"legacy-jobs-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
        shutil.move(str(LEGACY_DATABASE_PATH), str(backup))
    _move_legacy_uploads()
    if DATABASE_PATH.is_file():
        try:
            with sqlite3.connect(DATABASE_PATH) as connection:
                connection.execute("UPDATE jobs SET source_path=REPLACE(source_path, ?, ?) WHERE source_path LIKE ?", (old_upload_root, new_upload_root, old_upload_root + "%"))
        except sqlite3.Error:
            # A very old/non-queue database is kept intact; _initialize creates
            # a usable jobs table below when it is compatible.
            pass


def _initialize() -> None:
    """Create the queue and safely retain any job interrupted by an app restart."""
    with _connect() as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS processing_settings (id INTEGER PRIMARY KEY, slot_limit INTEGER NOT NULL)")
        connection.execute("INSERT OR IGNORE INTO processing_settings VALUES (1, 1)")
        connection.execute("""CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, source_path TEXT NOT NULL, kind TEXT NOT NULL,
            state TEXT NOT NULL, phase TEXT NOT NULL, message TEXT NOT NULL,
            logs TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )""")
        existing_columns = {row["name"] for row in connection.execute("PRAGMA table_info(jobs)")}
        for name, definition in (
            ("held_by", "TEXT NOT NULL DEFAULT ''"),
            ("held_at", "TEXT NOT NULL DEFAULT ''"),
            ("input_count", "INTEGER NOT NULL DEFAULT 0"),
            ("input_type", "TEXT NOT NULL DEFAULT ''"),
            ("batch_id", "TEXT NOT NULL DEFAULT ''"),
            ("progress", "INTEGER NOT NULL DEFAULT 0"),
            ("page_current", "INTEGER NOT NULL DEFAULT 0"),
            ("page_total", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if name not in existing_columns:
                connection.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
        connection.execute(
            "UPDATE jobs SET state='held', message='Held because the app restarted. Resume when ready.', "
            "held_by=CASE WHEN TRIM(held_by)='' THEN ? ELSE held_by END, "
            "held_at=CASE WHEN TRIM(held_at)='' THEN ? ELSE held_at END, updated_at=? "
            "WHERE state IN ('queued', 'running')", (_default_holder(), _now(), _now())
        )



def _pdf_hash(path: Path) -> str:
    """Return a content hash without loading a PDF into memory all at once."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def duplicate_pdf_names(source_sha256: str) -> list[str]:
    """Return processed or active PDF names with the same file contents."""
    matches: set[str] = set()
    for manifest_path in PDFS.rglob("ocr-results.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if str(manifest.get("source_sha256", "")).lower() == source_sha256.lower():
                matches.add(Path(str(manifest.get("source_pdf", ""))).name)
        except (OSError, json.JSONDecodeError):
            continue
    try:
        with _connect() as connection:
            rows = connection.execute("SELECT source_path FROM jobs WHERE state IN ('queued', 'running', 'held')").fetchall()
        for row in rows:
            source = Path(str(row["source_path"]))
            if source.is_file() and _pdf_hash(source).lower() == source_sha256.lower():
                matches.add(source.name)
    except (OSError, sqlite3.Error):
        pass
    return sorted(name for name in matches if name)

_job_hash_cache: dict[tuple[str, int, int], str] = {}


def known_pdf_hashes() -> dict[str, str]:
    """Map every processed or active PDF hash to its name with one pass, for bulk uploads."""
    known: dict[str, str] = {}
    for manifest_path in PDFS.rglob("ocr-results.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            digest = str(manifest.get("source_sha256", "")).lower()
            if digest:
                known[digest] = Path(str(manifest.get("source_pdf", ""))).name
        except (OSError, json.JSONDecodeError):
            continue
    try:
        with _connect() as connection:
            rows = connection.execute("SELECT source_path FROM jobs WHERE state IN ('queued', 'running', 'held')").fetchall()
        for row in rows:
            source = Path(str(row["source_path"]))
            if source.is_file():
                stat = source.stat()
                key = (str(source), stat.st_mtime_ns, stat.st_size)
                if key not in _job_hash_cache:
                    _job_hash_cache[key] = _pdf_hash(source).lower()
                known[_job_hash_cache[key]] = source.name
    except (OSError, sqlite3.Error):
        pass
    return known


def _source_for_recovery(state: dict[str, object]) -> Path | None:
    """Locate an unfinished job's original PDF, preferring its saved source."""
    source_name = Path(str(state.get("source_pdf", ""))).name
    expected_hash = str(state.get("source_sha256", "")).lower()
    candidates: list[Path] = []
    saved_path = str(state.get("source_path", "")).strip()
    if saved_path:
        candidates.append(Path(saved_path))
    if source_name and UPLOAD_DIR.is_dir():
        candidates.extend(UPLOAD_DIR.rglob(source_name))
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            if resolved in seen or not resolved.is_file() or resolved.suffix.lower() != ".pdf":
                continue
            seen.add(resolved)
            if not expected_hash or _pdf_hash(resolved).lower() == expected_hash:
                return resolved
        except OSError:
            continue
    return None


def recover_interrupted_jobs() -> int:
    """Recreate held rows when copied deployments retain work but lose jobs.db."""
    processing_root = GALLERY_DIR / "_Processing"
    if not processing_root.is_dir():
        return 0
    recovered = 0
    for state_path in processing_root.glob("*/processing-state.json"):
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(state.get("status", "")).lower() == "complete":
            continue
        source = _source_for_recovery(state)
        if source is None:
            print(f"Interrupted PDF could not be recovered because its source is unavailable: {state_path.parent.name}", flush=True)
            continue
        with _lock, _connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM jobs WHERE source_path=? AND state IN ('queued', 'running', 'held') LIMIT 1",
                (str(source),),
            ).fetchone()
            if exists:
                continue
            job_id, now = uuid.uuid4().hex, _now()
            connection.execute(
                "INSERT INTO jobs (id, batch_id, source_path, kind, state, phase, message, logs, created_at, updated_at, held_by, held_at, input_count, input_type, progress) "
                "VALUES (?, ?, ?, 'pdf', 'held', 'image_scan', ?, ?, ?, ?, ?, ?, 1, 'pdf', 50)",
                (job_id, job_id, str(source), "Recovered after restart. Resume this batch to finish page images and OCR.",
                 "Recovered from " + str(state_path) + "\n", now, now, _default_holder(), now),
            )
            recovered += 1
    if recovered:
        print(f"Recovered {recovered} interrupted PDF job(s) as held batches.", flush=True)
    return recovered
def _row(job: sqlite3.Row | None) -> dict[str, object]:
    if job is None:
        return {"state": "idle", "phase": "", "message": "No processing job has started.", "logs": "", "job_id": None, "held_jobs": []}
    return {"state": job["state"], "phase": job["phase"], "message": job["message"], "logs": job["logs"], "job_id": job["id"], "created_at": job["created_at"], "updated_at": job["updated_at"]}


def _held_jobs(connection: sqlite3.Connection) -> list[dict[str, object]]:
    rows = connection.execute(
        "SELECT batch_id, MAX(id) AS id, MAX(held_by) AS held_by, MAX(held_at) AS held_at, "
        "MAX(updated_at) AS updated_at, COUNT(*) AS input_count, MAX(input_type) AS input_type "
        "FROM jobs WHERE state='held' GROUP BY COALESCE(NULLIF(batch_id, ''), id) ORDER BY MAX(held_at) DESC, MAX(updated_at) DESC"
    ).fetchall()
    return [{
        "id": r["batch_id"] or r["id"], "source": "Held batch", "phase": "held",
        "message": "Held batch", "updated_at": r["updated_at"], "held_by": r["held_by"],
        "held_at": r["held_at"] or r["updated_at"], "input_count": r["input_count"],
        "input_type": r["input_type"] or "file",
    } for r in rows]


def status() -> dict[str, object]:
    with _lock, _connect() as connection:
        job = connection.execute("SELECT * FROM jobs WHERE state IN ('queued', 'running') ORDER BY updated_at DESC LIMIT 1").fetchone()
        if job is None:
            job = connection.execute("SELECT * FROM jobs ORDER BY updated_at DESC LIMIT 1").fetchone()
        result = _row(job)
        result["slot_limit"] = _slot_limit()
        result["held_jobs"] = _held_jobs(connection)
        if job is not None:
            field, value = ("batch_id", job["batch_id"]) if job["batch_id"] else ("id", job["id"])
            counts = {r["state"]: r["n"] for r in connection.execute(
                f"SELECT state, COUNT(*) AS n FROM jobs WHERE {field}=? GROUP BY state", (value,)
            )}
            result["batch_counts"] = {"total": sum(counts.values()), **{state: counts.get(state, 0) for state in ("complete", "failed", "held")}}
        result["active_slots"] = [dict(row) for row in connection.execute(
            "SELECT * FROM jobs WHERE state='running' ORDER BY updated_at, created_at"
        ).fetchall()]
        result["queued_jobs"] = [dict(row) for row in connection.execute(
            "SELECT * FROM jobs WHERE state='queued' ORDER BY created_at"
        ).fetchall()]
        result["stuck_jobs"] = _stuck_jobs(connection)
        return result


def _update(job_id: str, **values: object) -> None:
    values["updated_at"] = _now()
    columns = ", ".join(f"{key}=?" for key in values)
    with _connect() as connection:
        connection.execute(f"UPDATE jobs SET {columns} WHERE id=?", (*values.values(), job_id))


def _append_log(job_id: str, line: str) -> None:
    with _connect() as connection:
        row = connection.execute("SELECT logs FROM jobs WHERE id=?", (job_id,)).fetchone()
        logs = ((row["logs"] if row else "") + line)[-24000:]
        connection.execute("UPDATE jobs SET logs=?, updated_at=? WHERE id=?", (logs, _now(), job_id))


def _state(job_id: str) -> str:
    with _connect() as connection:
        row = connection.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()
    return str(row["state"]) if row else "missing"


def _run_command(job_id: str, phase: str, command: list[str]) -> bool:
    message = "Creating searchable PDFs for every selected PDF first..." if phase == "searchable" else "Creating JPG page images and RapidOCR records..."
    _update(job_id, state="running", phase=phase, message=message, progress=0 if phase == "searchable" else 50)
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    process = subprocess.Popen(command, cwd=PROJECT_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=environment)
    with _lock:
        _processes[job_id] = process
    assert process.stdout is not None
    for line in process.stdout:
        _append_log(job_id, line)
        if phase == "image_scan":
            # Converter output: "Page 12/25: rendering and reading OCR..."
            import re
            match = re.search(r"Page\s+(\d+)\s*/\s*(\d+)", line)
            if match:
                current, total = int(match.group(1)), int(match.group(2))
                _update(job_id, page_current=current, page_total=total,
                        progress=min(99, 50 + int((current / max(total, 1)) * 49)))
    return_code = process.wait(timeout=7200)
    with _lock:
        _processes.pop(job_id, None)
    if _state(job_id) != "running":
        # Held, deleted, reprocessed or watchdog-failed while it ran: keep that state.
        return False
    if return_code:
        _update(job_id, state="failed", message=f"{phase.replace('_', ' ').title()} phase failed. Check the log and resume after fixing it.")
        return False
    if phase == "searchable":
        _update(job_id, progress=50)
    return True


def _slot_limit() -> int:
    with _connect() as connection:
        row = connection.execute("SELECT slot_limit FROM processing_settings WHERE id=1").fetchone()
    return int(row[0]) if row else PDF_SLOTS


def _worker_loop() -> None:
    try:
        while True:
            with _lock, _connect() as connection:
                if connection.execute("SELECT COUNT(*) FROM jobs WHERE state='running'").fetchone()[0] >= _slot_limit():
                    return
                row = connection.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created_at LIMIT 1").fetchone()
                if row is not None:
                    connection.execute("UPDATE jobs SET state='running', message='Starting independent PDF job.', updated_at=? WHERE id=?", (_now(), row["id"]))
            if row is None:
                return
            job_id, source = str(row["id"]), Path(str(row["source_path"]))
            if not source.exists():
                _update(job_id, state="failed", message="The source PDF no longer exists.")
                continue
            if source.is_file():
                searchable = [sys.executable, str(BATCH_SCRIPT), str(source.parent), "--pdf-file", str(source), "--searchable-only"]
                images = [sys.executable, str(BATCH_SCRIPT), str(source.parent), "--pdf-file", str(source), "--images-only"]
            else:
                searchable = [sys.executable, str(BATCH_SCRIPT), str(source), "--searchable-only"]
                images = [sys.executable, str(BATCH_SCRIPT), str(source), "--images-only"]
            if not _run_command(job_id, "searchable", searchable):
                continue
            if not _run_command(job_id, "image_scan", images):
                continue
            _update(job_id, state="complete", phase="complete", message="Searchable PDFs, page images, and OCR records are ready.", progress=100)
    except Exception as error:
        if 'job_id' in locals() and _state(job_id) != "held":
            _update(job_id, state="failed", message=str(error))
    finally:
        with _lock:
            _workers[:] = [worker for worker in _workers if worker.is_alive() and worker is not threading.current_thread()]


def _ensure_worker() -> None:
    global _dashboard
    with _lock:
        _workers[:] = [worker for worker in _workers if worker.is_alive()]
        with _connect() as connection:
            pending = connection.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('running','queued')").fetchone()[0]
        while len(_workers) < min(_slot_limit(), pending):
            worker = threading.Thread(target=_worker_loop, name=f"bol-processing-slot-{len(_workers) + 1}", daemon=True)
            _workers.append(worker)
            worker.start()
        if _dashboard is None or not _dashboard.is_alive():
            _dashboard = threading.Thread(target=_dashboard_loop, name="bol-terminal-dashboard", daemon=True)
            _dashboard.start()


def _cell(value: object, width: int) -> str:
    text = str(value)
    return text[:width - 3] + "..." if len(text) > width else text.ljust(width)


def _render_dashboard() -> str:
    """Build the foreground-terminal queue display requested by the user."""
    with _connect() as connection:
        running = connection.execute("SELECT * FROM jobs WHERE state='running' ORDER BY updated_at, created_at").fetchall()
        queued = connection.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created_at").fetchall()
        complete = connection.execute("SELECT COUNT(*) FROM jobs WHERE state='complete'").fetchone()[0]
        failed = connection.execute("SELECT COUNT(*) FROM jobs WHERE state='failed'").fetchone()[0]
        held = connection.execute("SELECT COUNT(*) FROM jobs WHERE state='held'").fetchone()[0]
    lines = ["BOL Images — Parallel PDF Processing", "Refresh: every 1 second", f"Workers: {len(running)} active slots | Queue: {len(queued)} waiting | Total active batch: {len(running) + len(queued)} PDFs", "", "+------+----------+------------------------------------------+-------------+----------+---------+", "| Slot | Status   | PDF file                                 | Phase       | Progress | Pages   |", "+------+----------+------------------------------------------+-------------+----------+---------+"]
    for slot, row in enumerate(running, 1):
        phase = "Image OCR" if row["phase"] == "image_scan" else "Searchable"
        pages = f"{row['page_current']} / {row['page_total']}" if row["page_total"] else "-"
        lines.append(f"| {str(slot).ljust(4)} | RUNNING  | {_cell(Path(row['source_path']).name, 40)} | {_cell(phase, 11)} | {str(row['progress']) + '%':>8} | {_cell(pages, 7)} |")
    for slot in range(len(running) + 1, _slot_limit() + 1):
        lines.append(f"| {str(slot).ljust(4)} | EMPTY    | {'-'.ljust(40)} | {'-'.ljust(11)} | {'-':>8} | {'-'.ljust(7)} |")
    lines += ["+------+----------+------------------------------------------+-------------+----------+---------+", "", "Queued PDFs", "", "+--------+----------------------------------------------+----------+", "| Queue #| PDF file                                     | Progress |", "+--------+----------------------------------------------+----------+"]
    for number, row in enumerate(queued[:10], 1):
        lines.append(f"| {str(number).ljust(6)} | {_cell(Path(row['source_path']).name, 44)} | {str(row['progress']) + '%':>8} |")
    if len(queued) > 10:
        lines.append(f"| {'...'.ljust(6)} | {_cell(f'{len(queued) - 10} more PDFs waiting', 44)} | {'0%':>8} |")
    if not queued:
        lines.append(f"| {'-'.ljust(6)} | {'No PDFs waiting'.ljust(44)} | {'-':>8} |")
    lines += ["+--------+----------------------------------------------+----------+", "", f"Completed: {complete} | Failed: {failed} | Held: {held}"]
    return "\n".join(lines)


def _dashboard_loop() -> None:
    """Refresh once a second in a visible foreground console, never pythonw."""
    while True:
        with _connect() as connection:
            active = connection.execute("SELECT 1 FROM jobs WHERE state IN ('queued', 'running') LIMIT 1").fetchone()
        if active is None:
            return
        if sys.stdout.isatty():
            print("\x1b[2J\x1b[H" + _render_dashboard(), flush=True)
        time.sleep(1)


def _default_holder() -> str:
    """Use the local PC name whenever a person did not provide a name."""
    return socket.gethostname() or os.environ.get("COMPUTERNAME") or "This PC"


def _hold_active(message: str, held_by: str = "", batch_id: str | None = None) -> None:
    with _lock, _connect() as connection:
        holder = held_by.strip()[:80] or _default_holder()
        held_at = _now()
        scope = "AND batch_id=?" if batch_id else ""
        active_ids = {row["id"] for row in connection.execute(
            f"SELECT id FROM jobs WHERE state IN ('queued', 'running') {scope}",
            () if not batch_id else (batch_id,),
        ).fetchall()}
        connection.execute(
            f"UPDATE jobs SET state='held', message=?, held_by=?, held_at=?, updated_at=? WHERE state IN ('queued', 'running') {scope}",
            (message, holder, held_at, held_at, *(() if not batch_id else (batch_id,))),
        )
        for active_id, process in list(_processes.items()):
            if active_id in active_ids and process.poll() is None:
                process.terminate()


def start(source: Path, input_count: int | None = None, input_type: str = "pdf", slots: int = 1) -> dict[str, object]:
    if not isinstance(slots, int) or slots < 0:
        raise HTTPException(status_code=400, detail="Slots must be a positive whole number, or 0 for one slot per PDF.")
    if not source.is_dir():
        raise HTTPException(status_code=400, detail="The supplied PDF folder does not exist.")
    gallery_root = GALLERY_DIR.resolve()
    upload_root = UPLOAD_DIR.resolve()
    pdf_files = [path for path in source.rglob("*.pdf") if (
        path.suffix.casefold() == ".pdf" and (gallery_root not in path.resolve().parents or upload_root in path.resolve().parents)
    )]
    if not pdf_files:
        raise HTTPException(status_code=400, detail="No PDF files were found in the selected source. Choose PDF files or a folder that contains PDFs.")
    _hold_active("Held because a newer processing batch was started.")
    file_count = input_count if input_count is not None else len(pdf_files)
    batch_id = uuid.uuid4().hex
    with _connect() as connection:
        connection.execute("UPDATE processing_settings SET slot_limit=? WHERE id=1", (slots or len(pdf_files),))
        for pdf_file in pdf_files:
            job_id, now = uuid.uuid4().hex, _now()
            connection.execute(
                "INSERT INTO jobs (id, batch_id, source_path, kind, state, phase, message, logs, created_at, updated_at, input_count, input_type, progress) "
                "VALUES (?, ?, ?, 'pdf', 'queued', 'searchable', ?, '', ?, ?, ?, ?, 0)",
                (job_id, batch_id, str(pdf_file.resolve()), f"Queued: {pdf_file.name}", now, now, file_count, input_type),
            )
    _ensure_worker()
    return status()


def hold(held_by: str = "") -> dict[str, object]:
    with _lock, _connect() as connection:
        active = connection.execute("SELECT batch_id FROM jobs WHERE state IN ('queued', 'running') ORDER BY updated_at DESC LIMIT 1").fetchone()
    if active is None:
        raise HTTPException(status_code=409, detail="There is no active processing job to hold.")
    _hold_active("Held by user. Completed work remains saved; resume the batch when ready.", held_by, str(active["batch_id"]))
    return status()


def stop() -> dict[str, object]:
    """Compatibility alias: Stop now means safe hold, never discard progress."""
    return hold()


def resume(job_id: str) -> dict[str, object]:
    with _connect() as connection:
        row = connection.execute("SELECT batch_id FROM jobs WHERE state='held' AND (id=? OR batch_id=?) LIMIT 1", (job_id, job_id)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Held batch was not found.")
        batch_id = str(row["batch_id"])
        connection.execute("UPDATE jobs SET state='queued', message='Queued to resume as part of this batch.', updated_at=? WHERE state='held' AND batch_id=?", (_now(), batch_id))
    _ensure_worker()
    return status()


def delete_held(job_id: str) -> dict[str, object]:
    """Discard only held queue records; source files and OCR output are retained."""
    with _lock, _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id, batch_id FROM jobs WHERE state='held' AND (id=? OR batch_id=?) LIMIT 1",
            (job_id, job_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Held batch was not found. Refresh the list.")
        # Old entries have no batch ID: never treat all such entries as one batch.
        field, value = ("batch_id", row["batch_id"]) if row["batch_id"] else ("id", row["id"])
        rows = connection.execute(f"SELECT id, state FROM jobs WHERE {field}=?", (value,)).fetchall()
        if any(r["state"] in ("running", "queued") or
               (r["id"] in _processes and _processes[r["id"]].poll() is None) for r in rows):
            raise HTTPException(status_code=409, detail="This batch is still stopping or active. Hold it and wait before deleting.")
        connection.execute(f"DELETE FROM jobs WHERE {field}=? AND state='held'", (value,))
    return status()


STALL_SECONDS = 15 * 60  # a running PDF with no log or page progress for this long is stuck


def _age_seconds(timestamp: str) -> float:
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(timestamp)).total_seconds()
    except (TypeError, ValueError):
        return 0.0


def _stuck_jobs(connection: sqlite3.Connection) -> list[dict[str, object]]:
    """Failed jobs plus jobs that stopped making progress, for the Stuck files list."""
    rows = connection.execute(
        "SELECT * FROM jobs WHERE state IN ('failed', 'running', 'queued') ORDER BY updated_at DESC"
    ).fetchall()
    stuck: list[dict[str, object]] = []
    for row in rows:
        idle = _age_seconds(str(row["updated_at"]))
        alive = row["id"] in _processes and _processes[row["id"]].poll() is None
        if row["state"] == "failed":
            reason = "Failed"
        elif row["state"] == "running" and idle > STALL_SECONDS:
            reason = f"No progress for {int(idle // 60)} min"
        elif row["state"] == "running" and not alive and idle > 120:
            reason = "Worker stopped unexpectedly"
        elif row["state"] == "queued" and idle > STALL_SECONDS and not _workers:
            reason = "Waiting with no worker"
        else:
            continue
        stuck.append({
            "id": row["id"], "name": Path(str(row["source_path"])).name, "state": row["state"],
            "phase": row["phase"], "reason": reason, "message": row["message"],
            "updated_at": row["updated_at"], "idle_seconds": int(idle),
            "page_current": row["page_current"], "page_total": row["page_total"],
        })
    return stuck


def _terminate_job(job_id: str) -> None:
    with _lock:
        process = _processes.pop(job_id, None)
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def _partial_output_folders(source_name: str) -> list[Path]:
    """Unfinished _Processing folders that belong to this source PDF only."""
    root = GALLERY_DIR / "_Processing"
    folders: list[Path] = []
    for state_path in root.glob("*/processing-state.json") if root.is_dir() else []:
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(state.get("status", "")).lower() != "complete" and Path(str(state.get("source_pdf", ""))).name == source_name:
            folders.append(state_path.parent)
    return folders


def reprocess_job(job_id: str) -> dict[str, object]:
    """Stop a stuck/failed PDF and put it back at the end of the queue."""
    with _connect() as connection:
        row = connection.execute("SELECT id, source_path FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="That file is no longer in the queue. Refresh the list.")
    if not Path(str(row["source_path"])).exists():
        raise HTTPException(status_code=409, detail="The source PDF is missing, so it cannot be reprocessed. Delete it and upload it again.")
    _terminate_job(job_id)
    _update(job_id, state="queued", phase="searchable", message="Queued to reprocess.", progress=0, page_current=0, page_total=0, logs="")
    _ensure_worker()
    return status()


def delete_job(job_id: str) -> dict[str, object]:
    """Remove a stuck/failed queue entry and its unfinished partial output.

    The uploaded source PDF and any finished gallery pages are kept.
    """
    with _lock, _connect() as connection:
        row = connection.execute("SELECT id, source_path, state FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="That file is no longer in the queue. Refresh the list.")
    _terminate_job(job_id)
    with _connect() as connection:
        connection.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    for folder in _partial_output_folders(Path(str(row["source_path"])).name):
        shutil.rmtree(folder, ignore_errors=True)
    return status()


def bulk_stuck(action: str) -> dict[str, object]:
    with _connect() as connection:
        ids = [str(item["id"]) for item in _stuck_jobs(connection)]
    for job_id in ids:
        try:
            (reprocess_job if action == "reprocess" else delete_job)(job_id)
        except HTTPException:
            continue
    return status()


def _watchdog_loop() -> None:
    """Kill PDFs that stopped producing output so a bad file cannot hold a slot forever."""
    while True:
        time.sleep(60)
        try:
            with _connect() as connection:
                rows = connection.execute("SELECT id, updated_at FROM jobs WHERE state='running'").fetchall()
            for row in rows:
                if _age_seconds(str(row["updated_at"])) > STALL_SECONDS and row["id"] in _processes:
                    _update(str(row["id"]), state="failed", message="Stopped automatically: no progress for 15 minutes. Reprocess or delete it.")
                    _terminate_job(str(row["id"]))
        except Exception:
            continue


def _run_images(source: Path) -> int:
    images = [p for p in source.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}]
    if not images:
        raise HTTPException(status_code=400, detail="No supported image files were selected.")
    source_pdf = source / f"{source.name}.pdf"
    document = fitz.open()
    try:
        for image in images:
            image_doc = fitz.open(image)
            rect = image_doc[0].rect
            image_doc.close()
            page = document.new_page(width=rect.width, height=rect.height)
            page.insert_image(page.rect, filename=str(image))
        document.save(source_pdf)
    finally:
        document.close()
    return len(images)


def start_images(source: Path, slots: int = 1) -> dict[str, object]:
    image_count = _run_images(source)
    return start(source, input_count=image_count, input_type="image", slots=slots)


_migrate_legacy_storage()
_initialize()
recover_interrupted_jobs()
threading.Thread(target=_watchdog_loop, name="bol-watchdog", daemon=True).start()


