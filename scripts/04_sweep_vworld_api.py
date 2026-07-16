"""V-World API 전국 스윕: 법정동 leaf 코드 × 연도 → Parquet 파티션.

사용:
    .venv/bin/python scripts/04_sweep_vworld_api.py --years 1990-2026
    .venv/bin/python scripts/04_sweep_vworld_api.py --years 2025 --sgg 11110   # 종로구만
    .venv/bin/python scripts/04_sweep_vworld_api.py --years 1990-2011 --skip-sido 11  # 서울 제외

- 작업 단위 (시군구, 연도): 완료 시 파티션 기록 + SQLite 체크포인트 → 중단 후 재시작 안전.
- VWORLD_KEY 필요 (.env). 기본 8 req/s.
- 서울은 열린데이터광장 벌크가 있으므로 --skip-sido 11 로 제외 가능 (교차검증용으로는 포함 실행).
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor

from tqdm import tqdm

from landprice import bjd, storage
from landprice.config import FIRST_YEAR, VWORLD_DOMAIN, VWORLD_KEY, VWORLD_RPS, ensure_dirs
from landprice.vworld import InvalidKeyError, VWorldClient, VWorldError


def parse_years(spec: str) -> list[int]:
    out: set[int] = set()
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    bad = [y for y in out if y < FIRST_YEAR]
    if bad:
        print(f"경고: {FIRST_YEAR}년 이전({sorted(bad)})은 제도상 데이터가 없습니다 — 제외.")
    return sorted(y for y in out if y >= FIRST_YEAR)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", required=True, help="예: 1990-2026 또는 2020,2021")
    ap.add_argument("--sgg", help="특정 시군구(5자리)만, 쉼표 구분")
    ap.add_argument("--skip-sido", help="제외할 시도(2자리), 쉼표 구분 (예: 11)")
    ap.add_argument("--rps", type=float, default=VWORLD_RPS)
    ap.add_argument("--workers", type=int, default=14, help="법정동 병렬 요청 워커 수 (전역 rps는 유지)")
    # 폐지 코드도 반드시 포함해야 함 (2026-07-15 실측): 행정구역 개편 지역은 재키잉이
    # 지역마다 달라서, 전북(45→52)·전남(46)·광주(29→통합 12) 등은 과거(전남·광주는
    # 현재까지도) 데이터가 폐지 코드 아래에 있음. 현존만 돌면 해당 지역이 통째로 누락됨.
    ap.add_argument("--only-active", action="store_true", help="현존 코드만 (불완전 — 테스트용)")
    args = ap.parse_args()

    ensure_dirs()
    years = parse_years(args.years)
    client = VWorldClient(VWORLD_KEY, domain=VWORLD_DOMAIN, rps=args.rps)

    leaves = bjd.load_leaf_codes(include_abolished=not args.only_active)
    by_sgg = bjd.group_prefixes_by_sgg(leaves)  # 읍면동 8자리 접두어 단위 조회
    sggs = sorted(by_sgg)
    if args.sgg:
        want = set(args.sgg.split(","))
        sggs = [s for s in sggs if s in want]
    if args.skip_sido:
        skip = set(args.skip_sido.split(","))
        sggs = [s for s in sggs if s[:2] not in skip]

    ckpt = storage.Checkpoint()
    units = [(s, y) for y in years for s in sggs if not ckpt.is_done(s, y)]
    print(f"작업 단위: {len(units):,}개 (시군구 {len(sggs)} × 연도 {len(years)}, 완료분 제외)")

    def fetch_prefix(prefix: str, year: int) -> list[dict]:
        out: list[dict] = []
        for raw in client.iter_parcels(prefix, year):
            norm = storage.normalize_vworld_row(raw)
            if norm:
                out.append(norm)
        return out

    failures: list[tuple[str, int, str]] = []
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for sgg, year in tqdm(units, unit="시군구·년"):
                try:
                    rows: list[dict] = []
                    for chunk in pool.map(lambda p: fetch_prefix(p, year), by_sgg[sgg]):
                        rows.extend(chunk)
                except InvalidKeyError:
                    raise
                except VWorldError as exc:
                    # 단위 실패는 기록만 하고 계속 — 체크포인트 미기록이라 재실행 시 자동 재시도
                    failures.append((sgg, year, str(exc)))
                    tqdm.write(f"실패 (재실행 시 재시도): {sgg} {year} — {exc}")
                    continue
                if rows:
                    table = storage.rows_to_table(rows, source="vworld_api")
                    storage.write_partition(table, year, sgg, source="vworld_api")
                ckpt.mark_done(sgg, year, len(rows))
    except InvalidKeyError as exc:
        print(f"\n중단: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print("\n사용자 중단 — 체크포인트 저장됨. 같은 명령으로 재시작하면 이어서 실행.")
    finally:
        for year, n_sgg, n_rows in ckpt.stats():
            print(f"  {year}: 시군구 {n_sgg}개 완료, {n_rows or 0:,}행")
        if failures:
            print(f"실패 단위 {len(failures)}개 — 같은 명령 재실행으로 재시도 가능")
        ckpt.close()
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
