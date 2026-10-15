"""Generate synthetic fixture data for Track 3 so the UI can be built before upstream data exists.

Writes into track3_app/fixtures/data/:
    anomalies_v1.geojson     10 features (4 high, 4 medium, 2 low)
    briefs/DB-NNNN.json      6 cited, 2 abstained_human_review, 1 error, 1 anomaly without a brief
    chips/*.png              plain coloured test images, clearly labelled SYNTHETIC
    FIXTURE_DATA.txt         marker file; the app shows the fixture-mode banner when it is present

Everything is validated against contract/*.schema.json and the script exits non-zero on failure.

Honesty rules for fixtures:
    * Citations point to clearly synthetic documents with .invalid URLs. No quote is attributed to a
      real statutory document.
    * Chips carry "SYNTHETIC FIXTURE" text so they can never be mistaken for satellite evidence.
    * DB-0003 deliberately contains one citation_id that does not resolve, to exercise the UI's
      "citation unavailable" path. Real Track 2 output must never do this.

Run:  python track3_app/fixtures/make_fixtures.py
"""

from __future__ import annotations

import json
import math
import random
import shutil
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import MultiPolygon, Polygon, mapping

FIXTURES_DIR = Path(__file__).resolve().parent
OUT_DIR = FIXTURES_DIR / "data"
REPO_ROOT = FIXTURES_DIR.parents[1]
CONTRACT_DIR = REPO_ROOT / "contract"

GENERATED_AT = "2026-10-01T00:00:00Z"
BASELINE_WINDOW = ["2023-01-01", "2024-12-31"]
CURRENT_WINDOW = ["2025-01-01", "2026-09-30"]

DISCLAIMER_EN = (
    "Satellite-derived indicator for screening purposes only. This is not a legal determination "
    "of unauthorised development. Findings require site verification by the relevant authority."
)
DISCLAIMER_ZH = "本結果為衛星遙感篩查指標，僅供參考，並非對違例發展的法律認定。相關發現須由主管部門進行實地核實。"

TIER_ORDER = {"high": 0, "medium": 1, "low": 2}

# One row per fixture anomaly. Values are plausible for Deep Bay: open water VV about -19 dB,
# dry or filled land about -12 to -15 dB; NDWI from about +0.3 (wet) to about -0.1 (dry).
# Low tier uses persistence 3 of 6 to represent weaker candidates that Track 1 keeps in the file
# but the UI hides by default (assumption: "low = anything weaker", PROJECT_CONTEXT section 3).
SPECS = [
    dict(id="DB-0001", site="SITE_A", tier="high", lon=114.0432, lat=22.4952, dx=0.0016, dy=0.0012,
         zone="WBA", optical=True, pers=(6, 6), vv=(-19.8, -12.6), ndwi=(0.33, -0.07),
         first="2025-03-01", timeseries=True, brief="cited"),
    dict(id="DB-0002", site="SITE_B", tier="high", lon=114.0781, lat=22.5023, dx=0.0014, dy=0.0011,
         zone="WBA", optical=True, pers=(5, 6), vv=(-19.2, -13.1), ndwi=(0.29, -0.05),
         first="2025-05-01", multipolygon=True, brief="cited"),
    dict(id="DB-0003", site="SITE_A", tier="high", lon=114.0365, lat=22.4987, dx=0.0012, dy=0.0010,
         zone="WCA", optical=True, pers=(5, 6), vv=(-20.1, -13.9), ndwi=(0.35, -0.02),
         first="2025-06-01", brief="cited", broken_citation=True),
    dict(id="DB-0004", site="SITE_C", tier="high", lon=114.0331, lat=22.4628, dx=0.0011, dy=0.0009,
         zone="OTHER", optical=True, pers=(6, 6), vv=(-18.9, -12.4), ndwi=(0.27, -0.09),
         first="2025-02-01", timeseries=True, brief="cited"),
    # Radar-only detection: PROJECT_CONTEXT caps single-sensor detections at "medium".
    # NDWI values are still required numbers by the contract; here they stand for the last
    # cloud-free optical months (assumption).
    dict(id="DB-0005", site="SITE_B", tier="medium", lon=114.0702, lat=22.4968, dx=0.0013, dy=0.0010,
         zone="WBA", optical=False, pers=(5, 6), vv=(-19.5, -14.8), ndwi=(0.30, 0.02),
         first="2025-07-01", chip_before_null=True, brief="abstained_human_review"),
    dict(id="DB-0006", site="SITE_A", tier="medium", lon=114.0478, lat=22.5068, dx=0.0010, dy=0.0009,
         zone="UNKNOWN", optical=True, pers=(4, 6), vv=(-18.7, -14.9), ndwi=(0.26, -0.01),
         first="2025-08-01", brief="cited"),
    dict(id="DB-0007", site="SITE_C", tier="medium", lon=114.0402, lat=22.4665, dx=0.0009, dy=0.0008,
         zone="WBA", optical=True, pers=(4, 6), vv=(-19.0, -15.2), ndwi=(0.24, -0.03),
         first="2025-09-01", brief="error"),
    dict(id="DB-0008", site="SITE_B", tier="medium", lon=114.0853, lat=22.5081, dx=0.0008, dy=0.0008,
         zone="OTHER", optical=True, pers=(4, 6), vv=(-18.6, -15.1), ndwi=(0.25, -0.02),
         first="2026-01-01", brief=None),
    dict(id="DB-0009", site="SITE_A", tier="low", lon=114.0510, lat=22.4890, dx=0.0007, dy=0.0006,
         zone="UNKNOWN", optical=True, pers=(3, 6), vv=(-18.4, -15.0), ndwi=(0.21, -0.06),
         first="2026-03-01", brief="cited"),
    dict(id="DB-0010", site="SITE_C", tier="low", lon=114.0298, lat=22.4701, dx=0.0006, dy=0.0006,
         zone="OTHER", optical=True, pers=(3, 6), vv=(-18.2, -14.9), ndwi=(0.22, -0.04),
         first="2026-04-01", brief="abstained_human_review"),
]


# --------------------------------------------------------------------------- geometry

def _ring(lon: float, lat: float, dx: float, dy: float, rng: random.Random) -> list[tuple[float, float]]:
    """Irregular closed quadrilateral around (lon, lat), longitude first."""
    jitter = lambda span: rng.uniform(-0.12, 0.12) * span  # noqa: E731
    corners = [
        (lon - dx / 2 + jitter(dx), lat + dy / 2 + jitter(dy)),
        (lon + dx / 2 + jitter(dx), lat + dy / 2 + jitter(dy)),
        (lon + dx / 2 + jitter(dx), lat - dy / 2 + jitter(dy)),
        (lon - dx / 2 + jitter(dx), lat - dy / 2 + jitter(dy)),
    ]
    corners = [(round(x, 6), round(y, 6)) for x, y in corners]
    return corners + [corners[0]]


def build_geometry(spec: dict, rng: random.Random):
    lon, lat, dx, dy = spec["lon"], spec["lat"], spec["dx"], spec["dy"]
    if spec.get("multipolygon"):
        part_a = Polygon(_ring(lon - dx * 0.45, lat, dx * 0.7, dy, rng))
        part_b = Polygon(_ring(lon + dx * 0.55, lat - dy * 0.2, dx * 0.5, dy * 0.7, rng))
        geom = MultiPolygon([part_a, part_b])
    else:
        geom = Polygon(_ring(lon, lat, dx, dy, rng))
    if not geom.is_valid:
        raise SystemExit(f"FIXTURE ERROR: generated invalid geometry for {spec['id']}")
    return geom


def area_hectares(geom) -> float:
    """Approximate equal-area size using a local equirectangular projection (fine at fixture scale)."""
    lat0 = math.radians(geom.centroid.y)
    m_per_deg_lon = 111_320.0 * math.cos(lat0)
    m_per_deg_lat = 110_574.0

    def project(poly: Polygon) -> Polygon:
        return Polygon([(x * m_per_deg_lon, y * m_per_deg_lat) for x, y in poly.exterior.coords])

    polys = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
    return sum(project(p).area for p in polys) / 10_000.0


# --------------------------------------------------------------------------- timeseries

def month_range(start: str, end: str) -> list[str]:
    year, month = int(start[:4]), int(start[5:7])
    end_year, end_month = int(end[:4]), int(end[5:7])
    months = []
    while (year, month) <= (end_year, end_month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return months


def build_timeseries(spec: dict, rng: random.Random) -> dict:
    months = month_range(BASELINE_WINDOW[0], CURRENT_WINDOW[1])
    first = spec["first"][:7]
    base_vv, cur_vv = spec["vv"]
    base_ndwi, cur_ndwi = spec["ndwi"]
    vv, ndwi = [], []
    for m in months:
        season = math.sin(2 * math.pi * (int(m[5:7]) - 1) / 12)
        changed = m >= first
        vv.append(round((cur_vv if changed else base_vv) + 0.5 * season + rng.uniform(-0.4, 0.4), 1))
        nd = (cur_ndwi if changed else base_ndwi) + 0.03 * season + rng.uniform(-0.03, 0.03)
        ndwi.append(round(max(-1.0, min(1.0, nd)), 2))
    return {"months": months, "vv_db": vv, "ndwi": ndwi}


# --------------------------------------------------------------------------- anomalies

def build_feature(spec: dict, rng: random.Random) -> dict:
    geom = build_geometry(spec, rng)
    base_vv, cur_vv = spec["vv"]
    base_ndwi, cur_ndwi = spec["ndwi"]
    aid = spec["id"]
    props = {
        "anomaly_id": aid,
        "site_id": spec["site"],
        "centroid_lon": round(geom.centroid.x, 5),
        "centroid_lat": round(geom.centroid.y, 5),
        "area_ha": round(area_hectares(geom), 2),
        "baseline_vv_db": base_vv,
        "current_vv_db": cur_vv,
        "delta_vv_db": round(cur_vv - base_vv, 1),
        "baseline_ndwi": base_ndwi,
        "current_ndwi": cur_ndwi,
        "delta_ndwi": round(cur_ndwi - base_ndwi, 2),
        "first_detection_date": spec["first"],
        "persistence_count": spec["pers"][0],
        "persistence_total": spec["pers"][1],
        "confidence_tier": spec["tier"],
        "zone_hint": spec["zone"],
        "optical_available": spec["optical"],
        "chip_before_png": None if spec.get("chip_before_null") else f"chips/{aid}_before.png",
        "chip_after_png": f"chips/{aid}_after.png",
    }
    if spec.get("timeseries"):
        props["timeseries"] = build_timeseries(spec, rng)
    return {"type": "Feature", "geometry": mapping(geom), "properties": props}


def _geometry_to_lists(obj):
    """shapely.mapping returns tuples; JSON wants lists (keeps the output identical across runs)."""
    if isinstance(obj, (list, tuple)):
        return [_geometry_to_lists(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _geometry_to_lists(v) for k, v in obj.items()}
    return obj


def build_collection(features: list[dict]) -> dict:
    features = sorted(
        features,
        key=lambda f: (TIER_ORDER[f["properties"]["confidence_tier"]], -f["properties"]["area_ha"]),
    )
    return {
        "type": "FeatureCollection",
        "metadata": {
            "schema_version": "1.0",
            "generated_at": GENERATED_AT,
            "aoi_name": "Deep Bay, Hong Kong (SYNTHETIC FIXTURE)",
            "baseline_window": BASELINE_WINDOW,
            "current_window": CURRENT_WINDOW,
            "sensors": ["Sentinel-1 VV", "Sentinel-2 SR"],
            "thresholds": {
                "delta_vv_db": 3.0,
                "delta_ndwi": -0.25,
                "despeckle": "3x3 focal median",
                "persistence_rule": ">=4 of last 6 months and flagged in latest 2",
                "min_area_ha": 0.1,
            },
            "anomaly_count": len(features),
        },
        "features": _geometry_to_lists(features),
    }


# --------------------------------------------------------------------------- briefs

SITE_EN = {"SITE_A": "Site A", "SITE_B": "Site B", "SITE_C": "Site C"}
SITE_ZH = {"SITE_A": "A 地點", "SITE_B": "B 地點", "SITE_C": "C 地點"}
ZONE_EN = {
    "WCA": "within the Wetland Conservation Area (indicative zoning)",
    "WBA": "within the Wetland Buffer Area (indicative zoning)",
    "OTHER": "outside the Wetland Conservation and Buffer Areas (indicative zoning)",
    "UNKNOWN": "where zoning could not be confirmed",
}
ZONE_ZH = {
    "WCA": "位於濕地保育區（指示性分區）",
    "WBA": "位於濕地緩衝區（指示性分區）",
    "OTHER": "位於濕地保育區及濕地緩衝區以外（指示性分區）",
    "UNKNOWN": "分區未能確定",
}
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December"]

SYNTHETIC_CITATIONS = [
    {
        "id": "FIXTURE-A-p3-c1",
        "doc": "Synthetic Test Document A (fixture)",
        "doc_title_zh": "合成測試文件甲（測試資料）",
        "page": 3,
        "section": "Test section 1",
        "quote": "Synthetic placeholder text for interface testing only; not quoted from any real document.",
        "source_url": "https://example.invalid/fixture-document-a",
    },
    {
        "id": "FIXTURE-B-p11-c2",
        "doc": "Synthetic Test Document B (fixture)",
        "doc_title_zh": "合成測試文件乙（測試資料）",
        "page": 11,
        "section": "Test section 2",
        "quote": "Second synthetic placeholder passage used to check multi-citation layout.",
        "source_url": "https://example.invalid/fixture-document-b",
    },
]
UNRESOLVABLE_CITATION_ID = "FIXTURE-MISSING-p99-c9"

ABSTAIN_REASONS = {
    "DB-0005": "No statutory clause was retrieved above the relevance threshold for this location. "
               "Referred for human review.",
    "DB-0010": "Citation verification failed for every candidate clause, so no statutory claim could "
               "be supported. Referred for human review.",
}


def _evidence_en(p: dict) -> list[str]:
    return [
        f"Affected area: {p['area_ha']:.2f} ha",
        f"Radar backscatter rose {p['delta_vv_db']:+.1f} dB above the 2023-2024 baseline for the same month",
        f"NDWI changed by {p['delta_ndwi']:+.2f} against the same-month baseline",
        f"First detected {p['first_detection_date'][:7]}, persistent in "
        f"{p['persistence_count']} of {p['persistence_total']} recent months",
    ]


def _evidence_zh(p: dict) -> list[str]:
    return [
        f"受影響面積：{p['area_ha']:.2f} 公頃",
        f"雷達後向散射較 2023 至 2024 年同月基線上升 {p['delta_vv_db']:+.1f} dB",
        f"NDWI 較同月基線變化 {p['delta_ndwi']:+.2f}",
        f"首次偵測於 {p['first_detection_date'][:7]}，最近 {p['persistence_total']} 個月中持續 "
        f"{p['persistence_count']} 個月",
    ]


def _summary_en(p: dict) -> str:
    year, month = int(p["first_detection_date"][:4]), int(p["first_detection_date"][5:7])
    return (
        f"A {p['area_ha']:.2f} ha area {ZONE_EN[p['zone_hint']]} shows a persistent transition from "
        f"water-covered to dry or filled surface, first observed in {MONTHS_EN[month - 1]} {year} and "
        f"present in {p['persistence_count']} of the last {p['persistence_total']} months."
    )


def _summary_zh(p: dict) -> str:
    year, month = int(p["first_detection_date"][:4]), int(p["first_detection_date"][5:7])
    return (
        f"一幅面積約 {p['area_ha']:.2f} 公頃、{ZONE_ZH[p['zone_hint']]}的範圍，自 {year} 年 {month} 月起"
        f"持續由水體覆蓋轉為乾地或填土表面，並於最近 {p['persistence_total']} 個月中的 "
        f"{p['persistence_count']} 個月出現。"
    )


def _claims(broken: bool) -> tuple[list[dict], list[dict]]:
    en = [{"claim": "Synthetic test claim used to check that statutory claims and their citations render correctly.",
           "citation_ids": ["FIXTURE-A-p3-c1", "FIXTURE-B-p11-c2"]}]
    zh = [{"claim": "合成測試陳述，用於檢查法定依據及其引用能否正確顯示。",
           "citation_ids": ["FIXTURE-A-p3-c1", "FIXTURE-B-p11-c2"]}]
    if broken:
        en.append({"claim": "Synthetic test claim whose citation intentionally does not resolve.",
                   "citation_ids": [UNRESOLVABLE_CITATION_ID]})
        zh.append({"claim": "合成測試陳述，其引用刻意無法對應，用於測試「引用不可用」標示。",
                   "citation_ids": [UNRESOLVABLE_CITATION_ID]})
    return en, zh


def build_brief(spec: dict, props: dict) -> dict | None:
    status = spec["brief"]
    if status is None:
        return None
    site_en, site_zh = SITE_EN[props["site_id"]], SITE_ZH[props["site_id"]]
    brief = {
        "schema_version": "1.0",
        "anomaly_id": spec["id"],
        "status": status,
        "model": "fixture-generator (no LLM)",
        "generated_at": GENERATED_AT,
        "citations": [],
        "human_review_required": status != "cited",
        "abstain_reason": None,
        "redaction_log": {"items_removed": 0, "types": []},
    }
    if status == "error":
        brief["en"] = {
            "title": "Brief generation failed", "summary": "", "evidence": [], "statutory_basis": [],
            "recommended_action": "", "limitations": DISCLAIMER_EN,
        }
        brief["zh_hant"] = {
            "title": "簡報生成失敗", "summary": "", "evidence": [], "statutory_basis": [],
            "recommended_action": "", "limitations": DISCLAIMER_ZH,
        }
        return brief

    en_claims, zh_claims = _claims(spec.get("broken_citation", False)) if status == "cited" else ([], [])
    brief["en"] = {
        "title": f"Preliminary Observation: Possible Wetland Loss at {site_en}",
        "summary": _summary_en(props),
        "evidence": _evidence_en(props),
        "statutory_basis": en_claims,
        "recommended_action": "Refer for site inspection and zoning confirmation by the relevant authority.",
        "limitations": DISCLAIMER_EN,
    }
    brief["zh_hant"] = {
        "title": f"初步觀察：{site_zh}可能出現濕地損失",
        "summary": _summary_zh(props),
        "evidence": _evidence_zh(props),
        "statutory_basis": zh_claims,
        "recommended_action": "建議轉介主管部門進行實地視察及確認土地用途地帶。",
        "limitations": DISCLAIMER_ZH,
    }
    if status == "cited":
        brief["citations"] = [dict(c) for c in SYNTHETIC_CITATIONS]
    else:
        brief["abstain_reason"] = ABSTAIN_REASONS[spec["id"]]
    return brief


# --------------------------------------------------------------------------- chips

def _font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def draw_chip(path: Path, anomaly_id: str, which: str) -> None:
    """Plain synthetic chip: water-coloured 'before', a tan patch in the 'after' image."""
    img = Image.new("RGB", (512, 512), (46, 92, 110) if which == "before" else (60, 98, 104))
    draw = ImageDraw.Draw(img)
    for x in range(0, 512, 128):  # pond bund grid
        draw.line([(x, 0), (x, 512)], fill=(88, 120, 92), width=6)
        draw.line([(0, x), (512, x)], fill=(88, 120, 92), width=6)
    if which == "after":
        draw.polygon([(170, 160), (350, 175), (340, 345), (160, 330)], fill=(176, 150, 104))
    draw.rectangle([(0, 0), (512, 56)], fill=(20, 20, 20))
    draw.text((12, 10), f"{anomaly_id}  {which.upper()}", fill=(255, 255, 255), font=_font(30))
    draw.rectangle([(0, 456), (512, 512)], fill=(180, 30, 30))
    draw.text((12, 468), "SYNTHETIC FIXTURE - NOT SATELLITE DATA", fill=(255, 255, 255), font=_font(24))
    img.save(path, format="PNG", optimize=True)


# --------------------------------------------------------------------------- validation and output

def _load_schema(name: str) -> dict:
    with open(CONTRACT_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def validate_or_die(doc: dict, schema_name: str, label: str) -> None:
    validator = Draft202012Validator(_load_schema(schema_name))
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    if errors:
        for err in errors:
            location = "/".join(str(p) for p in err.absolute_path) or "(root)"
            print(f"FIXTURE INVALID [{label}] at {location}: {err.message}", file=sys.stderr)
        raise SystemExit(1)


def write_json(path: Path, doc: dict) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main() -> None:
    rng = random.Random(20261001)  # deterministic output
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    (OUT_DIR / "chips").mkdir(parents=True)
    (OUT_DIR / "briefs").mkdir(parents=True)

    features = [build_feature(spec, rng) for spec in SPECS]
    collection = build_collection(features)
    validate_or_die(collection, "anomaly.schema.json", "anomalies_v1.geojson")
    write_json(OUT_DIR / "anomalies_v1.geojson", collection)

    props_by_id = {f["properties"]["anomaly_id"]: f["properties"] for f in features}
    counts: dict[str, int] = {}
    for spec in SPECS:
        props = props_by_id[spec["id"]]
        if props["chip_before_png"]:
            draw_chip(OUT_DIR / props["chip_before_png"], spec["id"], "before")
        draw_chip(OUT_DIR / props["chip_after_png"], spec["id"], "after")

        brief = build_brief(spec, props)
        counts[str(spec["brief"])] = counts.get(str(spec["brief"]), 0) + 1
        if brief is not None:
            validate_or_die(brief, "brief.schema.json", f"briefs/{spec['id']}.json")
            write_json(OUT_DIR / "briefs" / f"{spec['id']}.json", brief)

    (OUT_DIR / "FIXTURE_DATA.txt").write_text(
        "This folder contains SYNTHETIC fixture data generated by make_fixtures.py.\n"
        "It is not real satellite output. The app shows a fixture-mode banner while this file exists.\n",
        encoding="utf-8",
    )
    print(f"OK: wrote {len(features)} anomalies to {OUT_DIR}")
    print(f"    brief statuses: {counts}  (None = no brief file)")


if __name__ == "__main__":
    main()
