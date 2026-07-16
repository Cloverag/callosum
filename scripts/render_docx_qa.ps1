[CmdletBinding()]
param(
    [string]$Document,
    [string]$OutputDirectory = (Join-Path $env:TEMP 'callosum-docx-qa'),
    [string]$Soffice = $env:LIBREOFFICE_SOFFICE
)

$ErrorActionPreference = 'Stop'

if (-not $Document) {
    $Document = Join-Path $PSScriptRoot '..\data\demo\messy_operational_risk_memo.docx'
}

if (-not $Soffice) {
    $candidates = @(
        'C:\Program Files\LibreOffice\program\soffice.com',
        'C:\Program Files (x86)\LibreOffice\program\soffice.com'
    )
    $Soffice = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $Soffice) {
    throw 'LibreOffice soffice.com was not found. Install LibreOffice or set LIBREOFFICE_SOFFICE.'
}

$documentPath = (Resolve-Path -LiteralPath $Document).Path
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

& $Soffice --headless --convert-to pdf --outdir $OutputDirectory $documentPath
if ($LASTEXITCODE -ne 0) {
    throw "LibreOffice conversion failed with exit code $LASTEXITCODE."
}

$pdf = Join-Path $OutputDirectory ([System.IO.Path]::GetFileNameWithoutExtension($documentPath) + '.pdf')
if (-not (Test-Path $pdf)) {
    throw "LibreOffice completed but did not produce $pdf."
}

Write-Output "DOCX rendered to: $pdf"
Write-Output 'Visually inspect the PDF (or render it to PNG with pdftoppm) before recording QA complete.'
