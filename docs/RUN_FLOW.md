# Run flow (how the app runs)

## 1. Startup

```text
Control Center .bat  ->  _venv.bat  ->  _console_server.bat  ->  uvicorn app.main:app
```

1. **`_venv.bat`** finds the app root (the folder containing `app\main.py`). It then picks a Python environment in this order: `<root>\.venv`, `%ProgramData%\BOL_Images\venv`, `%LOCALAPPDATA%\BOL_Images\venv`. If none works it creates one. It falls back to the local ProgramData copy when the app folder is on a network share that refuses `python.exe`. It installs `requirements.txt` only when that file changed or an import fails. It sets `ROOT`, `PY` and `PYW`.
2. **`_console_server.bat`** (used by scheduled task `Tools-BOL_Images`):
   - Reads the command, port and URL from `cc_settings.py` and `settings.json`.
   - Checks `_paused.ps1` (pause flag: `logs\paused.flag`).
   - Exits if the port is already LISTENING, so it never starts a second copy.
   - Otherwise runs uvicorn with output appended to `logs\server.log`, and restarts after 10 s if it stops.
3. **`app/main.py`** on startup:
   - Initialises the gallery.
   - Recovers interrupted jobs (`processing.recover_interrupted_jobs`). It logs "Interrupted PDF could not be recovered because its source is unavailable" when the source file is gone.
   - Starts workers and the watchdog, and warms the gallery cache.
   - Starts the background integrity check and repairs missing searchable PDFs.

## 2. Processing a PDF

```text
Browser upload / path  ->  /api/process/*  ->  processing.start()  ->  job row in jobs.db
   ->  worker loop (slots)  ->  batch_pdf_to_images.py (one run per PDF)
   ->  gallery refresh (index.html + cache)
```

Per PDF (`process_pdf`):

1. Compute the SHA-256 of the source and check for duplicates against known hashes.
2. Create the searchable PDF first (PyMuPDF, text layer from RapidOCR). The gallery shows "Processing image scan" meanwhile.
3. Render each page to JPG (default 200 dpi), named `{page:03d} {PDF name} {company}.jpg`.
4. Run RapidOCR on each page and extract embedded PDF text.
5. Match the company via `companies.txt` aliases. If none matches, use the text after `USE Name:`, then `Unmatched company`.
6. Copy the original PDF, and write images and `ocr-results.json` into `BOL images/{company}/{PDF name}/`.
7. Record the manifest in the integrity database and refresh the gallery.

Background helpers:

- The **watchdog** flags stuck jobs (reprocess or delete them via `/api/process/job/*`).
- **integrity** validates and repairs manifests.
- **retention** removes unshown data.

## 3. Where to look when debugging

| What | Where |
| --- | --- |
| Server log (live) | `logs\server.log` (`66 5 LOG - Show live server log.bat`) |
| Pause state | `logs\paused.flag` |
| Job queue/state | `BOL images\_AppData\jobs.db` |
| Job status API | `GET /api/process/status` |
| Integrity API | `GET /api/integrity/status` |
| Health | `GET /health` |
| Port and PIDs | `66 3 CHECK - Show tasks ports and PIDs.bat`, or `netstat -ano \| findstr :8510` |
| Scheduled task | `schtasks /Query /TN Tools-BOL_Images /V /FO LIST` |

Manual foreground run (the best way to see errors):

```bat
call "app\App Control Center\_venv.bat"
cd /d "%ROOT%"
"%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port 8510
```

Environment sanity check:

```bat
"%PY%" -c "import sys,fastapi,uvicorn,pymupdf,rapidocr;print('PYTHON OK',sys.version.split()[0])"
```

## 4. Key API routes

`/api/gallery`, `/api/download`, `/api/thumb`, `/api/trash`, `/api/restore`, `/api/pdf/delete`, `/api/process/{path,stage,upload,images,stop,hold,resume,job/reprocess,job/delete}`, `/api/integrity/{status,validate,repair}`, `/api/spreadsheets/*`.
