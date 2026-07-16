# 전국 스윕 윈도우용 래퍼: 실패 단위 0이 될 때까지 반복 + 감시견 + 잠자기 방지.
# 사용:  powershell -ExecutionPolicy Bypass -File scripts\run_sweep.ps1 -Years 2012-2026
param([string]$Years = "2012-2026")

Set-Location (Split-Path $PSScriptRoot -Parent)
$py = ".venv\Scripts\python.exe"
$stallMin = 20

# 시스템 잠자기 방지 (프로세스 종료 시 자동 해제; 화면은 꺼져도 됨)
Add-Type -Name PW -Namespace Sys -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
[Sys.PW]::SetThreadExecutionState([uint32]"0x80000001") | Out-Null  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED

function Get-LastCompleted {
    & $py -c "import sqlite3,os;db='data/db/checkpoints.sqlite';print(sqlite3.connect(db).execute('SELECT COALESCE(MAX(completed_at),\'\') FROM sweeps').fetchone()[0] if os.path.exists(db) else '')" 2>$null
}

for ($i = 1; $i -le 40; $i++) {
    Write-Host "=== 스윕 패스 $i 시작 (연도 $Years): $(Get-Date) ==="
    # 서울(11)은 맥에서 벌크로 적재 완료 → 제외
    $p = Start-Process -FilePath $py -ArgumentList "scripts/04_sweep_vworld_api.py --years $Years --rps 12 --workers 8 --skip-sido 11" -NoNewWindow -PassThru

    while (-not $p.HasExited) {
        Start-Sleep -Seconds 120
        $last = Get-LastCompleted
        if ($last) {
            try {
                $lastTime = [datetime]::ParseExact($last, "yyyy-MM-ddTHH:mm:ss", $null)
                if (((Get-Date) - $lastTime).TotalMinutes -gt $stallMin) {
                    Write-Host "=== 감시견: ${stallMin}분간 진행 없음 -> 재시작: $(Get-Date) ==="
                    Stop-Process -Id $p.Id -Force
                    break
                }
            } catch {}
        }
    }
    $p.WaitForExit()
    $code = $p.ExitCode

    if ($code -eq 0) { Write-Host "=== 완료 (실패 0): $(Get-Date) ==="; exit 0 }
    if ($code -eq 2) { Write-Host "=== 인증키 오류로 중단 ==="; exit 2 }
    Write-Host "=== 패스 $i 종료 (code=$code) - 60초 후 재시도 ==="
    Start-Sleep -Seconds 60
}
Write-Host "=== 40회 반복 후에도 잔존 - 점검 필요 ==="
exit 1
