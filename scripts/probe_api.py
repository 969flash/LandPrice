"""V-World API 키 발급 직후 1회 실행하는 검증 스크립트.

확인 항목 (docs/DATA_SOURCES.md '미검증 항목'):
1. stdrYear 소급 하한 — 1990년대 데이터가 실제로 반환되는가
2. 정상 응답의 행 목록 키 구조 (방어적 파서 검증)
3. 7월(추가공시) 레코드 존재 여부
4. 표준지공시지가 API 동작

사용: .venv/bin/python scripts/probe_api.py
"""

import json

from landprice.config import VWORLD_DOMAIN, VWORLD_KEY
from landprice.vworld import INDVD_URL, REFER_URL, VWorldClient

PROBE_BJD = "1111010100"  # 서울 종로구 청운동
PROBE_YEARS = [1989, 1990, 1991, 1995, 2000, 2005, 2012, 2020, 2026]


def main() -> None:
    client = VWorldClient(VWORLD_KEY, domain=VWORLD_DOMAIN, rps=2.0)

    print("=== 원시 응답 구조 (2026년, 1페이지 2행) ===")
    payload = client._get(INDVD_URL, {"pnu": PROBE_BJD, "stdrYear": "2026", "numOfRows": 2, "pageNo": 1})
    print(json.dumps(payload, ensure_ascii=False, indent=2)[:2000])

    print("\n=== 연도별 소급 범위 (종로구 청운동) ===")
    for year in PROBE_YEARS:
        try:
            rows, total = client.fetch_page(PROBE_BJD, year, 1)
            sample = rows[0] if rows else {}
            print(f"{year}: totalCount={total:>7,}  sample_price={sample.get('pblntfPclnd', '-')} "
                  f"stdrMt={sample.get('stdrMt', '-')}")
        except Exception as exc:
            print(f"{year}: 오류 — {exc}")

    print("\n=== 7월 추가공시 레코드 존재 확인 (연도 미지정 조회에서 stdrMt 분포) ===")
    months: dict[str, int] = {}
    for i, row in enumerate(client.iter_parcels(PROBE_BJD)):
        months[str(row.get("stdrMt", "?")).strip()] = months.get(str(row.get("stdrMt", "?")).strip(), 0) + 1
        if i >= 4999:
            break
    print(f"stdrMt 분포 (최대 5000행): {months}")

    print("\n=== 표준지공시지가 API (getReferLandPriceAttr) ===")
    for year in (1990, 2000, 2026):
        try:
            payload = client._get(REFER_URL, {"ldCode": PROBE_BJD, "stdrYear": str(year), "numOfRows": 2, "pageNo": 1})
            rows, total, code = client._unwrap(payload)
            print(f"{year}: totalCount={total}, resultCode={code}, sample={rows[0] if rows else '-'}")
        except Exception as exc:
            print(f"{year}: 오류 — {exc}")


if __name__ == "__main__":
    main()
