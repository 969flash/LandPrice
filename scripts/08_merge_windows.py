"""윈도우 스테이징 데이터(2012~2026)를 맥의 본 데이터셋에 병합.

- 깨끗한 연도(중복 없음): 파일 그대로 복사.
- 중복 연도(2024·2025): (pnu,연도,월) 키로 중복 제거 + 충돌 필지는 재조회 확정값으로 교체.
- 서울(11)은 윈도우에 없으므로 파일명 충돌 없음 (본 데이터셋의 서울 파일 옆에 얹힘).

사용: .venv/bin/python scripts/08_merge_windows.py
"""

import shutil
from pathlib import Path

import polars as pl

from landprice.config import INDIVIDUAL_DIR, PARQUET_DIR

STAGING = PARQUET_DIR.parent / "from_windows" / "parquet"
OVERRIDE = PARQUET_DIR / "overrides" / "conflict_authoritative.parquet"
DIRTY_YEARS = {2024, 2025}  # 다중 개정본 존재 연도 (재조회로 확정)
KEY = ["pnu", "stdr_year", "stdr_month"]


def main() -> None:
    # 정정된 항목은 가격·공시일뿐 (std_land_yn 등은 스테이징 값 유지)
    override = pl.read_parquet(OVERRIDE).select(
        KEY + ["price_per_m2", "pblntf_de"]
    ).with_columns(  # 스테이징 파일과 조인 키 타입 일치
        pl.col("stdr_year").cast(pl.Int16),
        pl.col("stdr_month").cast(pl.Int8),
        pl.col("price_per_m2").cast(pl.Int64),
    )
    print(f"확정값(override) {override.height:,}건 로드")

    copied = merged = 0
    for year_dir in sorted(STAGING.glob("stdr_year=*")):
        year = int(year_dir.name.split("=")[1])
        dest_dir = INDIVIDUAL_DIR / year_dir.name
        dest_dir.mkdir(parents=True, exist_ok=True)

        if year not in DIRTY_YEARS:
            for f in year_dir.glob("*.parquet"):
                shutil.copy2(f, dest_dir / f.name)
                copied += 1
            continue

        ov_y = override.filter(pl.col("stdr_year") == year)
        for f in year_dir.glob("*.parquet"):
            df = pl.read_parquet(f).unique(subset=KEY, keep="first")
            # 충돌 필지 가격을 확정값으로 교체
            df = df.join(ov_y, on=KEY, how="left", suffix="_ov").with_columns(
                pl.coalesce(["price_per_m2_ov", "price_per_m2"]).cast(pl.Int64).alias("price_per_m2"),
                pl.coalesce(["pblntf_de_ov", "pblntf_de"]).alias("pblntf_de"),
            ).drop([c for c in ("price_per_m2_ov", "pblntf_de_ov")])
            df.write_parquet(dest_dir / f.name, compression="zstd")
            merged += 1
        print(f"{year}: 중복제거+확정값 병합, 파일 {len(list(year_dir.glob('*.parquet')))}개")

    print(f"\n완료: 직접복사 {copied:,}개 파일, 중복처리 {merged:,}개 파일")


if __name__ == "__main__":
    main()
