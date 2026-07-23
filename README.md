# LandPrice — 대한민국 개별공시지가 시계열 (1990–2026)

전국 모든 필지의 **개별공시지가(원/㎡)**를 제도 시작 시점인 1990년부터 2026년까지, 공신력 있는 정부 출처만으로 수집·정규화한 데이터셋과 그 수집 파이프라인입니다.

- **규모**: 1990–2026년 (37개 연도), 약 11.5억 행, 전국 250개 시군구
- **출처**: 국토교통부 V-World 개별공시지가 API (전국·전기간), 서울 열린데이터광장 (교차검증)
- **공시지가는 공적 평가가격**이며 시장 실거래가와 다릅니다.

## 📄 문서 · 시각화 → [`docs/`](docs)

| | |
|---|---|
| **[데이터 명세서](docs/DATA_SPEC.md)** | 스키마·PNU 구조·품질·사용법 (가장 먼저 보세요) |
| **[요약 대시보드](docs/index.html)** | 규모·추이·지역격차 한눈에 (브라우저로 열기) |
| **[시도별 지도](docs/map.html)** | 1990→2026 지가 변화 인터랙티브 지도 |
| [데이터 출처](docs/DATA_SOURCES.md) · [수집 방법론](docs/METHODOLOGY.md) | 출처 검증 상세 · 수집·정규화 설계 |
| [summary_data/](docs/summary_data) | 시도·시군구별 연도 시계열 CSV (바로 사용 가능) |

> 전체 원본 데이터(약 7.2GB)는 용량상 저장소에 포함되지 않습니다. 아래 파이프라인으로 생성하거나, 지역 단위 요약은 `docs/summary_data/`를 사용하세요.

## 코드 구조

```
src/landprice/       수집 라이브러리 (API 클라이언트, 파서, 저장·정규화)
├── config.py          경로·환경설정 (.env)
├── bjd.py             법정동코드 (스윕 키)
├── vworld.py          V-World API 클라이언트 (다중 개정본 dedup 포함)
├── seoul.py           서울 열린데이터광장 벌크
└── storage.py         표준 스키마·Parquet 파티션·체크포인트

scripts/             수집 파이프라인 (실행 순서대로 번호)
```

## 수집 파이프라인 (실행 순서)

```bash
# 준비: 가상환경 + V-World 개발키(.env)
python -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env          # VWORLD_KEY 기입 (https://www.vworld.kr/dev/v4dv_apikey_s001.do)
```

| 스크립트 | 역할 |
|---|---|
| `probe_api.py` | (키 발급 후 1회) API 소급 범위·응답 구조 실측 |
| `01_download_bjd_codes.py` | 법정동코드 다운로드 (스윕 키 목록) |
| `02_download_seoul_bulk.py` · `03_convert_seoul.py` | 서울 벌크 1990–2026 다운로드·변환 |
| `04_sweep_vworld_api.py` | **전국 API 스윕** (체크포인트 재시작·감시견 래퍼: `run_sweep.sh`/`.ps1`) |
| `06_convert_vworld_bulk.py` | V-World 데이터마켓 벌크 변환 (선택) |
| `07`~`10` | 다중 개정본 정리 (재조회·병합·현황집계·dedup) |
| `05_validate.py` | 품질 검증 (교차검증·중복·분포) |
| `11_stats_for_viz.py` · `12_map_data.py` | 시각화용 집계 (docs 웹페이지 데이터 생성) |
| `status.py` | 수집 진행 현황판 (`--live`) |

두 대 이상으로 나눠 수집하려면 [docs/SETUP_WINDOWS.md](docs/SETUP_WINDOWS.md) 참조 (연도 분담).

## 데이터 요약

| 컬럼 | 설명 |
|---|---|
| `pnu` | 필지 고유번호 19자리 (법정동10 + 대장구분1 + 본번4 + 부번4) |
| `stdr_year` / `stdr_month` | 공시 기준연도 / 월 (1=정기, 7=추가공시) |
| `price_per_m2` | 공시지가 (원/㎡) |
| `pblntf_de` · `std_land_yn` · `source` | 공시일자 · 표준지 여부 · 출처 |

전체 스키마·품질·사용 예시는 **[데이터 명세서](docs/DATA_SPEC.md)**에 정리돼 있습니다.
