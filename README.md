# LandPrice — 대한민국 필지별 공시지가 시계열 데이터 구축

전국 모든 필지(공시 대상 약 3,560만)의 **개별공시지가**를 제도상 기록 가능한 최초 시점인 **1990년**부터, 제도상 최대 밀도인 **연 1회(1.1 기준) + 변경 필지 7.1 기준 추가공시** 단위로 수집해 Parquet 데이터셋으로 구축한다.

- 출처 명세와 검증 상태: [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md)
- 수집·정규화·저장·QA 설계: [docs/METHODOLOGY.md](docs/METHODOLOGY.md)

**공신력 원칙**: 국토교통부(국가공간정보센터)·행정안전부·서울특별시·한국부동산원이 생산/배포하는 데이터만 사용. 민간 재가공 출처 불사용.

## 준비

```bash
/opt/homebrew/bin/python3.13 -m venv .venv        # 최초 1회
.venv/bin/pip install -e .
cp .env.example .env                               # VWORLD_KEY 기입
```

**V-World API 키 발급** (전국 스윕에 필수): https://www.vworld.kr/dev/v4dv_apikey_s001.do
회원가입 → 오픈API 인증키 신청 → 개발키 즉시 발급 (유효 6개월). 장기 운영은 운영키(심사 ~10일) 권장.

## 실행 순서

```bash
# 0. (키 발급 직후 1회) API 소급 범위·응답 구조 실측 — 결과를 docs/DATA_SOURCES.md 미검증 항목에 반영
.venv/bin/python scripts/probe_api.py

# 1. 법정동코드 (스윕 키 목록, 무인증)
.venv/bin/python scripts/01_download_bjd_codes.py

# 2. 서울 벌크 1990~2026 다운로드 (무인증, 약 1.5GB)
.venv/bin/python scripts/02_download_seoul_bulk.py

# 3. 서울 벌크 → Parquet 변환
.venv/bin/python scripts/03_convert_seoul.py

# 4. 전국 API 스윕 (서울 제외 예시; 수일 소요, 중단/재시작 안전)
.venv/bin/python scripts/04_sweep_vworld_api.py --years 1990-2026 --skip-sido 11

# 5. 품질 검증 (요약 통계 + 서울 벌크 vs API 교차검증)
.venv/bin/python scripts/05_validate.py --cross
```

## 산출물

```
data/parquet/individual/stdr_year=YYYY/sgg=XXXXX.parquet
```

| 컬럼 | 설명 |
|---|---|
| pnu | 필지 고유번호 19자리 (법정동코드10+대장구분1+본번4+부번4) |
| stdr_year / stdr_month | 공시 기준연도 / 기준월 (1=정기, 7=추가공시) |
| price_per_m2 | 공시지가 (원/㎡) |
| pblntf_de | 공시일자 (제공 시) |
| std_land_yn | 표준지 여부 |
| source | seoul_opendata / vworld_api / vworld_bulk |

조회 예 (DuckDB):

```python
import duckdb
con = duckdb.connect()
con.sql("""
  SELECT stdr_year, avg(price_per_m2)
  FROM read_parquet('data/parquet/individual/**/*.parquet', hive_partitioning=true)
  WHERE pnu LIKE '1111010100%'   -- 종로구 청운동
  GROUP BY 1 ORDER BY 1
""").show()
```

## 규모·소요 (추정)

- 최종 행 수 약 10~13억, Parquet(zstd) 약 20~35GB. 원본 보존 포함 디스크 100GB 권장.
- 전국 스윕: 최소 요청 약 130만 건(1000행/페이지) → 8 req/s 연속 가동 시 2~5일. `--years`로 분할 실행 가능.

## 주의

- 1990년 이전 필지별 공적 지가는 제도상 존재하지 않음 (docs/DATA_SOURCES.md §7).
- API의 1990년대 소급 하한은 미실측 (`scripts/probe_api.py`로 확인 후 진행). 미달 시 대안은 METHODOLOGY §6.
- 공시지가는 공적 평가가격이며 실거래가와 다름.
