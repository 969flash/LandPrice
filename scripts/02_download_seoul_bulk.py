"""서울 열린데이터광장 개별공시지가 연도별 ZIP 일괄 다운로드 (1990~최신).

사용: .venv/bin/python scripts/02_download_seoul_bulk.py [--years 1990-2000]
무인증 경로 — 즉시 실행 가능.
"""

import argparse

from tqdm import tqdm

from landprice import seoul
from landprice.config import ensure_dirs


def parse_years(spec: str | None, available: list[int]) -> list[int]:
    if not spec:
        return available
    out: set[int] = set()
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return sorted(out & set(available))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", help="예: 1990-2000 또는 1990,1995,2020 (기본: 전체)")
    args = ap.parse_args()

    ensure_dirs()
    mapping = seoul.scrape_year_seq_map()
    years = parse_years(args.years, sorted(mapping))
    print(f"대상 연도: {years[0]}~{years[-1]} ({len(years)}개)")

    for year in tqdm(years, unit="년"):
        path = seoul.download_year(year, mapping[year])
        tqdm.write(f"{year}: {path.name} ({path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
