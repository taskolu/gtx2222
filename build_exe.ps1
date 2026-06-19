param(
    [string]$PythonVersion = "3.11"
)

$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

$VenvPath = Join-Path $PSScriptRoot ".venv"
if (-not (Test-Path $VenvPath)) {
    py -$PythonVersion -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller pillow openpyxl

$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $PSScriptRoot "browsers"
& ".\.venv\Scripts\python.exe" -m playwright install chromium

& ".\.venv\Scripts\pyinstaller.exe" --noconfirm --clean --onedir --windowed `
    --name APFundingPaymentAutomation `
    --icon icon.ico `
    --add-data "icon.ico;." `
    --add-data "gif.gif;." `
    --add-data "rotating_logo.gif;." `
    --add-data "browsers;browsers" `
    --collect-all PyQt6 `
    --collect-all playwright `
    Main.py

Write-Host ""
Write-Host "Build complete:"
Write-Host (Join-Path $PSScriptRoot "dist\APFundingPaymentAutomation\APFundingPaymentAutomation.exe")
