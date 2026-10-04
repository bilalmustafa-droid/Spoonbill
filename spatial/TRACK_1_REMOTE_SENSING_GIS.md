# TRACK 1: Remote Sensing and GIS (Project Spoonbill)

**Owner:** Remote Sensing and GIS Lead
**Mission:** Turn Sentinel-1 and Sentinel-2 imagery into a clean, validated list of persistent wetland-to-land anomalies in the Deep Bay area, exported as structured JSON that Tracks 2 and 3 consume.

> Assumed calendar (adjust if your deadline differs): Day 1 = Mon 5 Oct 2026, Day 8 = Mon 12 Oct, Day 12 = Fri 16 Oct, Days 13-14 = Sat/Sun 17-18 Oct (freeze and submission buffer).

---

## 0. Why this track blocks everything

Track 2 cannot write a brief without anomaly metrics. Track 3 cannot draw a map without anomaly geometry. Your first job is therefore **not accuracy, it is unblocking**: publish a mock file on Day 1 and a rough real file on Day 4, then improve quality behind the same schema.

## 1. Shared data contract (v1, frozen on Day 1)

Output file: `data/anomalies_v1.geojson` (GeoJSON FeatureCollection, EPSG:4326). Do not rename fields without telling all three owners.

```json
{
  "type": "FeatureCollection",
  "metadata": {
    "schema_version": "1.0",
    "generated_at": "2026-10-09T10:00:00Z",
    "baseline_window": ["2023-01-01", "2024-12-31"],
    "current_window": ["2025-01-01", "2026-10-01"],
    "thresholds": {"delta_vv_db": 3.0, "delta_ndwi": -0.25, "despeckle": "3x3 focal median",
                   "persistence_rule": ">=4 of last 6 months and flagged in latest 2"}
  },
  "features": [{
    "type": "Feature",
    "geometry": {"type": "Polygon", "coordinates": []},
    "properties": {
      "anomaly_id": "DB-0001",
      "site_id": "SITE_A",
      "centroid_lon": 114.0,
      "centroid_lat": 22.5,
      "area_ha": 1.42,
      "baseline_vv_db": -19.8,
      "current_vv_db": -13.9,
      "delta_vv_db": 5.9,
      "baseline_ndwi": 0.31,
      "current_ndwi": -0.04,
      "delta_ndwi": -0.35,
      "first_detection_date": "2025-04-01",
      "persistence_count": 5,
      "persistence_total": 6,
      "confidence_tier": "high",
      "zone_hint": "WCA | WBA | OTHER | UNKNOWN",
      "chip_before_png": "chips/DB-0001_before.png",
      "chip_after_png": "chips/DB-0001_after.png"
    }
  }]
}
```

Rules: `confidence_tier` is `high` when both sensors agree and persistence is at least 5 of 6; `medium` when persistence is 4 of 6; `low` otherwise (low tier is kept in the file but hidden by default in the UI). `zone_hint` comes from an optional overlay with the OZP zoning polygons; if you do not have them, write `UNKNOWN`.

## 2. Suggested open-source stack

| Need | Primary | Fallback (fully open) |
|---|---|---|
| Imagery access and compute | Google Earth Engine Python API (free for non-commercial use, not open source) | `pystac-client` + Microsoft Planetary Computer or Copernicus Data Space, `stackstac`, `xarray`, `rioxarray`, `dask` |
| Vector ops | `geopandas`, `shapely` | same |
| Raster ops and despeckle | EE `focal_median` | `scipy.ndimage.median_filter(size=3)` |
| Validation | `scikit-learn` metrics, QGIS for manual labelling | same |
| Chips for UI | EE `getThumbURL` | `matplotlib` or `rasterio` + PIL |

## 3. Detection logic (what you are implementing in `step2.py`)

1. **Sentinel-1 (SAR):** IW mode, VV polarisation, one consistent orbit direction (pick ASCENDING or DESCENDING and stay with it so geometry does not add noise). Apply a 3x3 focal median for despeckling. Build **monthly median composites in dB**.
2. **Sentinel-2 (optical):** `COPERNICUS/S2_SR_HARMONIZED`, cloud mask using the SCL band (drop classes 3, 8, 9, 10) plus a cloud probability limit. NDWI = (B3 - B8) / (B3 + B8). Build monthly median composites.
3. **Baseline climatology:** for each calendar month (Jan to Dec), take the median of the 2023-2024 composites (two samples per month). This is what removes seasonality.
4. **Monthly flag:** for every month in the current window, compare against the baseline climatology of the **same calendar month**:
   `flag = (VV_m - VV_base[month] > +3.0 dB) AND (NDWI_m - NDWI_base[month] < -0.25) AND (NDWI_base_annual_median > 0.0)`
   The last term restricts to places that were wet or water-like in the baseline, so you only flag wetland loss, not random land changes.
5. **Persistence filter:** keep a pixel only if it is flagged in at least 4 of the last 6 usable months **and** in the latest 2 usable months. A drained fishpond that refills fails the "latest 2 months" test. A pond that is drained every winter fails because the same-month baseline also shows it.
6. **Clean up:** morphological opening (remove isolated pixels), minimum mapping unit of about 0.1 ha (tune), vectorise.
7. **Per-polygon stats:** area in ha, mean baseline and current VV and NDWI, first detection date (earliest flagged month among the persistent pixels, use the 10th percentile to avoid outliers), persistence count.

Core code sketch (keep it this small, let your AI assistant expand it):

```python
import ee
ee.Initialize(project="YOUR_PROJECT")

def s1_monthly(aoi, start, end):
    col = (ee.ImageCollection("COPERNICUS/S1_GRD")
           .filterBounds(aoi).filterDate(start, end)
           .filter(ee.Filter.eq("instrumentMode", "IW"))
           .filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING"))
           .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
           .select("VV"))
    return col.map(lambda i: i.focal_median(1, "square", "pixels")
                   .copyProperties(i, ["system:time_start"]))

def s2_ndwi(aoi, start, end):
    def prep(i):
        scl = i.select("SCL")
        ok = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10))
        return (i.updateMask(ok).normalizedDifference(["B3", "B8"]).rename("NDWI")
                .copyProperties(i, ["system:time_start"]))
    return (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(aoi).filterDate(start, end)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40)).map(prep))
```

Note: the GEE S1 collection is already in dB. Median compositing in dB is acceptable for an MVP; mention it as a known simplification in the methodology notes.

---

## PHASE 1: MUST-HAVE CORE SOLUTION (Days 1-8, high priority)

### Day 1 (Mon 5 Oct): Unblock everyone
- [ ] Define the AOI polygon for Deep Bay and choose **2 to 3 showcase sites** (do not try to cover everything).
- [ ] Freeze the data contract above with Tracks 2 and 3 (15 minute call).
- [ ] Authenticate GEE, create the repo folder `track1_gis/`, set up `.env` and a requirements file.
- [ ] **Publish `data/anomalies_mock.geojson`** with 5 to 8 fake but plausible features (valid geometry, all fields filled) plus placeholder chip PNGs.
- **Checkpoint CP0:** Tracks 2 and 3 can load the mock file.
- **Validation:** `jsonschema` check passes on the mock file.

### Day 2 (Tue 6 Oct): Build the two composite stacks
- [ ] Implement `s1_monthly` and `s2_ndwi` as above, monthly composites for 2023-01 to 2026-09.
- [ ] Sanity check: plot VV and NDWI time series for 3 known stable points (open water, mangrove, built-up).
- **Validation:** open water VV is clearly lower (roughly below -18 dB) and NDWI positive; built-up VV is clearly higher.

### Day 3 (Wed 7 Oct): Baseline climatology and monthly flags
- [ ] Build 12-month baseline climatology from 2023-2024 for both sensors.
- [ ] Compute delta VV and delta NDWI per month, apply the fusion rule.
- [ ] Export a quick preview map of flagged pixels to QGIS.
- **Validation:** flagged area is a small fraction of the AOI (if more than a few percent, thresholds or masks are wrong).

### Day 4 (Thu 8 Oct): Persistence filter and first real export (v0.1)
- [ ] Implement the persistence rule and the same-month seasonal logic.
- [ ] Vectorise, filter by minimum area, compute per-polygon stats and first detection date.
- [ ] **Export `data/anomalies_v0.1.geojson` that follows the schema** and push to repo.
- **Checkpoint CP2 (early):** Track 2 runs one real anomaly through the prompt, Track 3 renders real polygons on the map.
- **Validation:** schema check passes, every feature has non-null area, dates and tier.

### Day 5 (Fri 9 Oct): Chips and zone hints
- [ ] Generate before/after RGB chips (Sentinel-2, one cloud-free month from baseline year vs. latest) and VV chips for each high and medium anomaly into `data/chips/`.
- [ ] If OZP/zoning polygons are available (Planning Department open data), overlay them to fill `zone_hint`; otherwise `UNKNOWN`.
- **Validation:** each anomaly has two chip files that open, and the "after" chip visibly differs from "before" for at least 80% of high-tier anomalies.

### Day 6 (Sat 10 Oct): Reference labels
- [ ] Hand-label **40 to 60 points** using high-resolution imagery in QGIS or Google Earth historical imagery: 25 to 30 true wetland-loss points, 15 to 30 negatives (stable ponds, seasonal drain-downs, mangrove, built-up).
- [ ] Save as `validation/labels.geojson`.

### Day 7 (Sun 11 Oct): Tune and measure
- [ ] Compute precision and recall of detections against labels, plus a list of false positives by type.
- [ ] Tune three knobs only: thresholds, persistence count, minimum area.
- [ ] Write `validation/REPORT.md` with the confusion matrix and 3 to 5 example false positives.
- **Validation target:** precision at least 0.70 on high tier, recall at least 0.50 (honest numbers beat inflated ones; the pitch can state limitations).

### Day 8 (Mon 12 Oct): Freeze v1 and hand over
- [ ] Re-run the full pipeline, export **`data/anomalies_v1.geojson`** and all chips.
- [ ] One-command reproduction: `python step2.py --aoi ... --out data/`.
- [ ] Write `METHODOLOGY.md` (one page: sensors, thresholds, persistence, known limits).
- **Checkpoint CP3:** end-to-end demo (GIS file -> brief -> map) runs on a teammate's machine.
- **Validation:** fresh clone plus one command reproduces the file within a small tolerance.

---

## PHASE 2: ADVANCED / OPTIONAL ENHANCEMENTS (Days 9-12, low priority, non-blocking)

Only start these after CP3 passes. Each must ship behind the same schema (new fields are additive and optional).

| Day | Task | Output |
|---|---|---|
| 9 | **Optical brightness confidence tier** for plastic-lined ponds (where SAR change is weak but surface reflectance rises); add `optical_brightness_flag` | Extra field plus tier adjustment |
| 10 | **Time series per anomaly** (monthly VV and NDWI, baseline vs. current) as small JSON arrays for charts | `timeseries` property |
| 11 | **No-net-loss ledger:** total area lost by site and by month, cumulative | `data/ledger.json` |
| 12 | Extend to additional sites, or add Sentinel-1 coherence/ratio cross-check; record pipeline runtime and EE compute notes for the carbon footprint estimate | More coverage, `runtime_log.json` |

Days 13-14: code freeze, bug fixes only, support Track 3 on demo data, no schema changes.

---

## RISK MANAGEMENT AND FALLBACKS

| # | Risk | Likelihood | Impact | Mitigation | Fallback |
|---|---|---|---|---|---|
| 1 | GEE auth, quota or outage | Medium | High | Authenticate on Day 1, cache exports every run | Switch to open stack (Planetary Computer or Copernicus Data Space with `stackstac`); or ship pre-computed GeoJSON and chips, with the pipeline code as evidence |
| 2 | Too many false positives from seasonal fishpond drain-down | High | High | Same-calendar-month baseline, "latest 2 months" persistence test, baseline-wet mask | Raise persistence to 5 of 6, raise min area, mark more items `low`; add a manual exclusion polygon list for known fishpond clusters |
| 3 | Cloud cover and monsoon gaps in optical data | High | Medium | Monthly composites with cloud mask; SAR carries the signal when optical is missing | Allow SAR-only detections with `confidence_tier = medium` and flag `optical_missing = true` |
| 4 | SAR speckle or geometry noise (orbit mixing, tidal flats, wind on water) | Medium | Medium | Single orbit direction, 3x3 median, minimum area | Add a larger focal radius for noisy tiles; mask intertidal areas with a tide-affected polygon |
| 5 | Not enough time for validation | Medium | High | Fix label count at 40 to 60 points, start Day 6 | Use 20 labels minimum and state the limitation explicitly in the report |
| 6 | Schema drift breaks other tracks | Medium | High | Frozen v1 schema, JSON-schema CI check | Version the file (`anomalies_v1`, `v1.1`), never edit in place after Day 8 |
| 7 | Vibecoded code runs but is wrong (silent errors, wrong units) | Medium | High | Unit-check each step with the three reference points; log min/max of each layer | Pair review with another teammate for 30 minutes on Day 4 and Day 8 |
| 8 | Sentinel data for the latest weeks missing or delayed | Low | Low | Define current window end date explicitly | Shorten the window end to the last complete month |

**Definition of done for this track:** `anomalies_v1.geojson` plus chips pass schema validation, precision/recall report exists, one-command reproduction works, and Tracks 2 and 3 confirm they consume the file without edits.
