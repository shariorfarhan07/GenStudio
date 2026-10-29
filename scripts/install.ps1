#Requires -Version 5.1
<#
.SYNOPSIS
  GenStudio installer – sets up ComfyUI engine, backend, and frontend.
.DESCRIPTION
  Run this once from I:\AI after cloning the repo.
  Prerequisites: Python 3.12, uv, Node 24, git, ffmpeg (all in PATH).
#>
param(
  [switch]$SkipComfyUI,
  [switch]$SkipFrontend,
  [switch]$SkipBackend
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent   # I:\AI

function Banner([string]$Text) {
  Write-Host ""
  Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkCyan
  Write-Host "  $Text" -ForegroundColor Cyan
  Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkCyan
}

function Check-Command([string]$Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    Write-Host "  ✗ $Name not found in PATH" -ForegroundColor Red
    return $false
  }
  Write-Host "  ✓ $Name found" -ForegroundColor Green
  return $true
}

# ── 1. Check prerequisites ─────────────────────────────────────────────────
Banner "Checking prerequisites"
$ok = $true
foreach ($cmd in "python", "uv", "node", "npm", "git", "ffmpeg") {
  if (-not (Check-Command $cmd)) { $ok = $false }
}
if (-not $ok) {
  Write-Host "`nInstall missing tools and re-run install.ps1" -ForegroundColor Red
  exit 1
}

# Check NVIDIA GPU
Banner "GPU check"
try {
  $nvidiaSmi = nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>&1
  Write-Host "  GPU: $nvidiaSmi" -ForegroundColor Green
} catch {
  Write-Host "  ⚠  nvidia-smi not found. The engine requires an NVIDIA GPU." -ForegroundColor Yellow
}

# Check disk space
Banner "Disk space check"
$drive = Split-Path $Root -Qualifier
$disk = Get-PSDrive ($drive.TrimEnd(':')) -ErrorAction SilentlyContinue
if ($disk) {
  $freeGB = [math]::Round($disk.Free / 1GB, 1)
  Write-Host "  $drive free: ${freeGB} GB" -ForegroundColor $(if ($freeGB -gt 50) { "Green" } else { "Yellow" })
  if ($freeGB -lt 50) {
    Write-Host "  ⚠  Less than 50 GB free. The Starter pack alone needs ~45 GB." -ForegroundColor Yellow
  }
}

# ── 2. Create directories ───────────────────────────────────────────────────
Banner "Creating directories"
$dirs = @(
  "$Root\engine",
  "$Root\models\diffusion_models",
  "$Root\models\text_encoders",
  "$Root\models\vae",
  "$Root\models\loras",
  "$Root\models\upscale_models",
  "$Root\models\clip_vision",
  "$Root\models\rife",
  "$Root\data\uploads",
  "$Root\outputs",
  "$Root\logs"
)
foreach ($d in $dirs) {
  New-Item -ItemType Directory -Force $d | Out-Null
  Write-Host "  ✓ $d" -ForegroundColor DarkGray
}

# ── 3. ComfyUI engine ───────────────────────────────────────────────────────
if (-not $SkipComfyUI) {
  Banner "Setting up ComfyUI engine"

  $engineDir = "$Root\engine"
  $comfyDir  = "$engineDir\ComfyUI"

  # Clone ComfyUI
  if (-not (Test-Path "$comfyDir\main.py")) {
    Write-Host "  Cloning ComfyUI…" -ForegroundColor Cyan
    git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git $comfyDir
  } else {
    Write-Host "  ComfyUI already cloned, skipping." -ForegroundColor DarkGray
  }

  # Create engine venv
  $venvPy = "$engineDir\venv\Scripts\python.exe"
  if (-not (Test-Path $venvPy)) {
    Write-Host "  Creating engine venv (Python 3.12)…" -ForegroundColor Cyan
    uv venv "$engineDir\venv" --python 3.12
  }

  # Install PyTorch cu130 (best for Blackwell sm_120 NVFP4)
  Write-Host "  Installing PyTorch cu130 (this may take a while)…" -ForegroundColor Cyan
  try {
    uv pip install --python $venvPy torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130
    if ($LASTEXITCODE -ne 0) { throw 'cu130 install failed' }
    Write-Host "  ✓ PyTorch cu130 installed" -ForegroundColor Green
  } catch {
    Write-Host "  ⚠  cu130 failed, falling back to cu128…" -ForegroundColor Yellow
    uv pip install --python $venvPy torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
    Write-Host "  ✓ PyTorch cu128 installed (fallback)" -ForegroundColor Green
  }

  # Install ComfyUI requirements
  Write-Host "  Installing ComfyUI requirements…" -ForegroundColor Cyan
  uv pip install --python $venvPy -r "$comfyDir\requirements.txt"

  # Custom nodes
  $nodesDir = "$comfyDir\custom_nodes"
  New-Item -ItemType Directory -Force $nodesDir | Out-Null

  $customNodes = @(
    @{ Name = "ComfyUI-GGUF";                Url = "https://github.com/city96/ComfyUI-GGUF.git";                  Ref = "HEAD" },
    @{ Name = "ComfyUI-Frame-Interpolation"; Url = "https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git"; Ref = "HEAD" },
    @{ Name = "ComfyUI-VideoHelperSuite";    Url = "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git";  Ref = "HEAD" }
  )

  foreach ($node in $customNodes) {
    $nodeDir = "$nodesDir\$($node.Name)"
    if (-not (Test-Path $nodeDir)) {
      Write-Host "  Installing custom node: $($node.Name)…" -ForegroundColor Cyan
      git clone --depth 1 $node.Url $nodeDir
    } else {
      Write-Host "  $($node.Name) already installed." -ForegroundColor DarkGray
    }
    $nodeReqs = "$nodeDir\requirements.txt"
    if (Test-Path $nodeReqs) {
      uv pip install --python $venvPy -r $nodeReqs
    }
  }

  # Write extra_model_paths.yaml
  $extraYaml = "$engineDir\extra_model_paths.yaml"
  @"
genstudio:
    base_path: $Root\models
    checkpoints: diffusion_models/
    unet: diffusion_models/
    clip: text_encoders/
    vae: vae/
    loras: loras/
    upscale_models: upscale_models/
    clip_vision: clip_vision/
    ipadapter: clip_vision/
"@ | Set-Content $extraYaml -Encoding utf8
  Write-Host "  ✓ extra_model_paths.yaml written" -ForegroundColor Green
}

# ── 4. Backend ─────────────────────────────────────────────────────────────
if (-not $SkipBackend) {
  Banner "Setting up backend"
  $backendDir = "$Root\backend"
  $bvenvPy = "$backendDir\.venv\Scripts\python.exe"

  if (-not (Test-Path $bvenvPy)) {
    Write-Host "  Creating backend venv…" -ForegroundColor Cyan
    uv venv "$backendDir\.venv" --python 3.12
  }
  Write-Host "  Installing backend dependencies…" -ForegroundColor Cyan
  & "$backendDir\.venv\Scripts\uv.exe" pip install -e "$backendDir" 2>&1 | Out-Null
  uv pip install -e "$backendDir" --python "$backendDir\.venv\Scripts\python.exe" -q
  Write-Host "  ✓ Backend ready" -ForegroundColor Green
}

# ── 5. Frontend ────────────────────────────────────────────────────────────
if (-not $SkipFrontend) {
  Banner "Building frontend"
  Push-Location "$Root\frontend"
  try {
    Write-Host "  npm ci…" -ForegroundColor Cyan
    if (Test-Path package-lock.json) { npm ci --silent } else { npm install --silent }
    Write-Host "  npm run build…" -ForegroundColor Cyan
    npm run build
    Write-Host "  ✓ Frontend built" -ForegroundColor Green
  } finally {
    Pop-Location
  }
}

# ── 6. Pagefile advice ─────────────────────────────────────────────────────
Banner "Pagefile recommendation"
$ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
if ($ram -lt 48) {
  Write-Host "  ⚠  Your system has ${ram} GB RAM. Large video models (Wan A14B, LTX-2)" -ForegroundColor Yellow
  Write-Host "     offload into RAM + pagefile. We recommend a ≥ 48 GB system-managed" -ForegroundColor Yellow
  Write-Host "     pagefile on your fastest SSD for reliable generation." -ForegroundColor Yellow
}

Banner "Installation complete! ✨"
Write-Host "  Start with: .\scripts\start.ps1  or  double-click scripts\start.bat" -ForegroundColor Cyan
Write-Host "  Then open:  http://localhost:8700" -ForegroundColor Cyan
Write-Host ""
