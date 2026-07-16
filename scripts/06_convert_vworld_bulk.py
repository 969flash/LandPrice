"""V-World 데이터마켓 벌크 CSV (AL_D151_*.zip) → 표준 스키마 Parquet 변환.

파일명 형식: AL_D151_{시도코드}_{기준일YYYYMMDD}.zip (내부 cp949 CSV, 13컬럼 — 컬럼정의서 검증)
수록 내용: 스냅샷당 한 해치 (예: 2026-05-26 스냅샷 = 2026년 1월 기준분) — 2026-07-15 실측.

사용: .venv/bin/python scripts/06_convert_vworld_bulk.py [--mark-done]
  --mark-done: 변환 후 해당 (시군구, 연도) 단위를 체크포인트에 완료 표기 (API 스윕에서 제외)
출력: data/parquet/individual/stdr_year=YYYY/sgg=XXXXX-vworld_bulk.parquet
"""

import argparse
import csv
import io
import zipfile
from collections import defaultdict
from pathlib import Path

from tqdm import tqdm

from landprice import storage
from landprice.config import RAW_DIR, ensure_dirs

BULK_DIR = RAW_DIR / "vworld_bulk"
EXPECTED_HEADER_PREFIX = ["고유번호", "법정동코드", "법정동명", "특수지구분코드"]


def iter_rows(zip_path: Path):
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.file_size == 0 or not info.filename.lower().endswith(".csv"):
                continue
            with z.open(info) as f:
                text = io.TextIOWrapper(f, encoding="cp949", newline="")
                reader = csv.reader(text)
                header = next(reader)
                if [h.strip().lstrip("﻿") for h in header[:4]] != EXPECTED_HEADER_PREFIX:
                    raise RuntimeError(f"{zip_path.name}: 예상과 다른 헤더 {header[:4]} — 컬럼정의서 변경 확인 필요")
                # 0고유번호 6기준연도 7기준월 8공시지가 9공시일자 10표준지여부
                for row in reader:
                    if len(row) < 11 or not row[0].strip() or not row[8].strip():
                        continue
                    yield {
                        "pnu": row[0].strip(),
                        "stdr_year": int(row[6]),
                        "stdr_month": int(row[7] or 1),
                        "price_per_m2": int(float(row[8].replace(",", ""))),
                        "pblntf_de": row[9].strip() or None,
                        "std_land_yn": row[10].strip() or None,
                    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mark-done", action="store_true", help="변환된 (시군구,연도)를 스윕 완료로 표기")
    args = ap.parse_args()

    ensure_dirs()
    zips = sorted(BULK_DIR.glob("AL_D151_*.zip"))
    if not zips:
        raise SystemExit(f"{BULK_DIR} 에 AL_D151_*.zip 없음")

    unit_rows: dict[tuple[int, str], int] = {}
    for zp in tqdm(zips, unit="파일"):
        buckets: dict[tuple[int, str], list[dict]] = defaultdict(list)
        for r in iter_rows(zp):
            buckets[(r["stdr_year"], r["pnu"][:5])].append(r)
        for (year, sgg), rows in buckets.items():
            table = storage.rows_to_table(rows, source="vworld_bulk")
            storage.write_partition(table, year, sgg, source="vworld_bulk")
            unit_rows[(year, sgg)] = unit_rows.get((year, sgg), 0) + len(rows)
        years = sorted({y for y, _ in buckets})
        tqdm.write(f"{zp.name}: {sum(len(v) for v in buckets.values()):,}행, 연도 {years}, 시군구 {len(buckets)}개")

    print(f"총 파티션 {len(unit_rows):,}개")
    if args.mark_done:
        ckpt = storage.Checkpoint()
        marked = kept = 0
        for (year, sgg), n in unit_rows.items():
            if ckpt.is_done(sgg, year):
                kept += 1
            else:
                ckpt.mark_done(sgg, year, n)
                marked += 1
        ckpt.close()
        print(f"체크포인트: 신규 완료 {marked}개, 기존 유지 {kept}개")


if __name__ == "__main__":
    main()
