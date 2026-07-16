"""수집 진행 현황판.

사용:
    .venv/bin/python scripts/status.py          # 현재 상태 1회 출력
    .venv/bin/python scripts/status.py --live   # 5초마다 자동 갱신 (Ctrl+C로 종료)
"""

import argparse
import datetime as dt
import os
import sqlite3
import subprocess
import time

from landprice import bjd
from landprice.config import CHECKPOINT_DB

YEARS = 37  # 1990~2026


def active_sggs() -> set[str]:
    # 스윕 범위와 동일: 폐지 코드 포함 (전북·전남·광주 등 과거 데이터가 폐지 코드에 있음)
    return set(bjd.group_by_sgg(bjd.load_leaf_codes(include_abolished=True)))


def sweep_running() -> bool:
    r = subprocess.run(["pgrep", "-f", "04_sweep_vworld_api"], capture_output=True)
    return r.returncode == 0


def report(sggs: set[str], total: int) -> str:
    conn = sqlite3.connect(CHECKPOINT_DB)
    marks = ",".join("?" * len(sggs))
    done, rows = conn.execute(
        f"SELECT COUNT(*), COALESCE(SUM(rows),0) FROM sweeps WHERE sgg IN ({marks})", tuple(sggs)
    ).fetchone()

    # 최근 30분 완료 속도로 남은 시간 추정
    cutoff = (dt.datetime.now() - dt.timedelta(minutes=30)).isoformat(timespec="seconds")
    recent, recent_rows = conn.execute(
        f"SELECT COUNT(*), COALESCE(SUM(rows),0) FROM sweeps WHERE completed_at >= ? AND sgg IN ({marks})",
        (cutoff, *sggs),
    ).fetchone()
    conn.close()

    pct = done / total * 100
    bar = "█" * int(pct // 2.5) + "░" * (40 - int(pct // 2.5))
    lines = [
        f"수집 프로그램: {'🟢 실행 중' if sweep_running() else '🔴 멈춤 (재실행하면 이어서 진행됨)'}",
        f"진행률: [{bar}] {pct:.1f}%",
        f"완료: {done:,} / {total:,} (시군구×연도 단위)",
        f"수집된 가격 기록: {rows:,}행",
    ]
    if recent > 0:
        per_hour = recent * 2  # 30분치 × 2
        eta_h = (total - done) / per_hour
        finish = dt.datetime.now() + dt.timedelta(hours=eta_h)
        lines += [
            f"최근 30분 속도: 단위 {recent:,}개, {recent_rows:,}행",
            f"예상 완료: 약 {eta_h:.1f}시간 뒤 ({finish.strftime('%m월 %d일 %H시 %M분')}경)",
        ]
    lines.append(f"(기준 시각 {dt.datetime.now().strftime('%H:%M:%S')})")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="5초마다 자동 갱신")
    args = ap.parse_args()

    sggs = active_sggs()
    total = len(sggs) * YEARS
    if not args.live:
        print(report(sggs, total))
        return
    try:
        while True:
            os.system("clear")
            print("=== 공시지가 수집 현황 (Ctrl+C로 종료) ===\n")
            print(report(sggs, total))
            time.sleep(5)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
