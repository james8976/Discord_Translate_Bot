# PongPong Research — 從 Oracle VM 拉回實驗結果到本機
# 用法：
#   cd bot
#   powershell -ExecutionPolicy Bypass -File research/fetch_results.ps1
#   powershell -ExecutionPolicy Bypass -File research/fetch_results.ps1 -OpenReport

param(
    [string]$VmHost = "155.248.173.141",
    [string]$VmUser = "ubuntu",
    [string]$RemoteBotDir = "~/bot",
    [switch]$OpenReport
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BotDir = Split-Path -Parent $ScriptDir
$LocalRunsDir = Join-Path $BotDir "research\results\runs"
$LocalLatestDir = Join-Path $BotDir "research\results\latest"

New-Item -ItemType Directory -Force -Path $LocalRunsDir | Out-Null

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  PongPong — 從 Oracle VM 拉回實驗結果" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  VM:     ${VmUser}@${VmHost}"
Write-Host "  遠端:   ${RemoteBotDir}/research/results/"
Write-Host "  本機:   $LocalRunsDir"
Write-Host ""

# 測試 SSH 連線
Write-Host "[1/3] 測試 SSH 連線..." -ForegroundColor Yellow
ssh -o ConnectTimeout=10 -o BatchMode=yes "${VmUser}@${VmHost}" "echo OK" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "  SSH 連線失敗。請確認：" -ForegroundColor Red
    Write-Host "  1. VM 已開機"
    Write-Host "  2. 已設定 SSH 金鑰（ssh ${VmUser}@${VmHost} 可登入）"
    Write-Host "  3. Oracle 使用者可能是 ubuntu 或 opc，可用 -VmUser opc 指定"
    Write-Host ""
    Write-Host "  先手動連線測試：" -ForegroundColor Yellow
    Write-Host "    ssh ${VmUser}@${VmHost}"
    exit 1
}
Write-Host "  SSH 連線成功" -ForegroundColor Green

# 取得最新 run_id
Write-Host "[2/3] 取得最新實驗 Run ID..." -ForegroundColor Yellow
$RemoteRuns = "${RemoteBotDir}/research/results/runs"
$LatestRun = ssh "${VmUser}@${VmHost}" "ls -1t ${RemoteRuns} 2>/dev/null | head -1"
if (-not $LatestRun -or $LatestRun -eq "") {
    Write-Host "  遠端尚無實驗結果。請先在 VM 上執行：" -ForegroundColor Red
    Write-Host "    cd ~/bot && python research/run_experiment.py --small"
    exit 1
}
$LatestRun = $LatestRun.Trim()
Write-Host "  最新 Run: $LatestRun" -ForegroundColor Green

# SCP 拉回
Write-Host "[3/3] 下載結果..." -ForegroundColor Yellow
$LocalRunDir = Join-Path $LocalRunsDir $LatestRun
New-Item -ItemType Directory -Force -Path $LocalRunDir | Out-Null

scp -r "${VmUser}@${VmHost}:${RemoteRuns}/${LatestRun}/*" "$LocalRunDir/"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  SCP 下載失敗" -ForegroundColor Red
    exit 1
}

# 同步 latest
if (Test-Path $LocalLatestDir) {
    Remove-Item -Recurse -Force $LocalLatestDir
}
Copy-Item -Recurse -Force $LocalRunDir $LocalLatestDir

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  下載完成！" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  本機資料夾:  $LocalRunDir"
Write-Host "  Markdown:    $(Join-Path $LocalRunDir 'SUMMARY.md')"
Write-Host "  HTML 報告:   $(Join-Path $LocalRunDir 'SUMMARY.html')"
Write-Host ""
Write-Host "  開啟總覽報告：" -ForegroundColor Yellow
Write-Host "    Start-Process `"$(Join-Path $LocalRunDir 'SUMMARY.html')`""
Write-Host ""

if ($OpenReport) {
    $SummaryHtml = Join-Path $LocalRunDir "SUMMARY.html"
    if (Test-Path $SummaryHtml) {
        Start-Process $SummaryHtml
    }
}
