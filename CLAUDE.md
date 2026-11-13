# CLAUDE.md

Read [AGENTS.md](AGENTS.md) first; its rules apply here. Summary of what matters:

- Purpose: local BOL PDF to JPG + OCR gallery. Keep everything local; never upload PDFs or OCR data.
- OCR is RapidOCR; PyMuPDF builds the searchable PDF text layer. Do not change OCR providers without user approval. Never overwrite source PDFs.
- Trash/restore moves JPGs to the PDF folder's `Trash/`; never delete permanently unless asked.
- Do not add unrelated accounting, spreadsheet-app, SQL or cloud deployment code.
- Do not commit `BOL images/`, uploaded PDFs, OCR manifests, databases, logs or caches.

## Layout

- `app/main.py`: FastAPI server and API routes
- `app/services/processing.py`: job queue (sqlite `_AppData/jobs.db`), workers, watchdog
- `app/services/batch_pdf_to_images.py`: per-PDF pipeline
- `app/services/ocr.py`, `gallery.py`, `integrity.py`, `retention.py`, `storage_layout.py`
- `app/App Control Center/`: Windows launchers and tray
- `tests/`: pytest suites

## Debugging

See [docs/RUN_FLOW.md](docs/RUN_FLOW.md) for the runtime flow and where logs live, and [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for known issues.

## Conventions

- `.bat`/`.ps1` files must keep CRLF line endings (`.gitattributes` enforces this). LF-only batch files can break `goto :label`.
- Run tests: `python -m pytest tests`
- When a deployment-relevant file changes, refresh its copy in `00 Ready to Deploy` (see AGENTS.md).
