# 윈도우 분담 수집 가이드 (2012~2026년)

이 문서는 두 번째 컴퓨터(Windows)에서 수집을 분담하기 위한 것으로, **그 컴퓨터의 Claude 세션이 그대로 따라 실행하면 되도록** 작성됨.

## 역할 분담 (2026-07-16 확정)

| 기계 | 담당 연도 | 비고 |
|---|---|---|
| 맥 (원본) | 1990~2011 | 서울 전 연도는 벌크로 적재 완료 |
| 윈도우 (이 기계) | **2012~2026** | **서울(시도 11) 제외** — 래퍼에 이미 반영됨 |

두 기계의 산출물은 연도로 완전히 분리되므로 충돌 없음. 각자 로컬 체크포인트를 쓰므로 동기화 불필요.

## 설치 (Claude가 실행)

1. **Python 3.10 이상 설치** (없다면): `winget install Python.Python.3.12` 후 터미널 재시작
2. 전달받은 `landprice_windows_kit.zip`을 원하는 위치에 풀기 (예: `C:\LandPrice`) — 이하 그 폴더에서:
   ```powershell
   python -m venv .venv
   .venv\Scripts\pip install -e .
   ```
3. `.env` 파일이 있는지 확인 (VWORLD_KEY 포함 — 키트에 포함되어 있음. 같은 키를 두 기계에서 써도 무방)
4. 전원 설정: 노트북이면 "전원 연결 시 절전 안 함" 권장 (래퍼가 잠자기 방지를 걸지만 이중 안전)

## 실행

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_sweep.ps1 -Years 2012-2026
```

- 실패 단위가 0이 될 때까지 자동 반복 (최대 40패스), 20분 진행 정체 시 자동 재시작
- 중단해도 안전: 재실행하면 완료 단위는 건너뛰고 이어서 진행
- 법정동코드는 첫 실행 시 자동 다운로드 (키트에 원본 포함되어 있으면 그것 사용)

## 진행 확인

```powershell
.venv\Scripts\python scripts\status.py
```
주의: 진행률(%)은 전 연도·전국 기준이라 이 기계 담당분만 보면 과소 표시됨. **"수집된 가격 기록" 행 수가 늘어나는지**와 최근 30분 속도를 보면 됨.

## 완료 후 (수작업 병합 — 맥으로 가져갈 것)

1. `data\parquet\individual\` 아래의 `stdr_year=2012` ~ `stdr_year=2026` 폴더 전체
2. `data\db\checkpoints.sqlite` (감사 기록용, 이름을 `checkpoints_windows.sqlite`로 바꿔서)

맥 프로젝트의 `data/parquet/individual/`에 연도 폴더들을 그대로 복사해 넣으면 병합 완료 (연도가 겹치지 않아 덮어쓰기 없음). 병합 후 맥에서 `scripts/05_validate.py`로 전체 검증.

## 문제 발생 시

- `INVALID_KEY` / 인증키 오류: .env의 VWORLD_KEY 확인 (vworld.kr 마이포털에서 키 상태 확인)
- HTTP 502 / 연결 끊김 다발: 정상 범위(서버 간헐 오류) — 래퍼가 자동 재시도. 지속되면 -Years 범위를 쪼개 실행
- 특정 단위 반복 실패: 그대로 두면 다음 패스에서 재시도됨. 40패스 후에도 남으면 맥 쪽 세션에 보고
