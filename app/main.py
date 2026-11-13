"""FastAPI routes for the BOL Images gallery."""

from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import threading
import time
import uuid

from fastapi import FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from .services import spreadsheets
from .services.retention import clean_unshown_data

from .services.gallery import (
    GALLERY_DIR,
    download_response,
    delete_pdf_output,
    ensure_gallery_dir,
    gallery_cards,
    move_to_trash,
    restore_from_trash,
    thumbnail_response,
)
from .services.processing import (
    UPLOAD_DIR,
    bulk_stuck,
    delete_job as delete_stuck_job,
    duplicate_pdf_names,
    known_pdf_hashes,
    reprocess_job,
    delete_held as delete_held_processing,
    hold as hold_processing,
    resume as resume_processing,
    start as start_processing,
    start_images,
    status as processing_status,
    stop as stop_processing,
)
from .services.integrity import integrity_status, start_manual_integrity_check


ensure_gallery_dir()
app = FastAPI(title="BOL Images", docs_url="/docs")
app.mount("/media", StaticFiles(directory=str(GALLERY_DIR)), name="media")
_repair_lock = threading.Lock()


def ensure_gallery_index() -> Path:
    """Create the lightweight gallery shell when the app starts without one."""
    index = GALLERY_DIR / "index.html"
    if not index.is_file():
        from .services.batch_pdf_to_images import generate_gallery

        generate_gallery()
    return index


def repair_searchable_pdfs_in_background() -> None:
    """Repair older records without delaying application startup."""
    if not _repair_lock.acquire(blocking=False):
        return

    def repair() -> None:
        try:
            from .services.batch_pdf_to_images import cleanup_completed_processing, generate_gallery, repair_searchable_pdfs
            from .services.dependencies import ensure_tesseract

            available, message = ensure_tesseract()
            print(message, flush=True)
            if not available:
                return
            cleaned = cleanup_completed_processing()
            if cleaned:
                print(f"Removed {cleaned} completed temporary processing folder(s).", flush=True)
            repaired, failed = repair_searchable_pdfs()
            if repaired or failed:
                print(f"Searchable PDF startup repair: {repaired} created, {failed} failed.", flush=True)
            generate_gallery()
        except Exception as error:
            print(f"Searchable PDF startup repair failed: {error}", flush=True)
        finally:
            _repair_lock.release()

    threading.Thread(target=repair, name="searchable-pdf-repair", daemon=True).start()


@app.on_event("startup")
def initialize_gallery() -> None:
    # Rebuild the lightweight browser shell once per server start so deployed UI updates apply immediately.
    from .services.batch_pdf_to_images import generate_gallery

    generate_gallery()
    repair_searchable_pdfs_in_background()


@app.get("/health")
def health() -> dict[str, str]:
    """Lightweight endpoint for the local watchdog and service monitor."""
    return {"status": "ok"}


@app.get("/", response_class=FileResponse)
def gallery_home() -> FileResponse:
    # The gallery shell contains live UI logic, so always refresh it instead of
    # leaving a browser with an older JavaScript version after an app update.
    return FileResponse(ensure_gallery_index(), headers={"Cache-Control": "no-store"})


@app.get("/api/download")
def download_image(file: str = Query(...)) -> Response:
    return download_response(file)


@app.get("/api/thumb")
def thumbnail(file: str = Query(...)) -> Response:
    return thumbnail_response(file)


_last_prune = 0.0


_prune_running = threading.Lock()


def prune_unshown_data() -> None:
    """Pruning rescans the whole gallery, so run it in the background at most every 30 seconds."""
    global _last_prune
    if time.monotonic() - _last_prune < 30 or not _prune_running.acquire(blocking=False):
        return
    _last_prune = time.monotonic()

    def run() -> None:
        try:
            clean_unshown_data()
        except Exception:
            pass
        finally:
            _prune_running.release()

    threading.Thread(target=run, daemon=True).start()


_cards_cache: dict[tuple[bool, bool], tuple[float, list[dict[str, object]]]] = {}
_cards_lock = threading.Lock()
_cards_refreshing: set[tuple[bool, bool]] = set()
CARDS_FRESH_SECONDS = 5.0


_search_blobs: dict[tuple[bool, bool], list[str]] = {}


def _scan_cards(key: tuple[bool, bool]) -> list[dict[str, object]]:
    cards = gallery_cards(trash=key[0], include_text=key[1])
    # Lower-cased searchable text per card, built once per scan so a search is one
    # substring test per card instead of a disk scan.
    blobs = [" ".join(str(value) for value in card.values()).casefold() for card in cards] if key[1] else []
    with _cards_lock:
        _cards_cache[key] = (time.monotonic(), cards)
        _search_blobs[key] = blobs
        _cards_refreshing.discard(key)
    return cards


def search_cards(trash: bool, query: str) -> list[dict[str, object]]:
    """Search OCR text and card details in memory (full text, never truncated)."""
    key = (trash, True)
    cards = cached_gallery_cards(trash, True)
    with _cards_lock:
        blobs = _search_blobs.get(key, [])
    needle = query.casefold().strip()
    if len(blobs) != len(cards):  # cache replaced mid-request: fall back to a direct filter
        return [card for card in cards if needle in " ".join(str(value) for value in card.values()).casefold()]
    return [card for card, blob in zip(cards, blobs) if needle in blob]


def cached_gallery_cards(trash: bool, include_text: bool) -> list[dict[str, object]]:
    """Serve the last scan instantly and refresh it in the background.

    Only the very first request after a start waits for a disk scan, which can be
    slow on a network drive; every later request answers immediately.
    """
    key = (trash, include_text)
    with _cards_lock:
        entry = _cards_cache.get(key)
        if entry is not None:
            if time.monotonic() - entry[0] >= CARDS_FRESH_SECONDS and key not in _cards_refreshing:
                _cards_refreshing.add(key)
                threading.Thread(target=_refresh_quietly, args=(key,), daemon=True).start()
            return entry[1]
    return _scan_cards(key)


def _refresh_quietly(key: tuple[bool, bool]) -> None:
    try:
        _scan_cards(key)
    except Exception:
        with _cards_lock:
            _cards_refreshing.discard(key)


def warm_gallery_cache() -> None:
    for key in ((False, False), (False, True), (True, False)):
        try:
            _scan_cards(key)
        except Exception:
            pass


threading.Thread(target=warm_gallery_cache, name="bol-cache-warmup", daemon=True).start()


@app.middleware("http")
async def invalidate_cards_after_changes(request: Request, call_next):
    response = await call_next(request)
    if request.method in ("POST", "DELETE", "PUT"):
        with _cards_lock:
            _cards_cache.clear()
    return response


def _newest_first(cards: list[dict[str, object]]) -> list[dict[str, object]]:
    """Same order as the gallery page: date, processed time, PDF desc; page asc."""
    cards = sorted(cards, key=lambda card: int(card.get("page", 0)))
    for field in ("pdf", "processed_at", "date"):
        cards.sort(key=lambda card, field=field: str(card.get(field, "")), reverse=True)
    return cards


@app.get("/api/gallery")
def live_gallery(
    request: Request,
    query: str = Query(""),
    trash: bool = Query(False),
    include_text: bool = Query(True),
    offset: int = Query(0, ge=0),
    limit: int | None = Query(None, ge=1, le=5000),
) -> Response:
    """Serve a live, disk-backed gallery instead of embedding OCR data in HTML."""
    prune_unshown_data()
    cards = search_cards(trash, query) if query.strip() else list(cached_gallery_cards(trash, include_text))
    total = len(cards)
    if limit is not None:
        cards = _newest_first(cards)[offset:offset + limit]
    body = json.dumps(cards).encode("utf-8")
    headers = {"X-Total-Count": str(total), "Cache-Control": "no-store"}
    if "gzip" in request.headers.get("accept-encoding", "").lower():
        # Only this JSON is compressed; JPG/PDF media are already compressed.
        body = gzip.compress(body, 3)
        headers.update({"Content-Encoding": "gzip", "Vary": "Accept-Encoding"})
    return Response(body, media_type="application/json", headers=headers)


@app.post("/api/spreadsheets/upload")
async def upload_spreadsheets(files: list[UploadFile] = File(...)) -> dict:
    results, errors = [], []
    for upload in files:
        content = await upload.read(spreadsheets.MAX_BYTES + 1)
        try:
            results.append(await run_in_threadpool(spreadsheets.ingest, upload.filename or "", content))
        except HTTPException as error:
            errors.append({"name": upload.filename, "error": error.detail})
        finally:
            await upload.close()
    return {"files": results, "errors": errors}


@app.get("/api/spreadsheets")
def spreadsheet_cards(query: str = Query("")) -> list[dict]:
    return spreadsheets.cards(query)


@app.get("/api/spreadsheets/{file_id}/rows")
def spreadsheet_rows(file_id: str, sheet: int | None = Query(None, ge=0), query: str = Query(""), offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100)) -> dict:
    return spreadsheets.table(file_id, sheet, query, offset, limit)


@app.get("/api/spreadsheets/{file_id}/download")
def spreadsheet_download(file_id: str) -> FileResponse:
    path, name = spreadsheets.original(file_id)
    return FileResponse(path, filename=name)


@app.post("/api/trash")
def trash_image(file: str = Query(...)) -> dict[str, str]:
    return move_to_trash(file)


@app.delete("/api/spreadsheets/{file_id}")
def delete_spreadsheet(file_id: str, confirm: bool = Query(False)) -> dict:
    if not confirm:
        raise HTTPException(400, "Permanent deletion requires confirmation.")
    return spreadsheets.delete_permanently(file_id)


@app.post("/api/restore")
def restore_image(file: str = Query(...)) -> dict[str, str]:
    return restore_from_trash(file)


@app.post("/api/pdf/delete")
def delete_pdf(folder: str = Query(..., min_length=1)) -> dict[str, str]:
    return delete_pdf_output(folder)


@app.get("/api/integrity/status")
def data_validation_status() -> dict[str, object]:
    return integrity_status()


@app.post("/api/integrity/validate")
def validate_data() -> dict[str, object]:
    return start_manual_integrity_check(repair=False)


@app.post("/api/integrity/repair")
def repair_data() -> dict[str, object]:
    return start_manual_integrity_check(repair=True)


@app.get("/api/process/status")
def process_status() -> dict[str, object]:
    return processing_status()




def require_slot_password(slots: int, password: str) -> None:
    if slots != 1 and password != "moreslots":
        raise HTTPException(status_code=403, detail="Enter the correct password to use custom slots.")


@app.post("/api/process/path")
def process_path(source_path: str = Query(...), slots: int = Query(1, ge=1), slot_password: str = Header("", alias="X-Slot-Password")) -> dict[str, object]:
    require_slot_password(slots, slot_password)
    return start_processing(Path(source_path.strip().strip('"')), slots=slots)


_stage_lock = threading.Lock()
_staged_hashes: dict[str, dict[str, str]] = {}
MAX_FILES_PER_REQUEST = 25
MAX_PDF_BYTES = 1024 * 1024 * 1024


def _session_folder(session: str) -> Path:
    if not session or len(session) > 64 or not all(c.isalnum() or c in "-_" for c in session):
        raise HTTPException(status_code=400, detail="Invalid upload session.")
    return UPLOAD_DIR / session


async def _stage_pdfs(session: str, files: list[UploadFile]) -> dict[str, object]:
    """Stream PDFs to disk (never fully in memory), skipping duplicates and non-PDFs."""
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(status_code=413, detail=f"Send at most {MAX_FILES_PER_REQUEST} files per request.")
    folder = _session_folder(session)
    folder.mkdir(parents=True, exist_ok=True)
    known = await run_in_threadpool(known_pdf_hashes)
    accepted, duplicates, skipped = 0, [], []
    for upload in files:
        name = Path(upload.filename or "").name
        if not name or Path(name).suffix.lower() != ".pdf":
            skipped.append(name or "(unnamed)")
            await upload.close()
            continue
        temp = folder / (name + ".part")
        digest, size = hashlib.sha256(), 0
        try:
            with temp.open("wb") as target:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_PDF_BYTES:
                        raise HTTPException(status_code=413, detail=f"{name} is larger than 1 GB.")
                    digest.update(chunk)
                    await run_in_threadpool(target.write, chunk)
            value = digest.hexdigest()
            with _stage_lock:
                staged = _staged_hashes.setdefault(session, {})
                existing = known.get(value) or staged.get(value)
                if existing:
                    duplicates.append({"uploaded": name, "existing": [existing]})
                    temp.unlink(missing_ok=True)
                    continue
                destination = folder / name
                number = 2
                while destination.exists():  # same name, different content
                    destination = folder / f"{Path(name).stem} ({number}){Path(name).suffix}"
                    number += 1
                temp.replace(destination)
                staged[value] = name
                accepted += 1
        except HTTPException:
            temp.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()
    return {"accepted": accepted, "duplicates": duplicates, "skipped": skipped}


@app.post("/api/process/stage")
async def stage_upload(files: list[UploadFile] = File(...), session: str = Query(...)) -> dict[str, object]:
    """Receive one chunk of a large PDF selection; the browser sends many small chunks."""
    return await _stage_pdfs(session, files)


@app.post("/api/process/stage/start")
async def start_staged(session: str = Query(...), slots: int = Query(1, ge=1), slot_password: str = Header("", alias="X-Slot-Password")) -> dict[str, object]:
    require_slot_password(slots, slot_password)
    folder = _session_folder(session)
    if not folder.is_dir() or not any(folder.glob("*.pdf")):
        raise HTTPException(status_code=409, detail="No new PDFs were uploaded, so nothing was started.")
    result = await run_in_threadpool(start_processing, folder, None, "pdf", slots)
    with _stage_lock:
        _staged_hashes.pop(session, None)
    return result


@app.post("/api/process/upload")
async def process_upload(files: list[UploadFile] = File(...), slots: int = Query(1, ge=1), slot_password: str = Header("", alias="X-Slot-Password")) -> dict[str, object]:
    """Single-request upload kept for older pages; it uses the same streaming staging."""
    require_slot_password(slots, slot_password)
    session = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    totals: dict[str, object] = {"accepted": 0, "duplicates": [], "skipped": []}
    for index in range(0, len(files), MAX_FILES_PER_REQUEST):
        part = await _stage_pdfs(session, files[index:index + MAX_FILES_PER_REQUEST])
        totals["accepted"] += part["accepted"]
        totals["duplicates"] += part["duplicates"]
        totals["skipped"] += part["skipped"]
    if not totals["accepted"]:
        raise HTTPException(status_code=409, detail={"message": "Duplicate PDF upload was not started.", "duplicates": totals["duplicates"]})
    result = await run_in_threadpool(start_processing, _session_folder(session), None, "pdf", slots)
    result["duplicates"] = totals["duplicates"]
    return result


@app.post("/api/process/images")
async def process_images(files: list[UploadFile] = File(...), slots: int = Query(1, ge=1), slot_password: str = Header("", alias="X-Slot-Password")) -> dict[str, object]:
    require_slot_password(slots, slot_password)
    upload_folder = UPLOAD_DIR / ("images-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    upload_folder.mkdir(parents=True, exist_ok=True)
    saved = 0
    for upload in files:
        if upload.filename and Path(upload.filename).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}:
            (upload_folder / Path(upload.filename).name).write_bytes(await upload.read())
            saved += 1
    if not saved:
        raise HTTPException(status_code=400, detail="Choose at least one supported image file.")
    return start_images(upload_folder, slots=slots)


@app.post("/api/process/stop")
def stop_process() -> dict[str, object]:
    return stop_processing()


@app.post("/api/process/hold")
def hold_process(held_by: str = Query("", max_length=80)) -> dict[str, object]:
    """Safely pause a job and retain the name of the person who held it."""
    return hold_processing(held_by)


@app.post("/api/process/resume")
def resume_process(job_id: str = Query(..., min_length=1)) -> dict[str, object]:
    return resume_processing(job_id)


@app.delete("/api/process/held")
def delete_held_process(job_id: str = Query(..., min_length=1)) -> dict[str, object]:
    return delete_held_processing(job_id)





@app.post("/api/process/job/reprocess")
def reprocess_stuck_job(job_id: str = Query(..., min_length=1)) -> dict[str, object]:
    return reprocess_job(job_id)


@app.post("/api/process/job/delete")
def delete_stuck_job_endpoint(job_id: str = Query(..., min_length=1)) -> dict[str, object]:
    return delete_stuck_job(job_id)


@app.post("/api/process/stuck/{action}")
def stuck_bulk_action(action: str) -> dict[str, object]:
    if action not in ("reprocess", "delete"):
        raise HTTPException(status_code=404, detail="Unknown action.")
    return bulk_stuck(action)
