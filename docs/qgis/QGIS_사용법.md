# QGIS에서 공시지가 데이터 쓰는 법

이 데이터는 **필지별 공시지가 값 표**입니다 (땅 모양·좌표는 없음). QGIS에서 지도로 그리는 방법은 목적에 따라 두 가지입니다.

---

## A. 지역(시도·시군구) 단위 지도 — 이 폴더 파일만으로 즉시

**대용량 데이터 필요 없습니다.** 이 폴더(`docs/qgis/`)의 GeoJSON은 경계에 값이 이미 들어 있어, 열자마자 지도가 됩니다.

| 파일 | 용량 | 내용 |
|---|---|---|
| `시도_공시지가_1990-2026.geojson` | 1.2 MB | 17개 시도 경계 + 전 연도 지가 |
| `시군구_공시지가_1990-2026.geojson` | 6.6 MB | 250개 시군구 경계 + 전 연도 지가 |

**단계**
1. QGIS에 GeoJSON 파일을 드래그
2. 레이어 우클릭 → 속성 → **심볼(Symbology)**
3. 상단을 **Graduated(단계 구분)** 으로
4. Value = **`med_2026`** (2026년 중위 지가) — 다른 연도는 `med_2010`, `avg_2020` 등 원하는 필드 선택
   - 각 시군구에 `med_1990`…`med_2026`, `avg_1990`…`avg_2026` 이 모두 들어 있음
5. Mode = **Logarithmic(로그)** 권장 (지가 편차가 100배 이상이라)
6. Classify → 색상표 → 적용 ✔

> 좌표계는 **EPSG:4326(WGS84)** 입니다.

---

## B. 필지 단위 지도 — 업로드한 대용량 데이터(Parquet) 사용

개별 필지(땅 하나하나) 정밀 분석이면 **7GB Parquet 원본**을 씁니다. 여기엔 값만 있으니, **필지 도형(연속지적도)에 PNU로 조인**합니다.

### 1) 필지 도형 확보
- V-World 공간정보 다운로드 → **연속지적도**(시군구별 SHP, `PNU` 속성 포함, 무료·로그인)
- https://www.vworld.kr/dtmk/dtmk_ntads_s001.do

### 2) Parquet에서 필요한 지역·연도만 CSV로 추출
전국을 한 번에 하면 무거우니 분석 대상만 뽑습니다. (DuckDB 설치: `pip install duckdb`)

```bash
python parquet_to_csv.py --sgg 11110 --year 2026 --out 종로구_2026.csv
```

또는 QGIS 3.28+ 라면 Parquet를 바로 열 수도 있습니다
(Layer → Add Vector Layer → `.parquet` 선택; GDAL Parquet 드라이버 필요, 지오메트리 없는 테이블로 로드됨).

### 3) QGIS에서 조인
1. 연속지적도 SHP 열기 (예: 종로구)
2. 추출한 CSV 불러오기 (Add Delimited Text Layer)
3. 지적도 레이어 속성 → **Joins** → `+`
   - Join layer = CSV, Join field = `pnu`, Target field = `PNU`(지적도의 고유번호 필드)
4. 조인된 `price_per_m2`로 Graduated 색칠 → **필지별 지가 지도** ✔

---

## 요약

| 원하는 것 | 쓰는 파일 | 대용량 데이터 |
|---|---|---|
| 지역별 지가 지도·비교 | `docs/qgis/*.geojson` | **불필요** |
| 개별 필지 정밀 지도 | 업로드한 Parquet + 연속지적도 | 필요 |

**업로드하신 7GB는 "필지 단위 원본"입니다.** 지역 단위 분석은 위 작은 GeoJSON으로 끝나고, 필지 단위로 파고들 때 그 원본을 씁니다. 둘 다 커버됩니다.

- Parquet가 뭔지, 스키마·PNU 구조·품질 → [../DATA_SPEC.md](../DATA_SPEC.md)
