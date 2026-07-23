"""전 연도 vworld_api 데이터의 중복·충돌 현황 집계 (메모리 안전, 연도별 순회).

출력: 연도별 총행/고유키/완전중복/가격충돌키. 충돌키 목록은 파일로 저장.
"""
import duckdb
import pandas as pd

from landprice.config import INDIVIDUAL_DIR, PARQUET_DIR

con = duckdb.connect()
con.execute("SET memory_limit='5GB'; SET threads=3;")

conflict_frames = []
print(f"{'연도':>6} {'총행':>12} {'고유키':>12} {'완전중복':>10} {'충돌키':>8}")
for ydir in sorted(INDIVIDUAL_DIR.glob("stdr_year=*")):
    year = int(ydir.name.split("=")[1])
    G = f"{ydir}/*-vworld_api.parquet"
    files = list(ydir.glob("*-vworld_api.parquet"))
    if not files:
        continue
    tot, dist = con.sql(f"""
      WITH t AS (SELECT * FROM read_parquet('{G}'))
      SELECT (SELECT COUNT(*) FROM t), (SELECT COUNT(*) FROM (SELECT DISTINCT pnu,stdr_month FROM t))
    """).fetchone()
    conf = con.sql(f"""
      WITH t AS (SELECT * FROM read_parquet('{G}'))
      SELECT pnu, stdr_month FROM t GROUP BY 1,2 HAVING COUNT(DISTINCT price_per_m2) > 1
    """).df()
    exact_dup = tot - dist - len(conf)  # 완전중복 = 전체중복 - 충돌
    print(f"{year:>6} {tot:>12,} {dist:>12,} {exact_dup:>10,} {len(conf):>8,}")
    if len(conf):
        conf["stdr_year"] = year
        conf["bjd"] = conf["pnu"].str[:10]
        conflict_frames.append(conf)

if conflict_frames:
    allc = pd.concat(conflict_frames, ignore_index=True)
    out = PARQUET_DIR / "overrides" / "conflict_keys_all.parquet"
    allc.to_parquet(out)
    print(f"\n총 충돌키 {len(allc):,}건, 법정동 {allc['bjd'].nunique():,}곳 → {out}")
else:
    print("\n충돌 없음")
