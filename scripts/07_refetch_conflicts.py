"""윈도우 데이터의 가격 충돌 필지를 API로 재조회해 최신본(lastUpdtDt 최대) 값 확정.

배경: V-World API는 한 필지의 여러 개정 버전을 모두 반환한다 (stdrMt '01' vs '1' 등
형식 차이로 구분되며, 진짜 구분자는 lastUpdtDt). 수집이 며칠에 걸쳐 돌면 개정 전·후
값이 모두 저장돼 (pnu, 연도, 월) 키에 가격이 2개 이상 생긴다. 최신 lastUpdtDt가 official.

우리 저장 스키마는 lastUpdtDt를 안 남기므로, 충돌 필지만 재조회해 확정한다.
출력: data/parquet/overrides/conflict_authoritative.parquet
"""

import pandas as pd

from landprice.config import VWORLD_KEY, PARQUET_DIR
from landprice.vworld import VWorldClient

# 충돌키는 미리 추출해 저장 (603M행 재스캔은 메모리 부담 → 파일 재사용)
CONFLICT_KEYS = PARQUET_DIR / "overrides" / "conflict_keys.parquet"


def main() -> None:
    conf = pd.read_parquet(CONFLICT_KEYS)  # columns: stdr_year, pnu, bjd
    conflict_pnus = set(conf["pnu"])
    dong_years = sorted(set(zip(conf["bjd"], conf["stdr_year"])))
    print(f"충돌 필지 {len(conflict_pnus):,}개, 재조회 대상 (법정동,연도) {len(dong_years):,}건")

    client = VWorldClient(VWORLD_KEY, rps=12, max_retries=6)
    # (pnu, year, month) -> (lastUpdtDt, price, pblntf_de, std)
    best: dict[tuple, tuple] = {}
    for i, (bjd, year) in enumerate(dong_years, 1):
        for r in client.iter_parcels(bjd, int(year)):
            pnu = str(r.get("pnu", ""))
            if pnu not in conflict_pnus:
                continue
            price = str(r.get("pblntfPclnd", "")).strip().replace(",", "")
            if not price:
                continue
            month = int(str(r.get("stdrMt", "1")).strip() or 1)
            last = str(r.get("lastUpdtDt", "")).strip()
            key = (pnu, int(year), month)
            if key not in best or last > best[key][0]:
                best[key] = (last, int(float(price)), str(r.get("pblntfDe", "")).strip() or None,
                             str(r.get("stdLandAt", "")).strip() or None)
        if i % 200 == 0:
            print(f"  {i}/{len(dong_years)} 법정동 처리, 확정 {len(best):,}건")

    # 저장
    import pyarrow as pa
    import pyarrow.parquet as pq
    out_dir = PARQUET_DIR / "overrides"
    out_dir.mkdir(parents=True, exist_ok=True)
    tbl = pa.table({
        "pnu": [k[0] for k in best],
        "stdr_year": [k[1] for k in best],
        "stdr_month": [k[2] for k in best],
        "price_per_m2": [v[1] for v in best.values()],
        "pblntf_de": [v[2] for v in best.values()],
        "std_land_yn": [v[3] for v in best.values()],
        "last_updt_dt": [v[0] for v in best.values()],
    })
    path = out_dir / "conflict_authoritative.parquet"
    pq.write_table(tbl, path, compression="zstd")
    print(f"확정값 {tbl.num_rows:,}건 저장 → {path}")


if __name__ == "__main__":
    main()
