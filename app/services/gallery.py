"""Local gallery file operations."""

from __future__ import annotations

import hashlib
import mimetypes
import os
import time
import json
import shutil
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response
from .storage_layout import PDFS, migrate_legacy_gallery


PROJECT_DIR = Path(__file__).resolve().parents[2]
GALLERY_DIR = PROJECT_DIR / "BOL images"
_last_migration = 0.0


def ensure_gallery_dir() -> Path:
    GALLERY_DIR.mkdir(exist_ok=True)
    migrate_legacy_gallery()
    return GALLERY_DIR


def _file_names(folder: Path) -> set[str]:
    """One directory listing instead of an exists-check per file (slow on network drives)."""
    try:
        with os.scandir(folder) as entries:
            return {entry.name for entry in entries if entry.is_file()}
    except OSError:
        return set()


def _manifest_paths() -> list[Path]:
    """Manifests live one or two levels under PDFs; avoid walking every image folder."""
    found = set(PDFS.glob("*/ocr-results.json")) | set(PDFS.glob("*/*/ocr-results.json"))
    return sorted(found)


_manifest_cache: dict[Path, tuple[tuple[int, int], dict]] = {}


def _read_manifest(path: Path) -> dict | None:
    """Parse an OCR manifest once per change; the gallery list is requested often."""
    try:
        stat = path.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        cached = _manifest_cache.get(path)
        if cached and cached[0] == signature:
            return cached[1]
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _manifest_cache.pop(path, None)
        return None
    if not isinstance(manifest, dict):
        return None
    _manifest_cache[path] = (signature, manifest)
    return manifest


def gallery_cards(query: str = "", trash: bool = False, include_text: bool = True) -> list[dict[str, str | int | bool]]:
    """Return only gallery pages that currently exist on disk.

    OCR manifests remain the source of metadata, while the JPG existence check
    prevents the browser from receiving cards for deleted or moved files.
    """
    # Upgrading older page-image locations walks every file, so do it at most
    # every 30 seconds instead of on each request.
    global _last_migration
    if time.monotonic() - _last_migration > 30:
        migrate_legacy_gallery()
        _last_migration = time.monotonic()
    normalized_query = query.casefold().strip()
    cards: list[dict[str, str | int | bool]] = []
    for manifest_path in _manifest_paths():
        manifest = _read_manifest(manifest_path)
        if manifest is None:
            continue

        source_name = Path(str(manifest.get("source_pdf", ""))).name
        source_path = manifest_path.parent / source_name
        pdf_files = _file_names(manifest_path.parent)
        source_exists = source_name in pdf_files
        image_dir = GALLERY_DIR / str(manifest.get("images_folder", ""))
        image_files = _file_names(image_dir) if image_dir.is_dir() else None
        if image_files is None:
            image_dir = manifest_path.parent
            image_files = pdf_files
        trash_files = _file_names(image_dir / "Trash")
        searchable_name = str(manifest.get("searchable_pdf") or f"{Path(source_name).stem} Searchable.pdf")
        searchable_path = manifest_path.parent / searchable_name
        searchable_exists = searchable_name in pdf_files
        if not searchable_exists:
            candidates = sorted(name for name in pdf_files if name.endswith(" Searchable.pdf"))
            if len(candidates) == 1:
                searchable_path = manifest_path.parent / candidates[0]
                searchable_exists = True

        for page in manifest.get("pages", []):
            image_name = str(page.get("image", ""))
            in_images = image_name in image_files
            is_trash = not in_images and image_name in trash_files
            if (not in_images and not is_trash) or is_trash != trash:
                continue
            active_path = (image_dir / "Trash" / image_name) if is_trash else (image_dir / image_name)

            page_text = str(page.get("searchable_text", ""))
            card: dict[str, str | int | bool] = {
                "image": active_path.relative_to(GALLERY_DIR).as_posix(),
                "name": active_path.name,
                "pdf": str(manifest.get("source_pdf", "")),
                "page": int(page.get("page", 0)),
                "date": str(manifest.get("processed_at", ""))[:10] or "Unknown date",
                "processed_at": str(manifest.get("processed_at", "")),
                "text": (page_text if include_text or normalized_query else page_text[:600]),
                "trash": is_trash,
                "source_pdf": source_path.relative_to(GALLERY_DIR).as_posix() if source_exists else "",
                "searchable_pdf": searchable_path.relative_to(GALLERY_DIR).as_posix() if searchable_exists else "",
                "pdf_folder": manifest_path.parent.relative_to(GALLERY_DIR).as_posix(),
                "image_folder": image_dir.relative_to(GALLERY_DIR).as_posix(),
            }
            if not normalized_query or normalized_query in " ".join([str(value) for value in card.values()] + [page_text]).casefold():
                cards.append(card)

    if not trash:
        processing_root = GALLERY_DIR / "_Processing"
        for state_path in processing_root.glob("*/processing-state.json"):
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if state.get("status") == "complete":
                continue
            source_name = Path(str(state.get("source_pdf", ""))).name
            searchable_name = str(state.get("searchable_pdf") or f"{Path(source_name).stem} Searchable.pdf")
            searchable_path = state_path.parent / searchable_name
            if not searchable_path.is_file():
                continue
            card = {
                "image": "",
                "name": source_name,
                "pdf": source_name,
                "page": 0,
                "date": "Processing",
                "text": "Searchable PDF is ready. Image rendering and OCR are still processing.",
                "trash": False,
                "processing": True,
                "source_pdf": "",
                "searchable_pdf": searchable_path.relative_to(GALLERY_DIR).as_posix(),
            }
            if not normalized_query or normalized_query in " ".join(str(value) for value in card.values()).casefold():
                cards.append(card)
    return cards


def delete_pdf_output(relative_folder: str) -> dict[str, str]:
    """Permanently delete one user-selected PDF output and its registry rows."""
    root = ensure_gallery_dir().resolve()
    target = (root / relative_folder).resolve()
    if PDFS.resolve() not in target.parents or not target.is_dir():
        raise HTTPException(status_code=404, detail="PDF output folder not found.")
    manifest_path = target / "ocr-results.json"
    if not manifest_path.is_file():
        raise HTTPException(status_code=404, detail="This folder is not a processed PDF output.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=409, detail=f"Could not read PDF record: {error}") from error
    source_sha256 = str(manifest.get("source_sha256", ""))
    shutil.rmtree(target)
    from .integrity import delete_database_record

    delete_database_record(source_sha256)
    return {"status": "deleted", "pdf": str(manifest.get("source_pdf", ""))}


def local_image(relative_path: str) -> Path:
    root = ensure_gallery_dir().resolve()
    target = (root / relative_path).resolve()
    if root not in target.parents or not target.is_file() or target.suffix.lower() not in {".jpg", ".jpeg"}:
        raise HTTPException(status_code=404, detail="Image not found")
    return target


def download_response(relative_path: str) -> Response:
    """Download a local image or PDF without widening Trash file operations."""
    root = ensure_gallery_dir().resolve()
    target = (root / relative_path).resolve()
    if root not in target.parents or not target.is_file() or target.suffix.lower() not in {".jpg", ".jpeg", ".pdf"}:
        raise HTTPException(status_code=404, detail="Download file not found")
    return Response(
        content=target.read_bytes(),
        media_type=mimetypes.guess_type(target.name)[0] or "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(target.name)}"},
    )


THUMB_WIDTH = 400


def thumbnail_response(relative_path: str) -> Response:
    """Serve a small cached JPEG preview so cards do not download full scans."""
    image = local_image(relative_path)
    stat = image.stat()
    cache_dir = GALLERY_DIR / "_AppData" / "thumbs"
    key = hashlib.sha1(f"{relative_path}|{stat.st_mtime_ns}|{stat.st_size}".encode("utf-8")).hexdigest()
    thumb = cache_dir / f"{key}.jpg"
    if not thumb.is_file():
        try:
            import pymupdf as fitz  # PyMuPDF 1.28+ has no 'fitz' module

            cache_dir.mkdir(parents=True, exist_ok=True)
            pixmap = fitz.Pixmap(str(image))
            if pixmap.alpha or pixmap.colorspace is None or pixmap.colorspace.n != 3:
                pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
            while pixmap.width // 2 >= THUMB_WIDTH:
                pixmap.shrink(1)
            temp = thumb.with_name(f"{key}.{uuid.uuid4().hex}.tmp")
            pixmap.save(str(temp), output="jpeg", jpg_quality=72)
            os.replace(temp, thumb)
        except Exception:
            # A preview must never break the gallery: fall back to the original.
            return FileResponse(image, media_type="image/jpeg")
    return FileResponse(thumb, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


def move_to_trash(relative_path: str) -> dict[str, str]:
    image = local_image(relative_path)
    if image.parent.name == "Trash":
        return {"status": "already in trash"}
    trash_dir = image.parent / "Trash"
    trash_dir.mkdir(exist_ok=True)
    destination = trash_dir / image.name
    if destination.exists():
        raise HTTPException(status_code=409, detail="An image with this name is already in Trash.")
    shutil.move(str(image), str(destination))
    return {"status": "moved to trash"}


def restore_from_trash(relative_path: str) -> dict[str, str]:
    image = local_image(relative_path)
    if image.parent.name != "Trash":
        return {"status": "already restored"}
    destination = image.parent.parent / image.name
    if destination.exists():
        raise HTTPException(status_code=409, detail="An image with this name already exists outside Trash.")
    shutil.move(str(image), str(destination))
    return {"status": "restored"}



