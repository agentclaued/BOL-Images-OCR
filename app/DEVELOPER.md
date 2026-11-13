# Developer guide

## What to run

Use app/services/batch_pdf_to_images.py for terminal-based PDF conversion and
OCR. It scans a source folder (including subfolders), creates JPG page images,
extracts OCR text with RapidOCR, creates a separate searchable PDF with
OCRmyPDF, classifies the document, and refreshes the gallery.

app/services/ocr.py is a supporting Python module. Do not run it directly; the
batch script imports it.

| File | Purpose |
| --- | --- |
| app/services/batch_pdf_to_images.py | Main terminal OCR and PDF-to-JPG workflow. |
| app/services/ocr.py | OCR provider functions used by the batch workflow. |
| app/services/gallery.py | Gallery file operations and live gallery data. |
| app/main.py | Local FastAPI gallery server. |
| app/serve_gallery.py | Standalone fallback gallery server. |

## Run OCR from PowerShell

Open PowerShell in the project folder:

~~~powershell
Set-Location "D:\PDF TO IMAGES PHOTS  v2 online auto"
~~~

Use the project Python installation and process a folder of PDFs:

~~~powershell
$py = "C:\Users\Lenovo\AppData\Local\Programs\Python\Python314\python.exe"
& $py .\app\services\batch_pdf_to_images.py "D:\Incoming BOL PDFs" --ocr-provider rapidocr
~~~

RapidOCR is the approved default local image-OCR provider. The workflow also
uses the RapidOCR results (invisible PyMuPDF text layer) to create a separate searchable PDF; it never replaces
the original PDF.

Processing order: the app creates the searchable PDF first. While JPG rendering
and RapidOCR continue, View by PDF shows the document with the label
Processing image scan and provides its searchable-PDF download. Completed page
images and OCR search results appear afterward.

For a single PDF, put only that PDF in a temporary input folder, then run the
same command against that folder:

~~~powershell
& $py .\app\services\batch_pdf_to_images.py "D:\Incoming BOL PDFs\One PDF" --ocr-provider rapidocr
~~~

If you omit the source folder, the script asks for it:

~~~powershell
& $py .\app\services\batch_pdf_to_images.py
~~~

Optional settings:

~~~powershell
# Higher JPG resolution; slower and larger output.
& $py .\app\services\batch_pdf_to_images.py "D:\Incoming BOL PDFs" --dpi 300

# Use a different company alias file.
& $py .\app\services\batch_pdf_to_images.py "D:\Incoming BOL PDFs" --companies "D:\My Lists\companies.txt"
~~~

## Repair missing searchable PDFs

If image cards show Searchable PDF unavailable, the original PDF and JPG pages
exist but OCRmyPDF did not create its separate searchable-PDF output. Repair
all existing gallery folders with:

~~~powershell
$py = "C:\Users\Lenovo\AppData\Local\Programs\Python\Python314\python.exe"
& $py .\app\services\batch_pdf_to_images.py --repair-searchable
~~~

This keeps original PDFs and JPGs unchanged. It creates only the missing
Searchable.pdf files, updates their manifests, and refreshes the gallery.
The FastAPI app also starts this repair automatically in the background each
time it starts; use the command above when an immediate manual repair is needed.
At startup the app checks for Tesseract and, when winget or Chocolatey is
already installed, uses that package manager to install Tesseract automatically.
It does not install a package manager itself.

## Install Tesseract manually

Tesseract is required only for creating Searchable.pdf files through OCRmyPDF.
RapidOCR still creates the JPG-page OCR text and gallery search data without it.

If the app reports that Tesseract is missing and no package manager is
available:

1. Download the 64-bit Windows installer from the
   [UB Mannheim Tesseract download page](https://digi.bib.uni-mannheim.de/tesseract/).
   Tesseract's own Windows documentation refers to these installers:
   [Tesseract Windows installation instructions](https://tesseract-ocr.github.io/tessdoc/Installation.html).
   From the directory listing, select:

   ~~~text
   tesseract-ocr-w64-setup-5.4.0.20240606.exe
   ~~~

   This is the newest stable 64-bit installer in that list. Do not choose
   files labelled w32, alpha, beta, rc, or dev.
2. Run the installer as Administrator.
3. Keep the default installation directory:

   ~~~text
   C:\Program Files\Tesseract-OCR
   ~~~

   A per-user installation directory is also supported by this app:

   ~~~text
   C:\Users\{Windows user}\AppData\Local\Programs\Tesseract-OCR
   ~~~

4. Keep English language data selected.
5. Add the installation directory to the Windows system PATH:

   - Press Win + R, enter sysdm.cpl, then press Enter.
   - Select Advanced, then Environment Variables.
   - Under System variables, select Path, choose Edit, then New.
   - Add:

     ~~~text
     C:\Program Files\Tesseract-OCR
     ~~~

   - Confirm all dialogs, then open a new PowerShell window.

6. Verify the installation:

   ~~~powershell
   tesseract --version
   ~~~

7. Restart BOL Images. Its startup repair creates missing searchable PDFs.

## Tesseract and searchable-PDF troubleshooting

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Tesseract is missing | Tesseract is not installed or is not on PATH. | Install it using the steps above, open a new terminal, and restart the app. |
| PDF cards show Searchable PDF unavailable | The JPG/OCR pages exist, but Searchable.pdf was not created. | Install Tesseract, then run Repair-MissingSearchablePdfs or restart the app. |
| tesseract is not recognized after installation | The terminal was opened before PATH changed, or PATH was not updated. | Close PowerShell, open a new one, then run tesseract --version. |
| OCRmyPDF reports Ghostscript is missing | Ghostscript is an additional OCRmyPDF dependency. | Install Ghostscript for Windows, reopen PowerShell, and run the repair command again. |
| Automatic install cannot run | Neither winget nor Chocolatey exists on the PC. | Install Tesseract manually; the app does not silently install a package manager. |
| Repair still fails for one PDF | The source PDF is absent, damaged, locked, or OCRmyPDF reports another error. | Read the server log, confirm the original PDF remains in its document folder, then rerun the repair command. |

## Output

Results are written locally under BOL images/{company}/{PDF name}/:

- Original copied PDF
- Searchable PDF version
- Numbered JPG pages
- ocr-results.json

The live BOL images/index.html opens in Photos view by default. It loads thumbnails lazily and receives short OCR previews first; searching still sends matching full OCR text only. This keeps large galleries responsive on the local network.

The live BOL images/index.html is refreshed automatically. It does not embed
OCR records; when served through app/main.py, it lists only files that still
exist on disk.

## Browser processing queue and recovery

The Process panel uses a small local SQLite database at
`BOL images/_AppData/jobs.db`.
It normally takes only a few KB to a few MB because it stores job status and
the most recent 24 KB of each job log, not PDF files, JPGs, or OCR records.

For every folder or PDF-file upload, processing happens in this order:

1. Create a separate searchable PDF for **all** selected PDFs.
2. Show each ready searchable PDF in **View by PDF** with the label
   `Processing image scan` and a download link.
3. Render JPG page images and run RapidOCR only after step 1 completes for
   the entire selection.

Use **Hold current job** to stop safely. Already-created searchable PDFs and
page work remain in `BOL images/_Processing`. Starting another job holds the
active job automatically. Choose a held item from **Resume selected** to
continue it; after an app or PC restart, an interrupted job is also shown as
held instead of being lost. A resumed job reuses completed work and skips
finished pages where possible.

If a deployment copy retains `BOL images/_Processing` and uploaded PDFs but
does not retain `BOL images/_AppData/jobs.db`, startup recreates matching jobs
as held batches. Select the recovered batch and use **Resume batch**. If the
original uploaded PDF is unavailable, the app leaves the temporary work intact
and reports that the same PDF must be uploaded again.

After a PDF finishes successfully, its `_Processing` folder is deleted
automatically. Final files remain in the company/PDF output folder. Therefore
only held or unfinished jobs retain temporary processing files; older stale
temporary folders are removed during app startup.

The database and browser-upload source folders both live in
`BOL images/_AppData/`, so moving the `BOL images` folder to another PC keeps
the queue history and resumable uploaded jobs with it. On first startup after
this update, the app automatically moves old `storage/jobs.db` and
`storage/uploads` into this folder and updates saved upload paths.

Gallery refresh cleanup never removes queued, running, or held jobs, or their browser-uploaded PDF folders. Only completed and failed queue records are eligible for cleanup.

The database is operational state only. Do not delete
`BOL images/_AppData/jobs.db` while the app is running. If it is deleted while
the app is stopped, completed BOL files remain intact, but the held-job history
disappears.

Browser-uploaded PDFs in `BOL images/_AppData/uploads/` are treated as valid
input. Other PDFs already inside `BOL images` are ignored so the app never
mistakes its generated gallery copies for new source documents.

## Manual data validation and repair

The Process panel has a **DataValidate** button. It checks processed PDF
records only when the user starts it; it does not alter files during the
validation pass. It stores PDF SHA-256 values, output folder, actual PDF page
count, searchable-PDF status, and one row per page in `jobs.db`.

Validation checks the preserved original PDF, searchable PDF, manifest, JPG
page files, OCR text, and actual page count. It pauses whenever the normal
Process panel has a queued, running, or held job. The daily developer log is:

`BOL images/_AppData/logs/integrity-YYYY-MM-DD.log`

If missing items are found, the app asks whether to repair them. Repair creates
only missing searchable PDFs, JPG pages, and OCR records; valid files are not
recreated.

In **View by PDF**, each PDF card includes **Delete this PDF data**. After its
confirmation prompt, it permanently removes that PDF's output folder,
including its original PDF, searchable PDF, JPGs, OCR manifest, Trash files,
and matching validation database records. It cannot be restored.

## Startup dependency check

Both `start_bol_images_app.bat` and `start app in backgroup.bat` run `python -m pip install -r requirements.txt` before starting the server. Pip keeps already-satisfied packages and downloads only missing or incompatible requirements. If installation fails, the server does not start; reconnect to the internet or repair Python, then run the launcher again.

## Run the local gallery server

~~~powershell
$py = "C:\Users\Lenovo\AppData\Local\Programs\Python\Python314\python.exe"
& $py -m uvicorn app.main:app --host 127.0.0.1 --port 8766
~~~

Then open http://127.0.0.1:8766/.

The gallery API is available at http://127.0.0.1:8766/api/gallery. It
supplies live file and OCR search data to the HTML page.

## Custom command labels

Paste these functions into PowerShell to use clear, short command names during
the current terminal session:

~~~powershell
$py = "C:\Users\Lenovo\AppData\Local\Programs\Python\Python314\python.exe"
$ocrmyPdf = "C:\Users\Lenovo\AppData\Local\Programs\Python\Python314\Scripts\ocrmypdf.exe"

function Create-BolImagesFromPdf {
    param([Parameter(Mandatory)] [string] $SourceFolder)
    & $py .\app\services\batch_pdf_to_images.py $SourceFolder --searchable-only
    if ($LASTEXITCODE -eq 0) {
        & $py .\app\services\batch_pdf_to_images.py $SourceFolder --images-only --ocr-provider rapidocr
    }
}

function Create-SearchablePdfsFirst {
    param([Parameter(Mandatory)] [string] $SourceFolder)
    & $py .\app\services\batch_pdf_to_images.py $SourceFolder --searchable-only
}

function Create-BolImagesAfterSearchable {
    param([Parameter(Mandatory)] [string] $SourceFolder)
    & $py .\app\services\batch_pdf_to_images.py $SourceFolder --images-only --ocr-provider rapidocr
}

function Make-PdfSearchable {
    param(
        [Parameter(Mandatory)] [string] $InputPdf,
        [Parameter(Mandatory)] [string] $OutputPdf
    )
    & $ocrmyPdf --skip-text --deskew --output-type pdf $InputPdf $OutputPdf
}

function Refresh-BolGallery {
    & $py -c "from app.services.batch_pdf_to_images import generate_gallery; generate_gallery()"
}

function Repair-MissingSearchablePdfs {
    & $py .\app\services\batch_pdf_to_images.py --repair-searchable
}

function Start-BolGallery {
    & $py -m uvicorn app.main:app --host 127.0.0.1 --port 8766
}
~~~

Use the labels like this:

~~~powershell
# Create JPG page images, OCR records, and a searchable PDF for every PDF
# in this folder.
Create-BolImagesFromPdf "D:\Incoming BOL PDFs"

# Run the same two phases separately when working in the terminal.
Create-SearchablePdfsFirst "D:\Incoming BOL PDFs"
Create-BolImagesAfterSearchable "D:\Incoming BOL PDFs"

# Create a separate searchable version. Do not use the same output path as
# the original PDF.
Make-PdfSearchable "D:\Incoming\invoice.pdf" "D:\Incoming\invoice Searchable.pdf"

# Rebuild only the lightweight gallery HTML.
Refresh-BolGallery

# Create searchable PDFs for older folders where they are missing.
Repair-MissingSearchablePdfs

# Start the local gallery website.
Start-BolGallery
~~~

To retain these command labels for future PowerShell sessions, add the function
definitions to your PowerShell profile. They do not change the project files or
upload documents anywhere.

## Notes

### Spreadsheet gallery

- The process panel accepts `.xls`, `.xlsx`, and `.csv` through **Upload spreadsheets**.
  Uploads are indexed locally without OCR, macro execution, or formula recalculation.
- Originals are preserved byte-for-byte in `BOL images/_AppData/uploads/spreadsheets/{id}/`.
  The original filename is recorded in `BOL images/_AppData/spreadsheets.db` alongside
  sheet names, row numbers, cell addresses, values, and available formulas.
- `app/services/spreadsheets.py` handles ingestion and paginated row search.
  `app/services/spreadsheet_gallery.html` provides file boxes and the table viewer;
  the gallery generator embeds this asset. Include both files in deployments.
- Search matches filenames, PDF OCR, and cells across all workbook sheets. The file-type
  view dropdown offers View by file (all files), View by PDF, and View by XLS/CSV
  (XLS, XLSX, CSV). Each view shows file boxes and combines with View by date.
  Spreadsheet cards have selection checkboxes and individual/bulk permanent deletion
  with filename confirmation. Only visible selected spreadsheets are included;
  changing filters clears hidden selections. DELETE /api/spreadsheets/{id}?confirm=true
  removes that imported original and its indexed sheets/rows, without deleting the
  external source file. This is not a Trash/Restore operation and cannot be undone.

## Filename-based document layout

`BOL images/PDFs/{PDF name}` contains the original PDF, searchable PDF,
`ocr-results.json`, and an `Images/` subfolder with its JPG pages. The
top-level `BOL images/Images` folder is reserved for directly uploaded images.
Spreadsheets are stored in `BOL images/Spreadsheets/{file name}`, alongside a
small `spreadsheet-data.json` record. Company matching and company folders are
not used. Each gallery rebuild and spreadsheet listing automatically detects
older company/upload layouts, organizes them into this layout, restores a
missing spreadsheet search index from visible `spreadsheet-data.json` files,
and removes an old internal copy only after confirming it is byte-for-byte
identical.

The gallery refresh runs retention cleanup from the unfiltered default View by
file inventory. Only represented PDF/image/spreadsheet folders are retained.
Temporary search, file-type filters, and Trash do not change that retention
set. Held jobs and their source uploads are always retained; completed/failed
job records, unused upload folders, and old logs are removed.
  Opening a workbook provides sheet selection, cell search, 100-row paging, and download.
- Import limits: 50 MB per file, 500,000 cells, 2,048 columns, and 200 MB uncompressed
  XLSX contents. Invalid files return an upload error without publishing a partial index.
  Failed originals remain local. CSV supports UTF-8/BOM, UTF-16 BOM, and Windows-1252
  fallback; delimiter detection supports comma, semicolon, tab, and pipe.
- XLSX formulas use saved results and show a warning when a result is absent. XLS
  exposes saved values. Simple zero-padding formats are preserved; this is a searchable
  value table, not a reproduction of all Excel formatting or charts.
- `python -m unittest discover -s tests -p test_spreadsheets.py -v` tests ingestion,
  search, provenance, paging, validation and exact original downloads with temporary data.
  `node tests/gallery_views.cjs` checks the existing PDF browsing behavior.

- The batch processor calculates a SHA-256 fingerprint from each PDF's actual
  contents and skips only an identical PDF. The fingerprint is 64 characters
  (about 0.2 KB or less in an OCR manifest) and is calculated in 1 MB chunks,
  so it does not load the full PDF into memory. A revised PDF with the same
  filename is processed as a new document; two different same-named PDFs are
  kept in separate hash-suffixed folders when necessary.
- Keep source PDFs outside BOL images; otherwise they are ignored to prevent
  reprocessing generated copies.
- Do not switch to cloud OCR providers without approval. They can send document
  content to an external service.




