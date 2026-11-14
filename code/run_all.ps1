# End-to-end pipeline: collect episodes -> score -> annotation sheet -> correlation.
#
#   .\run_all.cmd                 # real Dify agent + real judge (default)
#   .\run_all.cmd -Policy scripted -Mock   # free smoke test, no API calls
#   .\run_all.cmd -Limit 2        # only the first two tasks
param(
    [ValidateSet("scripted", "dify")] [string]$Policy = "dify",
    [switch]$Mock,
    [int]$Limit = 0
)

$ErrorActionPreference = "Stop"
$Code = $PSScriptRoot                    # repro\code
$Root = Split-Path $Code -Parent         # repro
$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "venv missing: $py  (see README step 2)" }

# Playwright needs a writable temp dir
$env:TEMP = Join-Path $Root ".tmp"
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
$env:PYTHONIOENCODING = "utf-8"

Write-Host "== 1/4 collecting episodes ($Policy)" -ForegroundColor Cyan
$runArgs = @((Join-Path $Code "run_episodes.py"), "--policy", $Policy)
if ($Limit -gt 0) { $runArgs += @("--limit", $Limit) }
& $py @runArgs

Write-Host "== 2/4 scoring trajectories" -ForegroundColor Cyan
$scoreArgs = @((Join-Path $Code "score_trajectories.py"))
if ($Mock -or $Policy -eq "scripted") { $scoreArgs += "--mock" }
& $py @scoreArgs

Write-Host "== 3/4 building annotation sheet" -ForegroundColor Cyan
& $py (Join-Path $Code "make_annotation_sheet.py")

Write-Host "== 4/4 correlation (needs a filled annotations.csv)" -ForegroundColor Cyan
& $py (Join-Path $Code "correlate.py")
