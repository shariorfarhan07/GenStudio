#Requires -Version 5.1
<#
.SYNOPSIS
  Start both backend (with hot-reload) and frontend (Vite dev server) for development.
#>
$Root = Split-Path $PSScriptRoot -Parent
$BackendPy = "$Root\backend\.venv\Scripts\python.exe"

# Backend
$env:PYTHONPATH = "$Root\backend"
$backendJob = Start-Job -Name "genstudio-backend" -ScriptBlock {
  param($py, $root)
  $env:PYTHONPATH = "$root\backend"
  & $py -m uvicorn app.main:app --host 127.0.0.1 --port 8700 --reload --reload-dir "$root\backend\app"
} -ArgumentList $BackendPy, $Root

# Frontend dev
$frontendJob = Start-Job -Name "genstudio-frontend" -ScriptBlock {
  param($root)
  Set-Location "$root\frontend"
  npm run dev
} -ArgumentList $Root

Write-Host "Backend:  http://localhost:8700" -ForegroundColor Cyan
Write-Host "Frontend: http://localhost:5173" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop both." -ForegroundColor DarkGray

try {
  while ($true) {
    $backendJob, $frontendJob | Receive-Job
    Start-Sleep 2
  }
} finally {
  $backendJob, $frontendJob | Stop-Job
  $backendJob, $frontendJob | Remove-Job
}
