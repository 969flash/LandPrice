"""전 vworld_api 파티션의 중복 제거 + 가격충돌 필지 확정값 적용 (종합 정리).

- 완전중복(값 동일, '01'/'1' 이중형식에서 파생): (pnu,연도,월) 키로 keep-first 제거.
- 가격충돌(값 상이, 다중 개정본): conflict_keys_all.parquet의 필지를 재조회해
  최신 lastUpdtDt 값으로 확정 후 교체.
파일 단위 원자적 덮어쓰기(idempotent) — 중단 후 재실행 안전.

사용: .venv/bin/python scripts/10_dedup_vworld.py
"""
import pandas as pd
import polars as pl

from landprice.config import INDIVIDUAL_DIR, PARQUET_DIR, VWORLD_KEY
from landprice.vworld import VWorldClient

KEY = ["pnu", "stdr_year", "stdr_month"]
COLS = ["pnu", "stdr_year", "stdr_month", "price_per_m2", "pblntf_de",
        "std_land_yn", "source", "collected_at"]


def build_overrides() -> pl.DataFrame:
    conf = pd.read_parquet(PARQUET_DIR / "overrides" / "conflict_keys_all.parquet")
    pnus = set(conf["pnu"])
    dong_years = sorted(set(zip(conf["bjd"], conf["stdr_year"])))
    print(f"충돌 필지 {len(pnus):,}개, 재조회 (법정동,연도) {len(dong_years):,}건")
    client = VWorldClient(VWORLD_KEY, rps=12, max_retries=6)
    best: dict[tuple, tuple] = {}
    for bjd, year in dong_years:
        for r in client.iter_parcels(bjd, int(year)):
            pnu = str(r.get("pnu", ""))
            if pnu not in pnus:
                continue
            price = str(r.get("pblntfPclnd", "")).strip().replace(",", "")
            if not price:
                continue
            month = int(str(r.get("stdrMt", "1")).strip() or 1)
            last = str(r.get("lastUpdtDt", "")).strip()
            key = (pnu, int(year), month)
            if key not in best or last > best[key][0]:
                best[key] = (last, int(float(price)), str(r.get("pblntfDe", "")).strip() or None)
    print(f"확정값 {len(best):,}건")
    return pl.DataFrame({
        "pnu": [k[0] for k in best],
        "stdr_year": [k[1] for k in best],
        "stdr_month": [k[2] for k in best],
        "price_ov": [v[1] for v in best.values()],
        "pblntf_ov": [v[2] for v in best.values()],
    }).with_columns(
        pl.col("stdr_year").cast(pl.Int16),
        pl.col("stdr_month").cast(pl.Int8),
        pl.col("price_ov").cast(pl.Int64),
    )


def main() -> None:
    ov = build_overrides()
    ov.write_parquet(PARQUET_DIR / "overrides" / "conflict_authoritative_all.parquet")

    files = sorted(INDIVIDUAL_DIR.glob("stdr_year=*/*-vworld_api.parquet"))
    print(f"vworld_api 파티션 {len(files):,}개 정리 시작")
    removed = 0
    for i, f in enumerate(files, 1):
        df = pl.read_parquet(f)
        n0 = df.height
        df = df.unique(subset=KEY, keep="first")
        df = df.join(ov, on=KEY, how="left").with_columns(
            pl.coalesce(["price_ov", "price_per_m2"]).cast(pl.Int64).alias("price_per_m2"),
            pl.coalesce(["pblntf_ov", "pblntf_de"]).alias("pblntf_de"),
        ).select(COLS)
        removed += n0 - df.height
        tmp = f.with_suffix(".parquet.tmp")
        df.write_parquet(tmp, compression="zstd")
        tmp.replace(f)
        if i % 1000 == 0:
            print(f"  {i}/{len(files)} 파일, 누적 제거 {removed:,}행")
    print(f"완료: {len(files):,}개 파일, 완전중복 제거 {removed:,}행")


if __name__ == "__main__":
    main()
