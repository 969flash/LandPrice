"""구축 데이터 품질 검증.

1. 완전성: 연도×시도별 행 수, 빈 파티션 플래그
2. 분포: 가격 0/음수/극단값, PNU 형식
3. 교차검증 (--cross, VWORLD_KEY 필요): 서울 벌크 vs API 표본 대조

사용: .venv/bin/python scripts/05_validate.py [--cross --sample 200]
"""

import argparse
import random

import duckdb

from landprice.config import INDIVIDUAL_DIR, VWORLD_DOMAIN, VWORLD_KEY
from landprice.vworld import VWorldClient

GLOB = str(INDIVIDUAL_DIR / "**" / "*.parquet")


def summary(con: duckdb.DuckDBPyConnection) -> None:
    print("=== 연도별 요약 ===")
    print(
        con.sql(f"""
        SELECT stdr_year,
               COUNT(*)                            AS rows,
               COUNT(DISTINCT substr(pnu, 1, 2))   AS n_sido,
               SUM(CASE WHEN stdr_month = 7 THEN 1 ELSE 0 END) AS july_rows,
               MIN(price_per_m2)                   AS min_price,
               ROUND(AVG(price_per_m2))            AS avg_price,
               MAX(price_per_m2)                   AS max_price
        FROM read_parquet('{GLOB}', hive_partitioning=true)
        GROUP BY 1 ORDER BY 1
        """)
    )
    print("\n=== 형식 이상 ===")
    print(
        con.sql(f"""
        SELECT
            SUM(CASE WHEN length(pnu) < 19 THEN 1 ELSE 0 END)  AS pnu_too_short,
            SUM(CASE WHEN price_per_m2 <= 0 THEN 1 ELSE 0 END) AS nonpositive_price,
            SUM(CASE WHEN stdr_month NOT IN (1, 7) THEN 1 ELSE 0 END) AS odd_month
        FROM read_parquet('{GLOB}', hive_partitioning=true)
        """)
    )
    print("\n=== 출처 간 중복 키 (pnu, year, month) 불일치 가격 ===")
    print(
        con.sql(f"""
        WITH t AS (SELECT * FROM read_parquet('{GLOB}', hive_partitioning=true))
        SELECT COUNT(*) AS conflicting_keys FROM (
            SELECT pnu, stdr_year, stdr_month
            FROM t GROUP BY 1, 2, 3
            HAVING COUNT(DISTINCT price_per_m2) > 1
        )
        """)
    )


def cross_check(con: duckdb.DuckDBPyConnection, n_sample: int) -> None:
    """서울 벌크 표본을 API로 재조회해 가격 일치율 측정."""
    rows = con.sql(f"""
        SELECT pnu, stdr_year, price_per_m2
        FROM read_parquet('{GLOB}', hive_partitioning=true)
        WHERE source = 'seoul_opendata' AND stdr_month = 1
        USING SAMPLE {n_sample} ROWS
    """).fetchall()
    if not rows:
        print("교차검증: seoul_opendata 데이터 없음 — 02/03 스크립트 먼저 실행")
        return
    client = VWorldClient(VWORLD_KEY, domain=VWORLD_DOMAIN, rps=5.0)
    match = mismatch = missing = 0
    for pnu, year, price in rows:
        api_rows, _ = client.fetch_page(pnu, year, 1)
        api_price = None
        for r in api_rows:
            if str(r.get("pnu")) == pnu and str(r.get("stdrMt", "1")).strip().lstrip("0") in ("1", ""):
                api_price = int(float(str(r["pblntfPclnd"]).replace(",", "")))
                break
        if api_price is None:
            missing += 1
        elif api_price == price:
            match += 1
        else:
            mismatch += 1
            print(f"  불일치: {pnu} {year} 벌크={price:,} API={api_price:,}")
    total = len(rows)
    print(f"교차검증 {total}건: 일치 {match} / 불일치 {mismatch} / API 미존재 {missing} "
          f"(일치율 {match / total * 100:.1f}%)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cross", action="store_true", help="서울 벌크 vs API 교차검증 (키 필요)")
    ap.add_argument("--sample", type=int, default=200)
    args = ap.parse_args()

    random.seed(42)
    con = duckdb.connect()
    summary(con)
    if args.cross:
        print()
        cross_check(con, args.sample)


if __name__ == "__main__":
    main()
