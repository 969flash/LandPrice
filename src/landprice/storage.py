"""표준 스키마 정의, Parquet 파티션 기록, 스윕 체크포인트.

파티션 구조: data/parquet/individual/stdr_year=YYYY/sgg=XXXXX.parquet
자연 키: (pnu, stdr_year, stdr_month)
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .config import CHECKPOINT_DB, INDIVIDUAL_DIR

SCHEMA = pa.schema(
    [
        ("pnu", pa.string()),
        ("stdr_year", pa.int16()),
        ("stdr_month", pa.int8()),
        ("price_per_m2", pa.int64()),
        ("pblntf_de", pa.string()),      # 공시일자 (출처 제공 시, YYYYMMDD 등 원문 유지)
        ("std_land_yn", pa.bool_()),     # 표준지 여부
        ("source", pa.string()),
        ("collected_at", pa.date32()),
    ]
)


def rows_to_table(rows: list[dict], source: str) -> pa.Table:
    """정규화된 dict 목록 → Arrow Table (스키마 강제)."""
    today = dt.date.today()
    cols: dict[str, list] = {name: [] for name in SCHEMA.names}
    for r in rows:
        cols["pnu"].append(str(r["pnu"]))
        cols["stdr_year"].append(int(r["stdr_year"]))
        cols["stdr_month"].append(int(r.get("stdr_month") or 1))
        cols["price_per_m2"].append(int(r["price_per_m2"]))
        cols["pblntf_de"].append(r.get("pblntf_de") or None)
        std = r.get("std_land_yn")
        if isinstance(std, str):
            std = std.strip().upper() in ("Y", "1", "TRUE", "표준지")
        cols["std_land_yn"].append(std)
        cols["source"].append(source)
        cols["collected_at"].append(today)
    return pa.table(cols, schema=SCHEMA)


def normalize_vworld_row(r: dict) -> dict | None:
    """V-World API 응답 행 → 표준 dict. 가격 없는 행은 None."""
    price = str(r.get("pblntfPclnd", "")).strip().replace(",", "")
    pnu = str(r.get("pnu", "")).strip()
    year = str(r.get("stdrYear", "")).strip()
    if not (price and pnu and year):
        return None
    month_s = str(r.get("stdrMt", "") or "1").strip()
    return {
        "pnu": pnu,
        "stdr_year": int(year),
        "stdr_month": int(month_s) if month_s.isdigit() else 1,
        "price_per_m2": int(float(price)),
        "pblntf_de": str(r.get("pblntfDe", "")).strip() or None,
        "std_land_yn": str(r.get("stdLandAt", "")).strip() or None,
        # 스키마엔 없지만 dedup_latest에서 최신 개정본 선택에 사용 (rows_to_table가 무시)
        "_last_updt_dt": str(r.get("lastUpdtDt", "")).strip(),
    }


def dedup_latest(rows: list[dict]) -> list[dict]:
    """(pnu, stdr_year, stdr_month) 키별로 최신 개정본만 남긴다.

    V-World API는 한 필지의 여러 개정 버전을 모두 반환하고, 며칠에 걸친 수집은
    개정 전·후 값을 다 담아 같은 키에 가격이 여러 개 생긴다. lastUpdtDt가 가장 큰
    (가장 최근 수정된) 레코드가 official 값이다. lastUpdtDt 동률이면 마지막 것 유지.
    """
    best: dict[tuple, dict] = {}
    for r in rows:
        key = (r["pnu"], r["stdr_year"], r["stdr_month"])
        cur = best.get(key)
        if cur is None or r.get("_last_updt_dt", "") >= cur.get("_last_updt_dt", ""):
            best[key] = r
    return list(best.values())


def partition_path(year: int, sgg: str, source: str, base: Path = INDIVIDUAL_DIR) -> Path:
    # source를 파일명에 포함 — 출처가 다른 동일 (연도, 시군구) 파티션이 서로 덮어쓰지 않도록
    return base / f"stdr_year={year}" / f"sgg={sgg}-{source}.parquet"


def write_partition(table: pa.Table, year: int, sgg: str, source: str, base: Path = INDIVIDUAL_DIR) -> Path:
    path = partition_path(year, sgg, source, base)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(path)  # os.replace: 대상이 있어도 원자적 덮어쓰기 (윈도우에서 rename은 실패)
    return path


class Checkpoint:
    """(sgg, year) 단위 스윕 진행 상태. 재시작 시 완료 단위 스킵."""

    def __init__(self, db_path: Path = CHECKPOINT_DB) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS sweeps (
                   sgg TEXT NOT NULL,
                   year INTEGER NOT NULL,
                   rows INTEGER NOT NULL,
                   completed_at TEXT NOT NULL,
                   PRIMARY KEY (sgg, year)
               )"""
        )
        self.conn.commit()

    def is_done(self, sgg: str, year: int) -> bool:
        cur = self.conn.execute("SELECT 1 FROM sweeps WHERE sgg=? AND year=?", (sgg, year))
        return cur.fetchone() is not None

    def mark_done(self, sgg: str, year: int, rows: int) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO sweeps VALUES (?, ?, ?, ?)",
            (sgg, year, rows, dt.datetime.now().isoformat(timespec="seconds")),
        )
        self.conn.commit()

    def stats(self) -> list[tuple[int, int, int]]:
        """연도별 (year, 완료 시군구 수, 총 행 수)."""
        cur = self.conn.execute(
            "SELECT year, COUNT(*), SUM(rows) FROM sweeps GROUP BY year ORDER BY year"
        )
        return cur.fetchall()

    def close(self) -> None:
        self.conn.close()
