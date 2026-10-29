#Requires -Version 5.1
<#
.SYNOPSIS
  Start the GenStudio backend (which auto-starts the ComfyUI engine).
#>
$Root = Split-Path $PSScriptRoot -Parent
$BackendPy = "$Root\backend\.venv\Scripts\python.exe"

if (-not (Test-Path $BackendPy)) {
  Write-Host "Backend venv not found. Run .\scripts\install.ps1 first." -ForegroundColor Red
  exit 1
}

# LAN access: bind to all interfaces only when enabled in settings
$BindHost = "127.0.0.1"
$SettingsFile = "$Root\data\settings.json"
if (Test-Path $SettingsFile) {
  try {
    $cfg = Get-Content $SettingsFile -Raw | ConvertFrom-Json
    if ($cfg.lan_access -eq $true) { $BindHost = "0.0.0.0" }
  } catch {}
}

# Set PYTHONPATH so 'app' is importable
$env:PYTHONPATH = "$Root\backend"

Write-Host "Starting GenStudio backend at http://localhost:8700 (bind $BindHost) …" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

# Open browser after a brief delay
Start-Job -ScriptBlock {
  Start-Sleep 4
  Start-Process "http://localhost:8700"
} | Out-Null

& $BackendPy -m uvicorn app.main:app `
  --host $BindHost `
  --port 8700 `
  --log-level info
