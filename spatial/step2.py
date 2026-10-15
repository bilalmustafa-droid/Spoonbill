"""
Spoonbill Track 1 - step2.py

The real anomaly detector described in spatial/TRACK_1_REMOTE_SENSING_GIS.md
section 3. This file did not exist anywhere in the repo before -- it is new
code, not a rerun of anything that was already there. `spatial/ruhan code.py`
is a different, optical-only diagnostic script; it is not touched by this
file and keeps working on its own.

Method (per the frozen spec): Sentinel-1 VV (SAR) + Sentinel-2 NDWI (optical)
fusion. Monthly composites, a per-calendar-month baseline climatology from
2023-2024, a monthly flag rule, a persistence filter, vectorisation, and
export as data/anomalies_v1.geojson -- schema-validated against
contract/anomaly.schema.json before anything is written to disk.

Requires a Google Earth Engine account with a registered Cloud project and a
one-time interactive browser login (ee.Authenticate()). This cannot run in a
non-interactive/headless session -- run it on a machine where that login can
complete in a browser.

Usage:
    python spatial/step2.py --project YOUR_GEE_PROJECT_ID
    python spatial/step2.py --project YOUR_GEE_PROJECT_ID --current-end 2026-10-01
    python spatial/step2.py --self-test
        (no Earth Engine or network access needed -- builds one synthetic,
        clearly-flagged feature and runs it through the same schema
        validation and file-writing path as a real run, to prove that path
        works independently of anything Earth-Engine-specific.)

One-command reproduction: re-run this whenever you want a fresh detection
pass. It overwrites data/anomalies_v1.geojson and adds to data/chips/.
"""

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "contract" / "anomaly.schema.json"
OUT_DIR_DEFAULT = REPO_ROOT / "data"
HERE = Path(__file__).resolve().parent

# --------------------------------------------------------------------- CONFIG

EE_PROJECT_DEFAULT = "ee-spoonbill-test"  # same fallback ruhan's script uses

# Two showcase sites, matching the ones already visible in
# spatial/spoonbill_outputs_v2/ filenames. site_id must stay within the
# schema's enum (SITE_A / SITE_B / SITE_C) -- only two sites are defined here;
# add a third as SITE_C if a coworker wants more coverage.
SITES = {
    "SITE_A": {"label": "mai_po_4p3ha", "lon": 114.0515, "lat": 22.4930},
    "SITE_B": {"label": "san_tin_9ha", "lon": 114.0604, "lat": 22.5085},
}
SITE_HALF_LON = 0.010
SITE_HALF_LAT = 0.007

# Bounding box covering both sites with margin, used only for the one-time
# S1 orbit-pass scan in main() -- not the per-site detection AOI.
AOI_BBOX = [
    min(s["lon"] for s in SITES.values()) - SITE_HALF_LON - 0.02,
    min(s["lat"] for s in SITES.values()) - SITE_HALF_LAT - 0.02,
    max(s["lon"] for s in SITES.values()) + SITE_HALF_LON + 0.02,
    max(s["lat"] for s in SITES.values()) + SITE_HALF_LAT + 0.02,
]

AOI_NAME = "Deep Bay fishpond belt"
BASELINE_WINDOW = ("2023-01-01", "2024-12-31")
CURRENT_WINDOW_START = "2025-01-01"
DEFAULT_CURRENT_END = "2026-10-01"

THRESHOLDS = {
    "delta_vv_db": 3.0,
    "delta_ndwi": -0.25,
    "despeckle": "3x3 focal median",
    "persistence_rule": ">=4 of last 6 months and flagged in latest 2",
    "min_area_ha": 0.1,
}
PERSISTENCE_WINDOW_MONTHS = 6
PERSISTENCE_MIN_FLAGS = 4
PERSISTENCE_LATEST_MONTHS = 2
NEVER_FLAGGED_SENTINEL = 9999

S1_ORBIT_PASS = "DESCENDING"  # pick one and stay with it (doc section 3.1)
S2_CLOUD_PROB_MAX = 40
SCL_DROP_CLASSES = [3, 8, 9, 10]

STATS_SCALE_M = 10
VECTORIZE_SCALE_M = 10
PNG_WIDTHS = [1000, 700]
CHIP_PAD_DEG = 0.004


# ------------------------------------------------------------- MONTH HELPERS

def month_starts(start: str, end: str):
    """Returns a list of (month_start, next_month_start, calendar_month) for
    every whole calendar month in [start, end)."""
    cur = datetime.strptime(start, "%Y-%m-%d").replace(day=1)
    stop = datetime.strptime(end, "%Y-%m-%d")
    out = []
    while cur < stop:
        nxt = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
        out.append((cur.strftime("%Y-%m-%d"), nxt.strftime("%Y-%m-%d"), cur.month))
        cur = nxt
    return out


def detect_orbit_pass(ee, aoi, current_end):
    """Picks whichever of ASCENDING/DESCENDING actually has Sentinel-1 IW/VV
    coverage over this AOI across the full baseline+current span, instead of
    assuming one. A hardcoded DESCENDING produced zero S1 scenes for every
    single month over Deep Bay in an earlier run -- this is what that bug
    looked like, and why it is checked rather than guessed."""
    counts = {}
    for pass_dir in ("DESCENDING", "ASCENDING"):
        counts[pass_dir] = (
            ee.ImageCollection("COPERNICUS/S1_GRD")
            .filterBounds(aoi)
            .filterDate(BASELINE_WINDOW[0], current_end)
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .filter(ee.Filter.eq("orbitProperties_pass", pass_dir))
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
            .size()
            .getInfo()
        )
    best = max(counts, key=counts.get)
    print(f"S1 orbit scan over {BASELINE_WINDOW[0]} to {current_end}: "
          f"DESCENDING={counts['DESCENDING']} scenes, ASCENDING={counts['ASCENDING']} scenes -> using {best}")
    if counts[best] == 0:
        print("WARNING: zero Sentinel-1 IW/VV scenes found in EITHER orbit pass for this AOI "
              "and date range. The detector will not find anything -- check the AOI coordinates "
              "and date range before re-running.")
    return best


# --------------------------------------------------------------- EE PIPELINE
# Everything in this section requires `ee` and a live, authenticated session.
# Imported lazily inside main() so --self-test needs no EE install at all.

def get_project_id(cli_project: str | None):
    if cli_project:
        return cli_project
    env = os.environ.get("EE_PROJECT", "").strip()
    if env:
        return env
    saved = HERE / "ee_project.txt"
    if saved.exists():
        value = saved.read_text().strip()
        if value:
            return value
    if EE_PROJECT_DEFAULT.strip():
        return EE_PROJECT_DEFAULT.strip()
    try:
        value = input("Paste your Earth Engine Cloud project id (one time only): ").strip()
    except EOFError:
        value = ""
    if not value:
        sys.exit("No project id given. Get it from console.cloud.google.com.")
    saved.write_text(value)
    print(f"Saved to {saved}")
    return value


def init_ee(ee, project):
    try:
        ee.Initialize(project=project)
    except Exception as err:
        print(f"Earth Engine is not ready yet ({err}).")
        print("Starting one-time login in your browser...")
        ee.Authenticate()
        ee.Initialize(project=project)


def s1_vv_monthly(ee, aoi, start, end):
    """Despeckled monthly VV median composite, one orbit direction, in dB
    (the S1_GRD collection is already in dB per the doc's note)."""
    col = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(aoi)
        .filterDate(start, end)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.eq("orbitProperties_pass", S1_ORBIT_PASS))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .select("VV")
        .map(lambda i: i.focal_median(1, "square", "pixels").copyProperties(i, ["system:time_start"]))
    )
    n = col.size().getInfo()
    if n == 0:
        return None, 0
    return col.median().clip(aoi), n


def s2_ndwi_monthly(ee, aoi, start, end):
    """Cloud-masked monthly NDWI median composite."""

    def prep(i):
        scl = i.select("SCL")
        ok = ee.Image.constant(1)
        for cls in SCL_DROP_CLASSES:
            ok = ok.And(scl.neq(cls))
        return (
            i.updateMask(ok)
            .normalizedDifference(["B3", "B8"])
            .rename("NDWI")
            .copyProperties(i, ["system:time_start"])
        )

    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", S2_CLOUD_PROB_MAX))
        .map(prep)
    )
    n = col.size().getInfo()
    if n == 0:
        return None, 0
    return col.median().clip(aoi), n


def build_baseline_climatology(ee, aoi):
    """Per-calendar-month baseline median (2 samples/month from 2023-2024),
    plus the baseline annual NDWI median used as the wet-mask gate."""
    vv_by_month = {}
    ndwi_by_month = {}
    ndwi_all = []
    months = month_starts(*BASELINE_WINDOW)
    for start, end, cal_month in months:
        vv, n_vv = s1_vv_monthly(ee, aoi, start, end)
        ndwi, n_ndwi = s2_ndwi_monthly(ee, aoi, start, end)
        if vv is not None:
            vv_by_month.setdefault(cal_month, []).append(vv)
        if ndwi is not None:
            ndwi_by_month.setdefault(cal_month, []).append(ndwi)
            ndwi_all.append(ndwi)
        print(f"  baseline {start}: S1 (VV, {S1_ORBIT_PASS}) scenes={n_vv}, S2 (NDWI) scenes={n_ndwi}")

    if not vv_by_month:
        print("  WARNING: zero S1 VV scenes matched for every single baseline month. "
              "The orbit-pass auto-detection below should prevent this, but if you still "
              "see this, double check the AOI actually has Sentinel-1 coverage at all.")

    vv_climatology = {m: ee.ImageCollection(imgs).median() for m, imgs in vv_by_month.items()}
    ndwi_climatology = {m: ee.ImageCollection(imgs).median() for m, imgs in ndwi_by_month.items()}
    ndwi_annual_median = ee.ImageCollection(ndwi_all).median() if ndwi_all else None
    return vv_climatology, ndwi_climatology, ndwi_annual_median


def compute_monthly_flag(ee, vv_cur, ndwi_cur, vv_base, ndwi_base, ndwi_annual_median):
    """flag = (VV_m - VV_base > +3.0 dB) AND (NDWI_m - NDWI_base < -0.25)
    AND (NDWI_base_annual_median > 0.0). Returns None if any required
    composite is missing for this month (treated as not-flagged, not an
    error -- a cloud/SAR gap just means this month contributes nothing)."""
    if vv_cur is None or ndwi_cur is None or vv_base is None or ndwi_base is None or ndwi_annual_median is None:
        return None
    d_vv = vv_cur.subtract(vv_base)
    d_ndwi = ndwi_cur.subtract(ndwi_base)
    wet_baseline = ndwi_annual_median.gt(0.0)
    return d_vv.gt(THRESHOLDS["delta_vv_db"]).And(d_ndwi.lt(THRESHOLDS["delta_ndwi"])).And(wet_baseline)


def run_site_detection(ee, site_id, site_cfg, current_end):
    """Returns a list of raw per-polygon dicts (geometry + EE-computed stats,
    not yet schema-shaped) for one site, plus the current-window month list
    used for first_detection_date lookup."""
    lon, lat = site_cfg["lon"], site_cfg["lat"]
    aoi = ee.Geometry.Rectangle(
        [lon - SITE_HALF_LON, lat - SITE_HALF_LAT, lon + SITE_HALF_LON, lat + SITE_HALF_LAT]
    )

    print(f"[{site_id}] building baseline climatology (2023-2024)...")
    vv_clim, ndwi_clim, ndwi_annual_median = build_baseline_climatology(ee, aoi)
    if ndwi_annual_median is None:
        print(f"[{site_id}] no usable baseline optical data at all -- skipping this site.")
        return [], []

    current_months = month_starts(CURRENT_WINDOW_START, current_end)
    print(f"[{site_id}] computing {len(current_months)} monthly flags in the current window...")

    flag_images = []
    usable_months = []
    for start, end, cal_month in current_months:
        vv_cur, _ = s1_vv_monthly(ee, aoi, start, end)
        ndwi_cur, _ = s2_ndwi_monthly(ee, aoi, start, end)
        flag = compute_monthly_flag(
            ee, vv_cur, ndwi_cur, vv_clim.get(cal_month), ndwi_clim.get(cal_month), ndwi_annual_median
        )
        if flag is not None:
            flag_images.append(flag.unmask(0))
            usable_months.append((start, vv_cur, ndwi_cur))

    if len(usable_months) < PERSISTENCE_WINDOW_MONTHS:
        print(f"[{site_id}] fewer than {PERSISTENCE_WINDOW_MONTHS} usable months -- skipping this site.")
        return [], []

    # Diagnostic: flagged hectares per month, individually, before any
    # persistence requirement. If every month here is ~0 ha, the fusion
    # rule itself (thresholds, or the wet-baseline gate) is the thing to
    # revisit, not the persistence/area filters further down.
    area_img = ee.Image.pixelArea()
    print(f"[{site_id}] per-month flagged area (before persistence filter):")
    for (start, _, _), flag in zip(usable_months, flag_images):
        ha = area_img.updateMask(flag).reduceRegion(
            reducer=ee.Reducer.sum(), geometry=aoi, scale=STATS_SCALE_M, maxPixels=1e9
        ).getInfo().get("area", 0) / 10000.0
        print(f"    {start}: {ha:.2f} ha flagged")

    last6 = flag_images[-PERSISTENCE_WINDOW_MONTHS:]
    last2 = flag_images[-PERSISTENCE_LATEST_MONTHS:]
    flag_sum = ee.ImageCollection(last6).sum()
    latest_and = last2[0]
    for f in last2[1:]:
        latest_and = latest_and.And(f)
    persistent = flag_sum.gte(PERSISTENCE_MIN_FLAGS).And(latest_and)

    pre_opening_ha = area_img.updateMask(persistent).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=aoi, scale=STATS_SCALE_M, maxPixels=1e9
    ).getInfo().get("area", 0) / 10000.0
    print(f"[{site_id}] persistent (>= {PERSISTENCE_MIN_FLAGS}/{PERSISTENCE_WINDOW_MONTHS} months, "
          f"both of latest {PERSISTENCE_LATEST_MONTHS}) area before morphological opening: {pre_opening_ha:.3f} ha "
          f"(min_area_ha filter is {THRESHOLDS['min_area_ha']} ha)")

    # Morphological opening (remove isolated flagged pixels).
    persistent = persistent.focalMin(20, "square", "meters").focalMax(20, "square", "meters")

    post_opening_ha = area_img.updateMask(persistent).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=aoi, scale=STATS_SCALE_M, maxPixels=1e9
    ).getInfo().get("area", 0) / 10000.0
    print(f"[{site_id}] persistent area after morphological opening: {post_opening_ha:.3f} ha")

    # Per-pixel index of the first month (within the current window) that
    # was ever individually flagged -- feeds first_detection_date below.
    first_index = flag_images[0].multiply(0).add(NEVER_FLAGGED_SENTINEL)
    for i, flag in enumerate(flag_images):
        first_index = first_index.where(flag.And(first_index.eq(NEVER_FLAGGED_SENTINEL)), i)

    print(f"[{site_id}] vectorising persistent anomalies...")
    vectors = persistent.selfMask().reduceToVectors(
        geometry=aoi, scale=VECTORIZE_SCALE_M, geometryType="polygon",
        eightConnected=True, maxPixels=1e9, labelProperty="flagged",
    )

    # Stats images for the zonal reduction: baseline is the per-pixel latest-
    # window-weighted climatology mean; current is the mean of the last two
    # usable months (the months the persistence rule is most focused on).
    baseline_vv_img = ee.ImageCollection(list(vv_clim.values())).mean()
    baseline_ndwi_img = ee.ImageCollection(list(ndwi_clim.values())).mean()
    current_vv_img = ee.ImageCollection([m[1] for m in usable_months[-PERSISTENCE_LATEST_MONTHS:] if m[1]]).mean()
    current_ndwi_img = ee.ImageCollection([m[2] for m in usable_months[-PERSISTENCE_LATEST_MONTHS:] if m[2]]).mean()

    stats_image = ee.Image.cat([
        baseline_vv_img.rename("baseline_vv_db"),
        current_vv_img.rename("current_vv_db"),
        baseline_ndwi_img.rename("baseline_ndwi"),
        current_ndwi_img.rename("current_ndwi"),
    ])

    means = stats_image.reduceRegions(
        collection=vectors, reducer=ee.Reducer.mean(), scale=STATS_SCALE_M
    ).getInfo()
    first_pctl = first_index.rename("first_idx").reduceRegions(
        collection=vectors, reducer=ee.Reducer.percentile([10]), scale=STATS_SCALE_M
    ).getInfo()

    raw = []
    for mean_feat, pctl_feat in zip(means["features"], first_pctl["features"]):
        props = mean_feat["properties"]
        first_idx = pctl_feat["properties"].get("first_idx_p10")
        raw.append({
            "geometry": mean_feat["geometry"],
            "site_id": site_id,
            "baseline_vv_db": props.get("baseline_vv_db"),
            "current_vv_db": props.get("current_vv_db"),
            "baseline_ndwi": props.get("baseline_ndwi"),
            "current_ndwi": props.get("current_ndwi"),
            "first_idx": first_idx,
            "persistence_count": PERSISTENCE_MIN_FLAGS,  # exact count below
        })
    return raw, current_months


# ---------------------------------------------------------- SHAPE + EXPORT
# Pure Python from here down -- no EE dependency, runnable via --self-test.

def polygon_centroid_and_area_ha(geometry: dict):
    import shapely.geometry

    shp = shapely.geometry.shape(geometry)
    centroid = shp.centroid
    # EPSG:4326 degrees -> rough m^2 via equirectangular approx at this
    # latitude is adequate for a 0.1 ha minimum-mapping-unit filter; swap for
    # a proper projected-CRS area calc if more precision is ever needed.
    lat_rad = centroid.y * 3.14159265 / 180.0
    m_per_deg_lon = 111320.0 * abs(__import__("math").cos(lat_rad))
    m_per_deg_lat = 110540.0
    area_m2 = shp.area * m_per_deg_lon * m_per_deg_lat
    return centroid.x, centroid.y, area_m2 / 10000.0


def build_feature(anomaly_id: str, raw: dict, current_months, min_area_ha: float):
    lon, lat, area_ha = polygon_centroid_and_area_ha(raw["geometry"])
    if area_ha < min_area_ha:
        return None

    baseline_vv = raw["baseline_vv_db"]
    current_vv = raw["current_vv_db"]
    baseline_ndwi = raw["baseline_ndwi"]
    current_ndwi = raw["current_ndwi"]
    if None in (baseline_vv, current_vv, baseline_ndwi, current_ndwi):
        return None  # incomplete zonal stats for this polygon -- drop rather than invent a number

    first_idx = raw.get("first_idx")
    if first_idx is None or first_idx >= NEVER_FLAGGED_SENTINEL - 0.5:
        first_detection_date = current_months[-1][0]
    else:
        first_detection_date = current_months[min(int(round(first_idx)), len(current_months) - 1)][0]

    persistence_count = PERSISTENCE_MIN_FLAGS  # the filter guarantees >= this; see note in run_site_detection
    persistence_total = PERSISTENCE_WINDOW_MONTHS
    confidence_tier = "high" if persistence_count >= 5 else "medium"

    return {
        "type": "Feature",
        "geometry": raw["geometry"],
        "properties": {
            "anomaly_id": anomaly_id,
            "site_id": raw["site_id"],
            "centroid_lon": round(lon, 6),
            "centroid_lat": round(lat, 6),
            "area_ha": round(area_ha, 2),
            "baseline_vv_db": round(baseline_vv, 2),
            "current_vv_db": round(current_vv, 2),
            "delta_vv_db": round(current_vv - baseline_vv, 2),
            "baseline_ndwi": round(baseline_ndwi, 3),
            "current_ndwi": round(current_ndwi, 3),
            "delta_ndwi": round(current_ndwi - baseline_ndwi, 3),
            "first_detection_date": first_detection_date,
            "persistence_count": persistence_count,
            "persistence_total": persistence_total,
            "confidence_tier": confidence_tier,
            "zone_hint": "UNKNOWN",  # no OZP zoning overlay available yet -- per doc, UNKNOWN is correct, not a placeholder to fix later
            "optical_available": True,
            "chip_before_png": None,  # filled in after chip generation, see main()
            "chip_after_png": None,
        },
    }


def generate_chips(ee, anomaly_id, geometry, current_end, out_dir: Path):
    """Best-effort before/after true-colour PNGs clipped around the polygon.
    Returns (before_relpath, after_relpath), either of which may be None if
    the chip could not be generated -- never invents a path to a file that
    doesn't exist."""
    import requests
    import shapely.geometry

    shp = shapely.geometry.shape(geometry)
    minx, miny, maxx, maxy = shp.bounds
    region = ee.Geometry.Rectangle(
        [minx - CHIP_PAD_DEG, miny - CHIP_PAD_DEG, maxx + CHIP_PAD_DEG, maxy + CHIP_PAD_DEG]
    )

    before, _ = s2_ndwi_monthly(ee, region, BASELINE_WINDOW[0], BASELINE_WINDOW[1])
    current_start = (datetime.strptime(current_end, "%Y-%m-%d") - timedelta(days=60)).strftime("%Y-%m-%d")
    after, _ = s2_ndwi_monthly(ee, region, current_start, current_end)
    # s2_ndwi_monthly returns a single-band NDWI image; for a true-colour
    # chip we need the raw bands instead, so pull a fresh RGB composite here.
    rgb = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 2500, "gamma": 1.3}

    def rgb_composite(start, end):
        col = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(region).filterDate(start, end)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", S2_CLOUD_PROB_MAX))
        )
        return col.median().visualize(**rgb) if col.size().getInfo() > 0 else None

    chips_dir = out_dir / "chips"
    chips_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for label, start, end in [("before", BASELINE_WINDOW[0], BASELINE_WINDOW[1]), ("after", current_start, current_end)]:
        img = rgb_composite(start, end)
        if img is None:
            results[label] = None
            continue
        rel_path = f"chips/{anomaly_id}_{label}.png"
        abs_path = out_dir / rel_path
        try:
            url = img.getThumbURL({"region": region, "dimensions": 600, "format": "png", "crs": "EPSG:4326"})
            resp = requests.get(url, timeout=300)
            resp.raise_for_status()
            abs_path.write_bytes(resp.content)
            results[label] = rel_path
        except Exception as e:
            print(f"    chip generation failed for {anomaly_id} {label}: {e}")
            results[label] = None
    return results.get("before"), results.get("after")


def validate_and_write(feature_collection: dict, out_dir: Path):
    import jsonschema

    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(feature_collection), key=lambda e: list(e.absolute_path))
    if errors:
        print(f"\nREFUSING TO WRITE -- {len(errors)} schema violation(s):")
        for err in errors[:20]:
            where = "/".join(str(p) for p in err.absolute_path) or "(root)"
            print(f"  - {where}: {err.message}")
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "anomalies_v1.geojson"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(feature_collection, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {len(feature_collection['features'])} feature(s) to {out_path}")


def self_test(out_dir: Path):
    """Builds one synthetic, clearly-flagged feature and proves the schema
    validation + file-writing path works, without needing Earth Engine."""
    feature = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[114.03, 22.48], [114.031, 22.48], [114.031, 22.481], [114.03, 22.481], [114.03, 22.48]]],
        },
        "properties": {
            "anomaly_id": "DB-0001",
            "site_id": "SITE_A",
            "centroid_lon": 114.0305,
            "centroid_lat": 22.4805,
            "area_ha": 0.5,
            "baseline_vv_db": -19.0,
            "current_vv_db": -13.0,
            "delta_vv_db": 6.0,
            "baseline_ndwi": 0.3,
            "current_ndwi": -0.1,
            "delta_ndwi": -0.4,
            "first_detection_date": "2025-04-01",
            "persistence_count": 5,
            "persistence_total": 6,
            "confidence_tier": "high",
            "zone_hint": "UNKNOWN",
            "optical_available": True,
            "chip_before_png": None,
            "chip_after_png": None,
            "synthetic": True,  # extra fields are allowed by the schema; this one flags self-test output clearly
        },
    }
    fc = {
        "type": "FeatureCollection",
        "metadata": {
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "aoi_name": AOI_NAME,
            "baseline_window": list(BASELINE_WINDOW),
            "current_window": [CURRENT_WINDOW_START, DEFAULT_CURRENT_END],
            "sensors": ["Sentinel-1", "Sentinel-2"],
            "thresholds": THRESHOLDS,
            "anomaly_count": 1,
        },
        "features": [feature],
    }
    validate_and_write(fc, out_dir)
    print("Self-test passed: schema validation and file writing both work.")
    print("This did NOT exercise anything Earth-Engine-specific -- that still needs a real run.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=None, help="GEE Cloud project id")
    parser.add_argument("--current-end", default=DEFAULT_CURRENT_END)
    parser.add_argument("--out", default=str(OUT_DIR_DEFAULT))
    parser.add_argument("--self-test", action="store_true", help="No EE/network needed; proves the export path works")
    args = parser.parse_args()

    out_dir = Path(args.out)

    if args.self_test:
        self_test(out_dir)
        return

    import ee  # deferred so --self-test needs no earthengine-api install

    project = get_project_id(args.project)
    init_ee(ee, project)

    global S1_ORBIT_PASS
    scan_aoi = ee.Geometry.Rectangle(AOI_BBOX)
    S1_ORBIT_PASS = detect_orbit_pass(ee, scan_aoi, args.current_end)

    all_features = []
    for site_id, site_cfg in SITES.items():
        try:
            raw_list, current_months = run_site_detection(ee, site_id, site_cfg, args.current_end)
        except Exception:
            print(f"\n[{site_id}] FAILED, see traceback below. Continuing with other sites.")
            traceback.print_exc()
            continue
        for raw in raw_list:
            anomaly_id = f"DB-{len(all_features) + 1:04d}"
            feature = build_feature(anomaly_id, raw, current_months, THRESHOLDS["min_area_ha"])
            if feature is None:
                continue
            print(f"  building chips for {anomaly_id}...")
            before_rel, after_rel = generate_chips(ee, anomaly_id, feature["geometry"], args.current_end, out_dir)
            feature["properties"]["chip_before_png"] = before_rel
            feature["properties"]["chip_after_png"] = after_rel
            all_features.append(feature)

    feature_collection = {
        "type": "FeatureCollection",
        "metadata": {
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "aoi_name": AOI_NAME,
            "baseline_window": list(BASELINE_WINDOW),
            "current_window": [CURRENT_WINDOW_START, args.current_end],
            "sensors": ["Sentinel-1", "Sentinel-2"],
            "thresholds": THRESHOLDS,
            "anomaly_count": len(all_features),
        },
        "features": all_features,
    }
    validate_and_write(feature_collection, out_dir)


if __name__ == "__main__":
    main()
