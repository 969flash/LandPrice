#!/bin/bash
# 전국 스윕: 실패 단위가 0이 될 때까지 반복 실행 + 감시견(진행 정체 시 자동 재시작).
# - 서버가 간헐적으로 접속을 끊거나(502/RemoteDisconnected) 응답을 정체시키는 경우가 있어,
#   20분간 완료 단위가 없으면 프로세스를 재시작한다 (체크포인트 덕분에 손실 없음).
cd "$(dirname "$0")/.."
DB=data/db/checkpoints.sqlite
STALL_MIN=20
YEARS="${1:-1990-2026}"   # 사용: run_sweep.sh 1990-2011 (기계별 연도 분담)

for i in $(seq 1 40); do
    echo "=== 스윕 패스 $i 시작 (연도 $YEARS): $(date) ==="
    .venv/bin/python scripts/04_sweep_vworld_api.py --years "$YEARS" --rps 12 --workers 8 &
    PY=$!

    # 감시견: 완료 단위 수가 STALL_MIN분간 변하지 않으면 재시작.
    # (완료 시각 기준으로 재면 재시작 직후 과거 시각을 정체로 오판 — 2026-07-17 수정)
    LAST_COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM sweeps" 2>/dev/null || echo 0)
    LAST_CHANGE=$(date "+%s")
    while kill -0 $PY 2>/dev/null; do
        sleep 120
        COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM sweeps" 2>/dev/null || echo "$LAST_COUNT")
        NOW=$(date "+%s")
        if [ "$COUNT" != "$LAST_COUNT" ]; then
            LAST_COUNT=$COUNT
            LAST_CHANGE=$NOW
        elif [ $((NOW - LAST_CHANGE)) -gt $((STALL_MIN * 60)) ]; then
            echo "=== 감시견: ${STALL_MIN}분간 진행 없음 → 재시작 ($(date)) ==="
            kill $PY 2>/dev/null
            sleep 5
            kill -9 $PY 2>/dev/null
            break
        fi
    done
    wait $PY
    code=$?

    if [ $code -eq 0 ]; then
        echo "=== 완료 (실패 0): $(date) ==="
        exit 0
    elif [ $code -eq 2 ]; then
        echo "=== 인증키 오류로 중단 ==="
        exit 2
    fi
    echo "=== 패스 $i 종료 (code=$code) — 60초 후 재시도 ==="
    sleep 60
done
echo "=== 40회 반복 후에도 잔존 — 점검 필요 ==="
exit 1
