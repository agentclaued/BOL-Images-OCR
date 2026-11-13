# PDF TO IMAGES PHOTS — Project Instructions

## Purpose

Maintain a local BOL PDF-to-image and OCR gallery. The workflow scans supplied PDF folders, converts each page to a JPG, extracts OCR text, classifies the PDF into a company folder, creates a searchable PDF, and displays all images in a browser gallery.

## Required output structure

```text
BOL images/
  _AppData/
    jobs.db
    uploads/
  {company name}/
    {PDF file name}/
      {original PDF}.pdf
      {PDF file name} Searchable.pdf
      001 {PDF file name} {company name}.jpg
      002 {PDF file name} {company name}.jpg
      ocr-results.json
      Trash/
  index.html
```

- Preserve the source PDF; copy it into the PDF output folder and never overwrite it.
- Each page image must be a JPG named `{page number:03d} {PDF file name} {company name}.jpg`.
- Store raw OCR text, embedded PDF text, searchable text, page number, image name, and detected company in `ocr-results.json`.
- Create a separate `{PDF file name} Searchable.pdf` with an invisible text layer built from the RapidOCR results (PyMuPDF), so each page is OCR'd once. Never replace the original PDF.
- Keep persistent local queue state and browser-upload source files in
  `BOL images/_AppData/` so they move with the gallery folder between PCs.

## Company matching

- Use `companies.txt` as the source of configured company names and aliases.
- Match company names case-insensitively and tolerate punctuation differences in OCR text.
- If no company list entry matches, use the value after `USE Name:` in OCR text as the company folder name. Use `Unmatched company` only when that field is unavailable.
- Keep company folders local under `BOL images`.

## Gallery requirements

- `BOL images/index.html` is the gallery home page and must be regenerated after processing.
- Show every page image with its image name, company, source PDF, page number, searchable PDF page link, and raw/searchable OCR preview.
- OCR text must be expandable within its own image card.
- Search must match image details and OCR text, and visibly highlight matched text in yellow.
- The View dropdown must provide All photos, View by PDF, and View by date. View by PDF first shows one PDF card; selecting it shows its page image cards.
- Each image card includes a download icon and a Trash icon. Trash cards include a restore icon.
- Download actions must cause a browser download rather than opening the JPG in a new tab. Use the local gallery server endpoint when required.
- Trash/restore must ultimately move JPG files between the PDF folder and that PDF folder's `Trash` folder; do not delete files permanently unless explicitly requested.

## Runtime and safety

- `app/services/batch_pdf_to_images.py` asks interactively for the source PDF folder if no argument is supplied.
- Default image OCR uses RapidOCR. PyMuPDF writes the searchable PDF text layer from the RapidOCR results; OCRmyPDF is no longer used. Do not change OCR providers without user approval.
- `app/main.py` hosts the gallery locally through FastAPI. `app/serve_gallery.py` is a standalone fallback server.
- Keep all generated artifacts local. Do not upload BOL PDFs or OCR data to an external service unless the user explicitly chooses and authorizes a cloud OCR provider.
- Do not add unrelated application, accounting, spreadsheet, SQL, or cloud deployment code.

## Deployment package

- 00 Ready to Deploy is the clean deployment package for this application.
- When a deployment-relevant source, configuration, launcher, or developer-guide
  file changes, refresh its corresponding copy in 00 Ready to Deploy in the
  same edit.
- Include application code, requirements.txt, companies.txt, launch/watch
  scripts, and developer documentation. Do not include BOL images, uploaded
  PDFs, OCR manifests, databases, or Python cache files in the package.
