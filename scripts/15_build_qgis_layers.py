"""QGIS용 경계+지가 레이어 생성 (작은 보조 파일). 대용량 Parquet 재업로드 불필요.

- 시도/시군구 경계에 전 연도(1990~2026) 중위·평균·필지수를 속성으로 baked-in.
  → QGIS에서 열자마자 아무 연도나 색칠 가능 (조인 불필요).
출력: docs/qgis/
"""
import json
from pathlib import Path
from landprice.config import PROJECT_ROOT

OUT = PROJECT_ROOT / "docs" / "qgis"
OUT.mkdir(parents=True, exist_ok=True)
KP = {"11":"서울","21":"부산","22":"대구","23":"인천","24":"광주","25":"대전","26":"울산",
      "29":"세종","31":"경기","32":"강원","33":"충북","34":"충남","35":"전북","36":"전남",
      "37":"경북","38":"경남","39":"제주"}
CRS = {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}


def rnd_geom(g, nd):
    def rr(ring):
        out = []
        for pt in ring:
            p = [round(pt[0], nd), round(pt[1], nd)]
            if not out or out[-1] != p:
                out.append(p)
        return out if len(out) >= 4 else None
    if g["type"] == "Polygon":
        rings = [r for r in (rr(x) for x in g["coordinates"]) if r]
        return {"type": "Polygon", "coordinates": rings} if rings else None
    polys = []
    for poly in g["coordinates"]:
        rings = [r for r in (rr(x) for x in poly) if r]
        if rings:
            polys.append(rings)
    return {"type": "MultiPolygon", "coordinates": polys} if polys else None


def baked_props(byyear, years):
    """전 연도 med/avg를 med_YYYY 속성으로. + 대표값(최신)."""
    p = {}
    for y in years:
        d = byyear.get(str(y))
        if d:
            p[f"med_{y}"] = d["med"]
            p[f"avg_{y}"] = d["avg"]
    return p


# ---- 시도 ----
sido = json.load(open("/tmp/map_data.json"))
years = sido["years"]; sido = sido["sido"]
gj = json.load(open("/tmp/sido_simplified.json"))
feats = []
for f in gj["features"]:
    nm = f["properties"]["name"]
    props = {"sido": nm}
    props.update(baked_props(sido.get(nm, {}), years))
    feats.append({"type": "Feature", "properties": props, "geometry": rnd_geom(f["geometry"], 3)})
json.dump({"type": "FeatureCollection", "crs": CRS, "features": feats},
          open(OUT / "시도_공시지가_1990-2026.geojson", "w"), ensure_ascii=False)

# ---- 시군구 ----
sgg = json.load(open("/tmp/map_sgg.json"))["sgg"]
gj = json.load(open("/tmp/sgg.geojson"))
feats = []
for f in gj["features"]:
    pr = f["properties"]; prov = KP.get(pr["code"][:2]); key = prov + "|" + pr["name"]
    props = {"sgg_key": key, "sido": prov, "sigungu": pr["name"]}
    props.update(baked_props(sgg.get(key, {}), years))
    feats.append({"type": "Feature", "properties": props, "geometry": rnd_geom(f["geometry"], 4)})
json.dump({"type": "FeatureCollection", "crs": CRS, "features": feats},
          open(OUT / "시군구_공시지가_1990-2026.geojson", "w"), ensure_ascii=False)

print("생성 완료:")
for p in sorted(OUT.glob("*.geojson")):
    print(f"  {p.name}  ({p.stat().st_size/1024/1024:.1f} MB)")
