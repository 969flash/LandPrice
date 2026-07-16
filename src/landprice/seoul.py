"""서울 열린데이터광장 '서울시 개별공시지가 정보' (OA-1180) 벌크 다운로드·파싱.

1990~2026년 연도별 ZIP(내부 cp949 CSV)을 무인증으로 제공 — 2026-07-14 실측 검증.
다운로드: POST https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?useCache=false
          (infId=OA-1180, infSeq=3, seq=<연도별 파일번호>)

1990년 파일 실측 스키마 (cp949):
    시도명, 시군구명, 법정동명, 토지코드(=PNU 19자리), 공시지가(원/㎡),
    시군구코드, 법정동코드, 필지구분코드, 필지구분명, 본번, 부번, 기준년도, 기준년월
연도별 헤더 변형에 대비해 키워드 기반으로 컬럼을 매핑한다.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path
from typing import Iterator

import requests

from .config import RAW_SEOUL_DIR

PAGE_URL = "https://data.seoul.go.kr/dataList/OA-1180/F/1/datasetView.do"
DOWNLOAD_URL = "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?useCache=false"

# 2026-07-14 페이지 실측 매핑 (스크레이핑 실패 시 fallback)
FALLBACK_YEAR_SEQ = {
    1990: 32, 1991: 33, 1992: 34, 1993: 35, 1994: 36, 1995: 37, 1996: 38,
    1997: 39, 1998: 40, 1999: 41, 2000: 42, 2001: 43, 2002: 44, 2003: 45,
    2004: 46, 2005: 47, 2006: 48, 2007: 49, 2008: 50, 2009: 51, 2010: 52,
    2011: 53, 2012: 54, 2013: 55, 2014: 56, 2015: 57, 2016: 58, 2017: 59,
    2018: 60, 2019: 61, 2020: 65, 2021: 70, 2022: 77, 2023: 81, 2024: 85,
    2025: 89, 2026: 92,
}


def scrape_year_seq_map(timeout: float = 30.0) -> dict[int, int]:
    """데이터셋 페이지에서 연도→seq 매핑을 재수집. 실패 시 fallback 반환."""
    try:
        html = requests.get(PAGE_URL, timeout=timeout).text
        pairs = re.findall(
            r"downloadFile\('(\d+)'\);\"[^>]*>\s*<span[^>]*>\s*[^<]*?(\d{4})년[^<]*?다운로드",
            html,
        )
        mapping = {int(year): int(seq) for seq, year in pairs}
        if len(mapping) >= len(FALLBACK_YEAR_SEQ):
            return mapping
    except requests.RequestException:
        pass
    return dict(FALLBACK_YEAR_SEQ)


def download_year(year: int, seq: int, dest_dir: Path = RAW_SEOUL_DIR, timeout: float = 600.0) -> Path:
    """연도별 ZIP 다운로드 (이미 있으면 스킵)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"공시지가_{year}년.zip"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    with requests.post(
        DOWNLOAD_URL,
        data={"infId": "OA-1180", "infSeq": "3", "seq": str(seq)},
        stream=True,
        timeout=timeout,
    ) as resp:
        resp.raise_for_status()
        tmp = dest.with_suffix(".part")
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                f.write(chunk)
        tmp.rename(dest)
    with zipfile.ZipFile(dest) as z:  # 무결성 확인
        z.testzip()
    return dest


def _match_column(header: list[str], *keywords: str) -> int:
    for i, col in enumerate(header):
        name = col.strip().lstrip("﻿")
        if any(kw in name for kw in keywords):
            return i
    raise KeyError(f"헤더에서 {keywords} 컬럼을 찾지 못함: {header}")


def iter_rows(zip_path: Path) -> Iterator[dict]:
    """ZIP 내 CSV를 표준화된 dict로 순회.

    반환 키: pnu, stdr_year, stdr_month, price_per_m2
    """
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.file_size == 0:
                continue
            with z.open(info) as f:
                text = io.TextIOWrapper(f, encoding="cp949", errors="strict", newline="")
                reader = csv.reader(text)
                header = next(reader)
                i_pnu = _match_column(header, "토지코드", "고유번호")
                i_price = _match_column(header, "공시지가")
                i_year = _match_column(header, "기준년도", "기준연도")
                i_ym = _match_column(header, "기준년월", "기준월")
                for row in reader:
                    if len(row) <= max(i_pnu, i_price, i_year, i_ym):
                        continue
                    pnu = row[i_pnu].strip()
                    price_s = row[i_price].strip().replace(",", "")
                    if not pnu or not price_s:
                        continue
                    ym = row[i_ym].strip()  # "1990-01-01" | "199001" | "01" 등 변형 대비
                    m = re.search(r"[-./](\d{1,2})(?:[-./]|$)", ym)
                    if m:
                        month = int(m.group(1))
                    elif len(ym) >= 6 and ym.isdigit():
                        month = int(ym[4:6])
                    elif ym.isdigit() and len(ym) <= 2:
                        month = int(ym)
                    else:
                        month = 1
                    yield {
                        "pnu": pnu,
                        "stdr_year": int(row[i_year]),
                        "stdr_month": month,
                        "price_per_m2": int(float(price_s)),
                    }
