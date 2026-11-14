# 端到端流水线：采集 -> 判分 -> 标注表 ->（人工填分）-> 相关性。
#
#   .\run_all.cmd                          # 真实 Dify agent + 真实 judge
#   .\run_all.cmd -RunId B-refactor        # 指定批次名，输出落 output\runs\B-refactor\
#   .\run_all.cmd -Limit 2                 # 只跑前两条任务
#
# 三条来自实际事故的约定（issue #6 / #7）：
#   1. 永不自动加 --mock：mock 分和真分不能进同一份结果；
#   2. 标注表已有内容就不再重建：这一步曾经真的清空过 50 个格子；
#   3. 标注没填就不算相关性：不要产出"全空但 exit 0"的 correlation.md。
param(
    [ValidateSet("scripted", "dify")] [string]$Policy = "dify",
    [string]$RunId = "",
    [int]$Limit = 0
)

$ErrorActionPreference = "Stop"
$Code = $PSScriptRoot                    # repro\code
$Root = Split-Path $Code -Parent         # repro
$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "venv missing: $py  (see README step 2)" }

# Playwright 需要一个可写的临时目录
$env:TEMP = Join-Path $Root ".tmp"
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
$env:PYTHONIOENCODING = "utf-8"

if (-not $RunId) { $RunId = (Get-Date -Format "yyyyMMddTHHmm") + "-" + $Policy }
$RunDir = Join-Path $Root "output\runs\$RunId"
$Traj = Join-Path $RunDir "trajectories"
$Scores = Join-Path $RunDir "scores.json"
$Ann = Join-Path $RunDir "annotations.csv"

Write-Host "== 批次 $RunId ==" -ForegroundColor Yellow
Write-Host "   $RunDir"

Write-Host "== 1/4 采集轨迹 ($Policy)" -ForegroundColor Cyan
$runArgs = @((Join-Path $Code "run_episodes.py"), "--policy", $Policy, "--run-id", $RunId)
if ($Limit -gt 0) { $runArgs += @("--limit", $Limit) }
& $py @runArgs

$failed = @(Get-ChildItem $Traj -Filter "*.failed.json" -ErrorAction SilentlyContinue)
if ($failed.Count -gt 0) {
    Write-Host "   注意：$($failed.Count) 条失败记录，判分时会自动忽略（issue #7）" -ForegroundColor Yellow
}

Write-Host "== 2/4 判分（写入来源指纹）" -ForegroundColor Cyan
& $py (Join-Path $Code "score_trajectories.py") --input $Traj --out $Scores --run-id $RunId

Write-Host "== 3/4 生成标注表" -ForegroundColor Cyan
& $py (Join-Path $Code "make_annotation_sheet.py") --input $Traj --out $Ann

Write-Host "== 4/4 相关性" -ForegroundColor Cyan
$filled = [int](& $py -c "import csv,sys;r=list(csv.DictReader(open(sys.argv[1],encoding='utf-8-sig')));d=['backtrack_and_explore','task_decomposition','observation_reading','self_verification','objective_quality'];print(sum(1 for x in r for k in d if (x.get(k) or '').strip()))" $Ann)
if ($filled -eq 0) {
    Write-Host ""
    Write-Host "标注表还是空的，跳过相关性计算。" -ForegroundColor Yellow
    Write-Host "  1) 打开 $Ann 填五列（同一批任务的说明见 $RunDir\annotations.md）"
    Write-Host "  2) 另存为「CSV UTF-8」（不要存成 ANSI/GBK）"
    Write-Host "  3) 再跑："
    Write-Host "     .\.venv\Scripts\python.exe code\correlate.py --scores $Scores --annotations $Ann"
    exit 0
}
Write-Host "   已填 $filled 个格子" -ForegroundColor Green
& $py (Join-Path $Code "correlate.py") --scores $Scores --annotations $Ann
