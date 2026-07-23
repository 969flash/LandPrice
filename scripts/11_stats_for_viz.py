"""웹 시각화용 요약 통계 추출 → JSON.

가격 통계는 vworld_api(전국·전기간 단일 커버리지) 1월 기준·양수 가격으로 계산해
서울 이중소스 중복과 7월 보충분 영향을 배제한다.
"""
import json

import duckdb

from landprice.config import INDIVIDUAL_DIR

con = duckdb.connect()
con.execute("SET memory_limit='6GB'; SET threads=4;")
G = str(INDIVIDUAL_DIR / "**" / "*.parquet")
API = f"read_parquet('{INDIVIDUAL_DIR}/**/*-vworld_api.parquet', hive_partitioning=true)"

SIDO = {
    "11": "서울", "26": "부산", "27": "대구", "28": "인천", "29": "광주",
    "30": "대전", "31": "울산", "36": "세종", "41": "경기", "42": "강원",
    "43": "충북", "44": "충남", "45": "전북", "46": "전남", "47": "경북",
    "48": "경남", "50": "제주", "51": "강원", "52": "전북", "12": "전남광주",
}

out = {}

# 1) 전체 요약
r = con.sql(f"""
  SELECT COUNT(*) AS n_rows, COUNT(DISTINCT stdr_year) AS n_years, MIN(stdr_year) AS mn, MAX(stdr_year) AS mx
  FROM read_parquet('{G}', hive_partitioning=true)
""").fetchone()
out["summary"] = {"rows": r[0], "years": r[1], "min_year": r[2], "max_year": r[3]}

# 2) 연도별: 필지수(vworld_api 1월), 평균/중위 가격(양수)
rows = con.sql(f"""
  SELECT stdr_year,
         COUNT(*) FILTER (WHERE stdr_month=1) AS parcels,
         ROUND(AVG(price_per_m2) FILTER (WHERE stdr_month=1 AND price_per_m2>0)) AS avg_price,
         ROUND(approx_quantile(price_per_m2, 0.5) FILTER (WHERE stdr_month=1 AND price_per_m2>0)) AS med_price
  FROM {API}
  GROUP BY 1 ORDER BY 1
""").fetchall()
out["per_year"] = [{"year": a, "parcels": b, "avg": c, "med": d} for a, b, c, d in rows]

# 3) 시도별(2026, vworld_api 1월): 평균가격·필지수
rows = con.sql(f"""
  SELECT substr(pnu,1,2) AS sido, COUNT(*) AS parcels,
         ROUND(AVG(price_per_m2) FILTER (WHERE price_per_m2>0)) AS avg_price
  FROM {API} WHERE stdr_year=2026 AND stdr_month=1
  GROUP BY 1 ORDER BY 3 DESC
""").fetchall()
out["per_sido_2026"] = [
    {"code": a, "name": SIDO.get(a, a), "parcels": b, "avg": c} for a, b, c in rows
]

# 4) 소스 구성
rows = con.sql(f"SELECT source, COUNT(*) FROM read_parquet('{G}', hive_partitioning=true) GROUP BY 1 ORDER BY 2 DESC").fetchall()
out["sources"] = [{"source": a, "rows": b} for a, b in rows]

# 5) 샘플 필지 시계열 (서울 종로구 청운동)
rows = con.sql(f"""
  SELECT stdr_year, MAX(price_per_m2) AS price
  FROM {API}
  WHERE pnu='1111010100200090004' AND stdr_month=1
  GROUP BY 1 ORDER BY 1
""").fetchall()
out["sample_parcel"] = {"pnu": "1111010100200090004", "label": "서울 종로구 청운동",
                        "series": [{"year": a, "price": b} for a, b in rows]}

print(json.dumps(out, ensure_ascii=False))
