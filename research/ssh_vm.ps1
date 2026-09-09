# PongPong — 快速 SSH 連線到 Oracle VM
# 用法：
#   powershell -ExecutionPolicy Bypass -File research/ssh_vm.ps1
#   powershell -ExecutionPolicy Bypass -File research/ssh_vm.ps1 -Command "cd ~/bot && python research/run_experiment.py --small"

param(
    [string]$VmHost = "155.248.173.141",
    [string]$VmUser = "ubuntu",
    [string]$Command = ""
)

Write-Host ""
Write-Host "連線到 Oracle VM: ${VmUser}@${VmHost}" -ForegroundColor Cyan
Write-Host ""

if ($Command -ne "") {
    ssh "${VmUser}@${VmHost}" $Command
} else {
    Write-Host "常用指令：" -ForegroundColor Yellow
    Write-Host "  cd ~/bot"
    Write-Host "  python research/run_experiment.py --small          # 四組精簡實驗"
    Write-Host "  python research/run_experiment.py --pair ja-zh     # 只跑中日"
    Write-Host "  ls research/results/runs/                          # 查看結果"
    Write-Host ""
    ssh "${VmUser}@${VmHost}"
}
