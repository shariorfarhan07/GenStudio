#Requires -Version 5.1
<#
.SYNOPSIS
  Smoke-test suite: submit one minimal job per installed pipeline, verify output.
#>
$Root = Split-Path $PSScriptRoot -Parent
$BackendUrl = "http://localhost:8700"
$Results = @()

function Invoke-Api([string]$Method, [string]$Path, [hashtable]$Body = $null) {
  $uri = "$BackendUrl$Path"
  if ($Body) {
    $json = $Body | ConvertTo-Json -Depth 10
    return Invoke-RestMethod -Method $Method -Uri $uri -Body $json -ContentType "application/json"
  }
  return Invoke-RestMethod -Method $Method -Uri $uri
}

function Write-Result([string]$Name, [bool]$Pass, [string]$Detail = "") {
  if ($Pass) {
    Write-Host "  PASS  $Name" -ForegroundColor Green
  } else {
    Write-Host "  FAIL  $Name  — $Detail" -ForegroundColor Red
  }
  $script:Results += [pscustomobject]@{ Name = $Name; Pass = $Pass; Detail = $Detail }
}

Write-Host "`nGenStudio Smoke Suite" -ForegroundColor Cyan
Write-Host "Backend: $BackendUrl`n"

# 1. Health check
try {
  $sys = Invoke-Api GET "/api/system"
  Write-Result "API health" $true
  Write-Host "    Engine: $($sys.engine_status)  GPU: $($sys.gpu.name)" -ForegroundColor DarkGray
} catch {
  Write-Result "API health" $false "Cannot reach $BackendUrl — start the backend first"
  exit 1
}

# 2. Pipelines
$pipelines = Invoke-Api GET "/api/pipelines"
Write-Host "  Loaded $($pipelines.Count) pipelines" -ForegroundColor DarkGray
$available = $pipelines | Where-Object { $_.available }
Write-Host "  Available: $($available.Count)" -ForegroundColor DarkGray

# 3. Test each available pipeline
foreach ($p in $available) {
  $testName = "Pipeline: $($p.id)"
  $params = @{ prompt = "a minimal smoke test image, simple"; seed = 12345 }

  # Add _tier = smallest tier
  $tiers = ($p.tiers | Get-Member -MemberType NoteProperty).Name
  if ($tiers.Count -gt 0) {
    $params["_tier"] = $tiers[-1]   # last = smallest
  }

  # Submit job
  try {
    $job = Invoke-Api POST "/api/jobs" @{ pipeline_id = $p.id; params = $params }
    $jobId = $job.job_ids[0]
  } catch {
    Write-Result $testName $false "Submit failed: $_"
    continue
  }

  # Wait up to 10 min
  $deadline = (Get-Date).AddMinutes(10)
  $status = "queued"
  while ($status -notin ("done", "failed", "cancelled") -and (Get-Date) -lt $deadline) {
    Start-Sleep 5
    $j = Invoke-Api GET "/api/jobs/$jobId"
    $status = $j.status
    Write-Host "    [$($p.id)] $status $($j.progress)%" -ForegroundColor DarkGray
  }

  if ($status -eq "done") {
    # Verify asset exists
    $assets = Invoke-Api GET "/api/assets?page=1"
    $asset = $assets | Where-Object { $_.job_id -eq $jobId } | Select-Object -First 1
    if ($asset) {
      Write-Result $testName $true "$($asset.kind) $($asset.width)x$($asset.height)"
    } else {
      Write-Result $testName $false "Job done but no asset found"
    }
  } else {
    $j = Invoke-Api GET "/api/jobs/$jobId"
    Write-Result $testName $false "Final status: $status — $($j.error)"
  }
}

# Summary
$passed = ($Results | Where-Object { $_.Pass }).Count
$failed = ($Results | Where-Object { -not $_.Pass }).Count
Write-Host "`n━━━ Smoke suite: $passed passed, $failed failed ━━━" -ForegroundColor $(if ($failed -eq 0) { "Green" } else { "Red" })

if ($failed -gt 0) { exit 1 }
