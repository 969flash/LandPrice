"""Parquet 원본에서 원하는 지역·연도를 CSV로 추출 (QGIS 조인용).

필요: pip install duckdb
원본 데이터셋(data/parquet/individual/) 이 있는 곳에서 실행하세요.

예)
    python parquet_to_csv.py --sgg 11110 --year 2026 --out 종로구_2026.csv     # 종로구 2026
    python parquet_to_csv.py --sido 26 --from 2000 --to 2026 --out 부산.csv    # 부산 2000~2026
"""
import argparse
import duckdb

DATASET = "data/parquet/individual/**/*.parquet"  # 필요시 절대경로로 수정


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sgg", help="시군구 법정동코드 5자리 (예: 11110)")
    ap.add_argument("--sido", help="시도 코드 2자리 (예: 26)")
    ap.add_argument("--year", type=int, help="단일 연도")
    ap.add_argument("--from", dest="y0", type=int, default=1990)
    ap.add_argument("--to", dest="y1", type=int, default=2026)
    ap.add_argument("--out", required=True)
    ap.add_argument("--month", type=int, default=1, help="1=정기공시(기본), 7=추가공시, 0=전체")
    a = ap.parse_args()

    conds = []
    if a.year:
        conds.append(f"stdr_year = {a.year}")
    else:
        conds.append(f"stdr_year BETWEEN {a.y0} AND {a.y1}")
    if a.month:
        conds.append(f"stdr_month = {a.month}")
    if a.sgg:
        conds.append(f"substr(pnu,1,5) = '{a.sgg}'")
    elif a.sido:
        conds.append(f"substr(pnu,1,2) = '{a.sido}'")
    where = " AND ".join(conds)

    con = duckdb.connect()
    con.execute("SET threads=4;")
    con.sql(f"""
      COPY (
        SELECT pnu, stdr_year, stdr_month, price_per_m2, pblntf_de, std_land_yn, source
        FROM read_parquet('{DATASET}', hive_partitioning=true)
        WHERE {where}
        ORDER BY pnu, stdr_year, stdr_month
      ) TO '{a.out}' (HEADER, DELIMITER ',');
    """)
    n = con.sql(f"SELECT COUNT(*) FROM read_parquet('{a.out}')").fetchone()[0]
    print(f"저장: {a.out}  ({n:,}행)")


if __name__ == "__main__":
    main()
