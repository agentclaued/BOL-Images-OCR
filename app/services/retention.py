"""Keep only the files represented by unfiltered View-by-file gallery cards."""
from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

from .storage_layout import ROOT, PDFS


def _remove_directory(folder: Path, parent: Path) -> bool:
    if folder.is_dir() and folder.parent.resolve() == parent.resolve():
        shutil.rmtree(folder)
        return True
    return False


def clean_unshown_data() -> dict[str, int]:
    """Prune completed records while retaining every queued, running, or held job."""
    from .gallery import gallery_cards
    from . import spreadsheets

    PDFS.mkdir(parents=True, exist_ok=True)
    # Default View by file is based on all normal gallery cards, never a search
    # query, an individual file filter, or the Trash tab.
    cards = gallery_cards()
    kept_pdf_folders = {str(card.get("pdf_folder", "")) for card in cards if card.get("pdf_folder")}
    removed_pdfs = sum(_remove_directory(folder, PDFS) for folder in list(PDFS.iterdir()) if folder.is_dir() and str(folder.relative_to(ROOT).as_posix()) not in kept_pdf_folders)

    sheet_cards = spreadsheets.cards()
    removed_sheets = spreadsheets.clean_unshown_spreadsheets({str(card["file_id"]) for card in sheet_cards})

    app_data = ROOT / "_AppData"; jobs_db = app_data / "jobs.db"; kept_uploads: set[Path] = set(); removed_jobs = 0
    if jobs_db.is_file():
        try:
            db = sqlite3.connect(jobs_db); db.row_factory = sqlite3.Row
            active = db.execute("SELECT source_path FROM jobs WHERE state IN ('queued', 'running', 'held', 'failed')").fetchall()
            kept_uploads = {Path(str(row["source_path"])).resolve().parent for row in active}
            with db:
                removed_jobs = db.execute("DELETE FROM jobs WHERE state='complete'").rowcount
            db.close()
        except sqlite3.Error:
            pass
    uploads = app_data / "uploads"; removed_uploads = 0
    if uploads.is_dir():
        for folder in list(uploads.iterdir()):
            if folder.resolve() not in kept_uploads and _remove_directory(folder, uploads):
                removed_uploads += 1
    logs = app_data / "logs"
    if logs.is_dir():
        for item in list(logs.iterdir()):
            if item.is_file(): item.unlink()
    return {"pdf_folders": removed_pdfs, "spreadsheet_folders": removed_sheets, "job_records": removed_jobs, "upload_folders": removed_uploads}

