"""서울 벌크 ZIP → 표준 스키마 Parquet 파티션 변환.

사용: .venv/bin/python scripts/03_convert_seoul.py [--years 1990-2026]
출력: data/parquet/individual/stdr_year=YYYY/sgg=XXXXX.parquet (source=seoul_opendata)
"""

import argparse
from collections import defaultdict

from tqdm import tqdm

from landprice import seoul, storage
from landprice.config import RAW_SEOUL_DIR, ensure_dirs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", help="예: 1990-2000 (기본: raw에 있는 전체)")
    args = ap.parse_args()

    ensure_dirs()
    zips = sorted(RAW_SEOUL_DIR.glob("공시지가_*년.zip"))
    if args.years:
        lo, hi = (args.years.split("-") + [args.years])[:2]
        keep = set(range(int(lo), int(hi) + 1))
        zips = [z for z in zips if int(z.stem.split("_")[1][:4]) in keep]
    if not zips:
        raise SystemExit("raw 파일 없음 — 먼저 02_download_seoul_bulk.py 실행")

    for zip_path in tqdm(zips, unit="파일"):
        # (year, sgg)별로 행을 모아 파티션 기록
        buckets: dict[tuple[int, str], list[dict]] = defaultdict(list)
        n = 0
        for row in seoul.iter_rows(zip_path):
            buckets[(row["stdr_year"], row["pnu"][:5])].append(row)
            n += 1
        for (year, sgg), rows in buckets.items():
            table = storage.rows_to_table(rows, source="seoul_opendata")
            storage.write_partition(table, year, sgg, source="seoul_opendata")
        tqdm.write(f"{zip_path.name}: {n:,}행 → 파티션 {len(buckets)}개")


if __name__ == "__main__":
    main()
