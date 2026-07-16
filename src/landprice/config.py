"""경로·환경설정. .env에서 VWORLD_KEY 등을 읽는다."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PARQUET_DIR = DATA_DIR / "parquet"
DB_DIR = DATA_DIR / "db"

RAW_SEOUL_DIR = RAW_DIR / "seoul"
RAW_BJD_DIR = RAW_DIR / "bjd"
INDIVIDUAL_DIR = PARQUET_DIR / "individual"
STANDARD_DIR = PARQUET_DIR / "standard"
CHECKPOINT_DB = DB_DIR / "checkpoints.sqlite"

# 개별공시지가 최초 고시 연도 (1990-08-30, 당시 '개별토지가격')
FIRST_YEAR = 1990

VWORLD_KEY = os.getenv("VWORLD_KEY", "")
VWORLD_DOMAIN = os.getenv("VWORLD_DOMAIN", "")
# 명목 한도는 사실상 무제한이지만 초당 제한이 미문서화라 보수적 기본값 사용
VWORLD_RPS = float(os.getenv("VWORLD_RPS", "8"))


def ensure_dirs() -> None:
    for d in (RAW_SEOUL_DIR, RAW_BJD_DIR, INDIVIDUAL_DIR, STANDARD_DIR, DB_DIR):
        d.mkdir(parents=True, exist_ok=True)
