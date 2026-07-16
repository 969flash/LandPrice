"""법정동코드 다운로드·파싱.

출처: 행정안전부 행정표준코드관리시스템 (code.go.kr) '법정동코드 전체자료'.
POST https://www.code.go.kr/etc/codeFullDown.do 로 무인증 다운로드 가능 (2026-07-14 검증).
ZIP 내 '법정동코드 전체자료.txt' — EUC-KR, 탭 구분, 컬럼: 법정동코드/법정동명/폐지여부.

법정동코드 10자리 구조: 시도(2) + 시군구(3) + 읍면동(3) + 리(2).
필지(PNU)는 동·리 leaf 코드에 붙으므로, API 스윕 키는 leaf 코드 목록이다.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

import requests

from .config import RAW_BJD_DIR

DOWNLOAD_URL = "https://www.code.go.kr/etc/codeFullDown.do"


@dataclass(frozen=True)
class BjdCode:
    code: str  # 10자리
    name: str
    abolished: bool

    @property
    def sido(self) -> str:
        return self.code[:2]

    @property
    def sgg(self) -> str:
        return self.code[:5]

    @property
    def emd(self) -> str:
        return self.code[5:8]

    @property
    def ri(self) -> str:
        return self.code[8:10]


def download(dest_dir: Path = RAW_BJD_DIR) -> Path:
    """전체자료 ZIP을 내려받아 저장하고 경로를 반환."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "법정동코드_전체자료.zip"
    resp = requests.post(DOWNLOAD_URL, data={"codeseId": "법정동코드"}, timeout=60)
    resp.raise_for_status()
    if not resp.content[:2] == b"PK":
        raise RuntimeError("ZIP이 아닌 응답 수신 — code.go.kr 페이지 구조 변경 여부 확인 필요")
    dest.write_bytes(resp.content)
    return dest


def parse(zip_path: Path) -> list[BjdCode]:
    """ZIP 내 텍스트를 파싱해 전체 코드 목록 반환 (폐지 포함)."""
    with zipfile.ZipFile(zip_path) as z:
        # ZIP 내 파일명이 cp949로 인코딩되어 있어 이름으로 찾지 않고 첫 항목 사용
        raw = z.read(z.infolist()[0])
    text = raw.decode("euc-kr")
    codes: list[BjdCode] = []
    for i, line in enumerate(text.splitlines()):
        parts = line.rstrip("\r\n").split("\t")
        if i == 0 or len(parts) < 3:  # 헤더/불량행 스킵
            continue
        code, name, status = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if len(code) != 10 or not code.isdigit():
            continue
        codes.append(BjdCode(code=code, name=name, abolished=(status != "존재")))
    if len(codes) < 10_000:
        raise RuntimeError(f"파싱 행 수 이상 ({len(codes)}행) — 파일 포맷 변경 여부 확인 필요")
    return codes


def leaf_codes(codes: list[BjdCode], include_abolished: bool = True) -> list[BjdCode]:
    """필지가 귀속되는 동·리 leaf 코드만 추출.

    - 읍면동 자리가 '000'이면 시도/시군구 상위 코드 → 제외.
    - 리 != '00' 인 코드는 항상 leaf.
    - 리 == '00' 인 동 코드는, 동일 8자리 접두어 아래 리 코드가 없을 때만 leaf
      (읍·면 코드 자체에는 필지가 붙지 않음).

    폐지 코드는 기본 포함: 원천 DB가 현행 코드로 재키잉되어 있음을 확인했으나
    (서울 1990년 데이터에 1995년 신설 자치구 코드 등장) 누락 대비 비용이 미미함.
    """
    pool = [c for c in codes if c.emd != "000" and (include_abolished or not c.abolished)]
    prefixes_with_ri = {c.code[:8] for c in pool if c.ri != "00"}
    return [c for c in pool if c.ri != "00" or c.code[:8] not in prefixes_with_ri]


def load_leaf_codes(include_abolished: bool = True) -> list[BjdCode]:
    """저장본이 있으면 파싱, 없으면 다운로드 후 파싱."""
    zip_path = RAW_BJD_DIR / "법정동코드_전체자료.zip"
    if not zip_path.exists():
        zip_path = download()
    return leaf_codes(parse(zip_path), include_abolished=include_abolished)


def group_by_sgg(codes: list[BjdCode]) -> dict[str, list[BjdCode]]:
    """시군구(5자리) → leaf 코드 목록. 스윕 작업 단위."""
    out: dict[str, list[BjdCode]] = {}
    for c in codes:
        out.setdefault(c.sgg, []).append(c)
    return out


def group_prefixes_by_sgg(leaves: list[BjdCode]) -> dict[str, list[str]]:
    """시군구(5자리) → 8자리(시도+시군구+읍면동) 접두어 목록.

    API의 pnu 파라미터는 8자리 이상 접두어를 허용하므로, 읍·면 하나를 리 단위로
    쪼개지 않고 한 번에 조회할 수 있다 (하위 리 전체 포함 — 2026-07-15 실측 검증:
    리 21개 읍면의 접두어 조회 = 리별 조회 합계와 일치). 요청 수 약 60% 절감.
    """
    out: dict[str, set[str]] = {}
    for c in leaves:
        out.setdefault(c.sgg, set()).add(c.code[:8])
    return {sgg: sorted(v) for sgg, v in out.items()}
