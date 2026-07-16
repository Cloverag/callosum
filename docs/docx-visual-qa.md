# DOCX visual QA

Callosum validates DOCX text extraction in the deterministic suite. This additional QA step
checks the rendered document, catching layout defects that text extraction cannot see:
clipping, overlap, missing glyphs, broken headings, and unexpected page breaks.

## Prerequisite

Install LibreOffice and use its console executable. On Windows:

```powershell
winget install --id TheDocumentFoundation.LibreOffice -e --silent `
  --accept-package-agreements --accept-source-agreements
```

If it is installed in a non-standard location, set `LIBREOFFICE_SOFFICE` to `soffice.com`.

## Render and inspect

```powershell
powershell -ExecutionPolicy Bypass -File scripts/render_docx_qa.ps1
```

The script writes a PDF to `%TEMP%\callosum-docx-qa`. Open the PDF and inspect every page.
For a PNG review, use Poppler's `pdftoppm` if available:

```powershell
pdftoppm -png -r 150 <rendered.pdf> <output-prefix>
```

Record the command, LibreOffice version, page count, and visual outcome in the relevant
handover/findings record. Do not commit generated PDFs or PNGs.

## 2026-07-16 verification

`data/demo/messy_operational_risk_memo.docx` was rendered with LibreOffice 26.2.4 to a
one-page PDF and then inspected as a 150-DPI PNG. The title, date/source-quality line,
section heading, and body text were readable with no clipping, overlap, or unexpected page
break. The fixture retains its deliberate content limitation: the memo describes an
OCR-cleaned source with a missing table row; this is test data, not a rendering defect.
