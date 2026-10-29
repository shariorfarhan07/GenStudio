#Requires -Version 5.1
<#
.SYNOPSIS
  Update ComfyUI and custom nodes to latest, run smoke tests, roll back on failure.
#>
$Root = Split-Path $PSScriptRoot -Parent
$engineDir = "$Root\engine"
$comfyDir  = "$engineDir\ComfyUI"
$nodesDir  = "$comfyDir\custom_nodes"
$venvPy    = "$engineDir\venv\Scripts\python.exe"

function Banner([string]$Text) { Write-Host "`n  >> $Text" -ForegroundColor Cyan }

Banner "Capturing current refs"
$prevRefs = @{}
$dirs = @($comfyDir) + (Get-ChildItem $nodesDir -Directory)
foreach ($d in $dirs) {
  $prevRefs[$d.FullName] = (git -C $d.FullName rev-parse HEAD 2>$null)
}

function Rollback {
  Banner "Rolling back"
  foreach ($d in $prevRefs.Keys) {
    $ref = $prevRefs[$d]
    if ($ref) {
      git -C $d checkout $ref --force 2>&1 | Out-Null
      Write-Host "  Rolled back $([System.IO.Path]::GetFileName($d)) to $ref" -ForegroundColor Yellow
    }
  }
}

Banner "Updating ComfyUI"
git -C $comfyDir pull --ff-only
uv pip install --python $venvPy -r "$comfyDir\requirements.txt"

Banner "Updating custom nodes"
foreach ($nodeDir in Get-ChildItem $nodesDir -Directory) {
  Write-Host "  $($nodeDir.Name)" -ForegroundColor DarkGray
  git -C $nodeDir.FullName pull --ff-only 2>&1 | Out-Null
  if (Test-Path "$($nodeDir.FullName)\requirements.txt") {
    uv pip install --python $venvPy -r "$($nodeDir.FullName)\requirements.txt"
  }
}

Banner "Running smoke suite"
try {
  & "$Root\scripts\smoke.ps1"
  $smokeOk = $LASTEXITCODE -eq 0
} catch {
  $smokeOk = $false
}

if (-not $smokeOk) {
  Write-Host "`nSmoke tests failed — rolling back." -ForegroundColor Red
  Rollback
  exit 1
}

Banner "Update complete. All smoke tests passed."
