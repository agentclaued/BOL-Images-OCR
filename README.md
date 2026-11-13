# BOL-Images-OCR

Local BOL PDF-to-image and OCR gallery. It scans PDFs, renders each page to JPG, runs RapidOCR, sorts each PDF into a company folder, builds a searchable PDF, and serves a browser gallery (FastAPI, default port **8510**).

All data stays local. Nothing is uploaded to an external service.

## Quick start (Windows)

1. Install Python 3.11+ and (optional) Tesseract.
2. Double-click `app/App Control Center/00 1 ON - Start in terminal.bat`. The first run creates a `.venv` and installs `requirements.txt`.
3. Open `http://localhost:8510/`.

Or manually:

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8510
```

Batch conversion from a terminal:

```powershell
python app\services\batch_pdf_to_images.py "D:\Incoming BOL PDFs" --ocr-provider rapidocr
```

## Output layout

```text
BOL images/
  _AppData/ (jobs.db, uploads/)
  {company}/{PDF name}/
      original PDF, "{PDF name} Searchable.pdf",
      001 {PDF name} {company}.jpg ..., ocr-results.json, Trash/
  index.html
```

`BOL images/` is git-ignored (private data).

## Documentation

| Doc | Contents |
| --- | --- |
| [docs/RUN_FLOW.md](docs/RUN_FLOW.md) | How the app starts and processes a PDF, for debugging |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Real errors seen in the field and their fixes |
| [app/DEVELOPER.md](app/DEVELOPER.md) | Developer guide |
| [CLAUDE.md](CLAUDE.md) | Instructions for Claude Code in this repo |
| [AGENTS.md](AGENTS.md) | Project rules |

## Control Center scripts

`app/App Control Center/` holds numbered ON/OFF launchers: terminal run (00), background (11), boot auto-start (22), login tray (33), dev reload (44), boot task with console window (66, recommended). See its `README.txt`.
