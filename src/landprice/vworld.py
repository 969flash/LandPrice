"""V-World NED Open API 클라이언트 (국토교통부 국가공간정보센터 제공).

- 개별공시지가속성조회: https://api.vworld.kr/ned/data/getIndvdLandPriceAttr (apiNum=25)
- 표준지공시지가속성조회: https://api.vworld.kr/ned/data/getReferLandPriceAttr (apiNum=74)

`pnu` 파라미터는 8자리 이상 접두어를 허용하므로 10자리 법정동코드를 넣으면
해당 법정동 전체 필지가 페이지(최대 1000행)로 반환된다.

응답 envelope 실측 (2026-07-14, 무키 호출):
    {"indvdLandPrices": {"resultCode": "INVALID_KEY", "resultMsg": "..."}}
정상 응답의 행 목록 키는 문서화가 빈약해 방어적으로 파싱한다
(dict 안에서 list-of-dict 값을 탐색). 키 발급 후 scripts/probe_api.py로 실측할 것.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Iterator

import requests

INDVD_URL = "https://api.vworld.kr/ned/data/getIndvdLandPriceAttr"
REFER_URL = "https://api.vworld.kr/ned/data/getReferLandPriceAttr"
MAX_ROWS = 1000

# 응답 행 필드 (컬럼정의서·API 스펙 기준)
ROW_FIELDS = (
    "pnu", "ldCode", "ldCodeNm", "regstrSeCode", "mnnmSlno",
    "stdrYear", "stdrMt", "pblntfPclnd", "pblntfDe", "stdLandAt", "lastUpdtDt",
)

FATAL_CODES = {"INVALID_KEY", "UNREGISTERED_KEY", "DENIED_KEY", "EXPIRED_KEY"}


class VWorldError(RuntimeError):
    pass


class InvalidKeyError(VWorldError):
    pass


class VWorldClient:
    def __init__(
        self,
        key: str,
        domain: str = "",
        rps: float = 8.0,
        # 정상 응답 중앙값 ~0.03s, 페이지당 최대 ~1s — 간헐적 커넥션 정지(10~30s)를
        # 빨리 끊고 재시도하는 편이 전체 처리량에 유리 (2026-07-14 실측)
        timeout: float = 12.0,
        max_retries: int = 6,
    ) -> None:
        if not key:
            raise InvalidKeyError(
                "VWORLD_KEY가 비어 있습니다. https://www.vworld.kr/dev/v4dv_apikey_s001.do 에서 "
                "발급 후 .env에 설정하세요 (개발키 즉시 발급, 유효 6개월)."
            )
        self.key = key
        self.domain = domain
        self.min_interval = 1.0 / rps if rps > 0 else 0.0
        self.timeout = timeout
        self.max_retries = max_retries
        self._last_call = 0.0
        self._throttle_lock = threading.Lock()  # 전역 속도 제한 (워커 수와 무관하게 rps 준수)
        self._local = threading.local()

    @property
    def session(self) -> requests.Session:
        # requests.Session은 스레드 안전이 보장되지 않아 스레드별로 생성
        if not hasattr(self._local, "session"):
            self._local.session = requests.Session()
        return self._local.session

    # ---- 저수준 ----

    def _throttle(self) -> None:
        with self._throttle_lock:
            now = time.monotonic()
            wait = self._last_call + self.min_interval - now
            self._last_call = max(now, self._last_call + self.min_interval)
        if wait > 0:
            time.sleep(wait)

    def _get(self, url: str, params: dict[str, Any]) -> dict:
        params = {k: v for k, v in params.items() if v not in (None, "")}
        params["key"] = self.key
        if self.domain:
            params["domain"] = self.domain
        params["format"] = "json"

        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                # stream + 총 시간 상한: requests의 timeout은 청크 간 간격만 재므로,
                # 서버가 바이트를 찔끔찔끔 흘리면 몇 시간이고 매달릴 수 있다 (2026-07-15 실제 발생)
                resp = self.session.get(url, params=params, timeout=self.timeout, stream=True)
                if resp.status_code >= 500:
                    resp.close()
                    raise VWorldError(f"HTTP {resp.status_code}")
                resp.raise_for_status()
                deadline = time.monotonic() + 60.0
                chunks = []
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    chunks.append(chunk)
                    if time.monotonic() > deadline:
                        resp.close()
                        raise VWorldError("응답 전송 지연 60초 초과")
                import json as _json

                return _json.loads(b"".join(chunks))
            except (requests.RequestException, ValueError, VWorldError) as exc:
                last_exc = exc
                time.sleep(min(0.5 * 2.0**attempt, 8.0))
        raise VWorldError(f"{url} 재시도 {self.max_retries}회 실패: {last_exc}")

    @staticmethod
    def _unwrap(payload: dict) -> tuple[list[dict], int, str]:
        """응답에서 (행 목록, totalCount, resultCode)를 방어적으로 추출."""
        # envelope: {"indvdLandPrices": {...}} 또는 {"referLandPrices": {...}} 등
        body = payload
        if len(payload) == 1 and isinstance(next(iter(payload.values())), dict):
            body = next(iter(payload.values()))

        result_code = str(body.get("resultCode", "")).upper()
        total = body.get("totalCount", body.get("totalcount", 0))
        try:
            total = int(total)
        except (TypeError, ValueError):
            total = 0

        rows: list[dict] = []
        for key in ("field", "fields", "items", "item", "list"):
            val = body.get(key)
            if isinstance(val, list):
                rows = [r for r in val if isinstance(r, dict)]
                break
            if isinstance(val, dict):  # 단건이 dict로 오는 경우
                rows = [val]
                break
        if not rows:  # 알려진 키가 없으면 첫 list-of-dict 값 탐색
            for val in body.values():
                if isinstance(val, list) and val and isinstance(val[0], dict):
                    rows = val
                    break
        return rows, total, result_code

    # ---- 공개 API ----

    def fetch_page(
        self, pnu_prefix: str, year: int | None, page: int, url: str = INDVD_URL
    ) -> tuple[list[dict], int]:
        """한 페이지 조회 → (행 목록, totalCount)."""
        payload = self._get(
            url,
            {
                "pnu": pnu_prefix,
                "stdrYear": str(year) if year else None,
                "numOfRows": MAX_ROWS,
                "pageNo": page,
            },
        )
        rows, total, code = self._unwrap(payload)
        if code in FATAL_CODES:
            raise InvalidKeyError(f"인증키 오류 ({code}) — 키/도메인 등록 상태를 확인하세요.")
        return rows, total

    def iter_parcels(
        self, pnu_prefix: str, year: int | None = None, url: str = INDVD_URL
    ) -> Iterator[dict]:
        """법정동코드(또는 PNU 접두어) × 연도의 전 필지를 페이지 순회로 반환."""
        page = 1
        seen = 0
        while True:
            rows, total = self.fetch_page(pnu_prefix, year, page, url=url)
            if not rows:
                return
            yield from rows
            seen += len(rows)
            if seen >= total or len(rows) < MAX_ROWS:
                return
            page += 1
