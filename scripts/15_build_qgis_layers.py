"""QGIS용 경계+지가 레이어 생성 (유효 도형 보장).

- 시도/시군구 경계에 전 연도(1990~2026) 중위·평균 지가를 속성으로 baked-in.
- 위상 보존 단순화(shapely) + make_valid로 유효한 폴리곤만 출력 → QGIS 공간분석 안전.
출력: docs/qgis/
"""
import json
from pathlib import Path

from shapely.geometry import shape, mapping
from shapely.validation import make_valid

from landprice.config import PROJECT_ROOT

OUT = PROJECT_ROOT / "docs" / "qgis"
OUT.mkdir(parents=True, exist_ok=True)
KP = {"11":"서울","21":"부산","22":"대구","23":"인천","24":"광주","25":"대전","26":"울산",
      "29":"세종","31":"경기","32":"강원","33":"충북","34":"충남","35":"전북","36":"전남",
      "37":"경북","38":"경남","39":"제주"}
CRS = {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}


def simplify_valid(geojson_geom, tol):
    g = shape(geojson_geom)
    g = g.simplify(tol, preserve_topology=True)  # 위상 보존 → 유효성 유지
    if not g.is_valid:
        g = make_valid(g)
    return mapping(g)


def baked_props(byyear, years):
    p = {}
    for y in years:
        d = byyear.get(str(y))
        if d:
            p[f"med_{y}"] = d["med"]
            p[f"avg_{y}"] = d["avg"]
    return p


def build(raw_path, key_fn, tol, out_name, extra_props):
    years_data = None
    gj = json.load(open(raw_path))
    feats = []
    for f in gj["features"]:
        key, props = key_fn(f["properties"])
        props.update(baked_props(TABLE.get(key, {}), YEARS))
        feats.append({"type": "Feature", "properties": props,
                      "geometry": simplify_valid(f["geometry"], tol)})
    json.dump({"type": "FeatureCollection", "crs": CRS, "features": feats},
              open(OUT / out_name, "w"), ensure_ascii=False)
    return feats


# ---- 시도 ----
_m = json.load(open("/tmp/map_data.json"))
YEARS = _m["years"]; TABLE = _m["sido"]
build("/tmp/sido.geojson",
      lambda p: (p["name"], {"sido": p["name"]}),
      tol=0.002, out_name="시도_공시지가_1990-2026.geojson", extra_props=None)

# ---- 시군구 ----
TABLE = json.load(open("/tmp/map_sgg.json"))["sgg"]
build("/tmp/sgg.geojson",
      lambda p: (KP.get(p["code"][:2]) + "|" + p["name"],
                 {"sgg_key": KP.get(p["code"][:2]) + "|" + p["name"],
                  "sido": KP.get(p["code"][:2]), "sigungu": p["name"]}),
      tol=0.001, out_name="시군구_공시지가_1990-2026.geojson", extra_props=None)

# ---- 검증 ----
for name in ["시도_공시지가_1990-2026", "시군구_공시지가_1990-2026"]:
    g = json.load(open(OUT / f"{name}.geojson"))
    inv = sum(1 for ft in g["features"] if not shape(ft["geometry"]).is_valid)
    sz = (OUT / f"{name}.geojson").stat().st_size / 1024 / 1024
    print(f"{name}: 피처 {len(g['features'])}, 유효하지않은 도형 {inv}, {sz:.1f} MB")
