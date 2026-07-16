"""법정동코드 전체자료 다운로드 및 leaf 코드 요약.

사용: .venv/bin/python scripts/01_download_bjd_codes.py
"""

from landprice import bjd
from landprice.config import RAW_BJD_DIR, ensure_dirs


def main() -> None:
    ensure_dirs()
    zip_path = RAW_BJD_DIR / "법정동코드_전체자료.zip"
    if not zip_path.exists():
        zip_path = bjd.download()
        print(f"다운로드 완료: {zip_path}")
    else:
        print(f"기존 파일 사용: {zip_path}")

    codes = bjd.parse(zip_path)
    leaves = bjd.leaf_codes(codes)
    active = [c for c in leaves if not c.abolished]
    by_sgg = bjd.group_by_sgg(leaves)
    print(f"전체 코드: {len(codes):,}")
    print(f"leaf 코드 (폐지 포함): {len(leaves):,} / (현존만): {len(active):,}")
    print(f"시군구 단위: {len(by_sgg):,}")


if __name__ == "__main__":
    main()
