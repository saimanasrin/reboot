# Q-Chain AI - one-command local setup + run (Windows PowerShell).
#   .\start.ps1           -> install deps (first run), seed demo data (first run), build UI, serve on http://127.0.0.1:8000
#   .\start.ps1 -Dev      -> API on :8000 + Vite dev server on :5173 (hot reload)
#   .\start.ps1 -Reseed   -> rebuild the synthetic demo database
param([switch]$Dev, [switch]$Reseed)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Push-Location "$root\backend"
if (-not (Test-Path .venv)) {
    Write-Host "Creating Python venv..."
    py -3.12 -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.txt
}
if ($Reseed -or -not (Test-Path qchain.db)) {
    Write-Host "Seeding synthetic demo data (1,284 shipments, ~2-3 min)..."
    .venv\Scripts\python.exe -m app.seed
}
Pop-Location

Push-Location "$root\frontend"
if (-not (Test-Path node_modules)) { npm install }
if ($Dev) {
    Start-Process -NoNewWindow -FilePath "$root\backend\.venv\Scripts\python.exe" -ArgumentList "-m uvicorn app.main:app --reload --port 8000" -WorkingDirectory "$root\backend"
    Write-Host "Open http://localhost:5173"
    npm run dev
} else {
    npm run build
    Pop-Location
    Write-Host "Open http://127.0.0.1:8000"
    Push-Location "$root\backend"
    .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
}
Pop-Location
