"""시도 단위 연도별 지가 집계 → 지도용 JSON. 경계 GeoJSON의 name으로 조인."""
import json
import duckdb
from landprice.config import INDIVIDUAL_DIR

con = duckdb.connect()
con.execute("SET memory_limit='6GB'; SET threads=4;")
API = f"read_parquet('{INDIVIDUAL_DIR}/**/*-vworld_api.parquet', hive_partitioning=true)"

# 법정동코드 시도 prefix -> 경계 GeoJSON(2018)의 name (강원 42/51, 전북 45/52 병합)
NAME_CASE = """
  CASE substr(pnu,1,2)
    WHEN '11' THEN '서울특별시' WHEN '26' THEN '부산광역시' WHEN '27' THEN '대구광역시'
    WHEN '28' THEN '인천광역시' WHEN '29' THEN '광주광역시' WHEN '30' THEN '대전광역시'
    WHEN '31' THEN '울산광역시' WHEN '36' THEN '세종특별자치시' WHEN '41' THEN '경기도'
    WHEN '42' THEN '강원도' WHEN '51' THEN '강원도'
    WHEN '43' THEN '충청북도' WHEN '44' THEN '충청남도'
    WHEN '45' THEN '전라북도' WHEN '52' THEN '전라북도'
    WHEN '46' THEN '전라남도' WHEN '47' THEN '경상북도' WHEN '48' THEN '경상남도'
    WHEN '50' THEN '제주특별자치도' ELSE NULL END
"""

rows = con.sql(f"""
  SELECT {NAME_CASE} AS name, stdr_year AS yr,
         COUNT(*) AS parcels,
         ROUND(AVG(price_per_m2) FILTER (WHERE price_per_m2>0)) AS avg_p,
         ROUND(approx_quantile(price_per_m2,0.5) FILTER (WHERE price_per_m2>0)) AS med_p
  FROM {API}
  WHERE stdr_month=1 AND {NAME_CASE} IS NOT NULL
  GROUP BY 1,2 ORDER BY 2,1
""").fetchall()

data = {}
for name, yr, parcels, avg_p, med_p in rows:
    data.setdefault(name, {})[int(yr)] = {
        "n": int(parcels), "avg": int(avg_p or 0), "med": int(med_p or 0)
    }
years = sorted({int(r[1]) for r in rows})
print(json.dumps({"years": years, "sido": data}, ensure_ascii=False))
