# PROJECT SPOONBILL: Shared Context and Data Contract (v1.0)

**Read this file before writing any code. It is the single source of truth for everything that crosses track boundaries.**

This file is given to every AI assistant working on the project. Each developer also has one track file:
`TRACK_1_REMOTE_SENSING_GIS.md`, `TRACK_2_GENAI_RAG_BACKEND.md`, `TRACK_3_FULLSTACK_STREAMLIT_UI.md`.

If this file and a track file disagree, **this file wins**.

---

## 1. What the project is

**Project Spoonbill** is a satellite-based monitoring platform that checks whether Hong Kong's **"no net loss of wetland"** commitment for the Northern Metropolis is actually being kept in the **Deep Bay area**.

It works in three stages:

1. **Detect.** Free Sentinel-1 radar and Sentinel-2 optical imagery are compared against a historical baseline to find places where wetland has turned into dry or filled land, and where that change has persisted.
2. **Ground.** Each detection is matched against Hong Kong statutory documents (planning guidelines, zoning notes, environmental conditions) using retrieval-augmented generation, so every statement in the output is backed by a real clause.
3. **Report.** A dashboard shows the detections on a map with satellite evidence, and exports a bilingual (English and Traditional Chinese) preliminary brief that a government or NGO officer could act on.

**Built for:** the Hong Kong Inter-University GenAI Hackathon for SDGs 2026, Sustainable Northern Metropolis track.
**Intended users:** planning and environmental enforcement staff, conservation NGOs, researchers.
**Deadline:** final submission in 2 weeks. MVP must be complete and runnable by Day 8.

### Why this matters for how you write code
The judging rewards: GenAI genuinely inside the product (not a bolt-on chatbot), cost efficiency relative to value, and real sustainability impact. So:
- The AI must make decisions and produce grounded output, not just chat.
- Prefer free and open-source tooling. Running costs are part of the pitch.
- Honest, verifiable output beats impressive-looking output.

---

## 2. Team and ownership

| Track | Owner | Folder in repo | Produces | Consumes |
|---|---|---|---|---|
| Track 1: Remote Sensing and GIS | **Shabbir** | `track1_gis/` | `data/anomalies_v1.geojson`, `data/chips/*.png` | Sentinel imagery |
| Track 2: GenAI and RAG Backend | **Ruhan** | `track2_rag/` | `data/briefs/*.json` | Track 1 GeoJSON, statutory documents |
| Track 3: Full-Stack UI and Reporting | **Bilal** | `track3_app/` | Streamlit app, PDF and DOCX exports | Track 1 GeoJSON and chips, Track 2 briefs |

Each person uses a different AI assistant. **Work only inside your own folder.** Never edit another track's code. The only things shared are the `data/` folder, the `contract/` folder and this file.

### Repo and branch rules
- One private GitHub monorepo, everyone works in it.
- Branch naming: `track1-gis`, `track2-rag`, `track3-ui`. Open a pull request into `main`, do not push directly to `main`.
- Commit small and often. Never commit secrets or API keys; use a local `.env` file that is listed in `.gitignore`.
- Large binary outputs (chips, exports) go in `data/`, which is committed so the demo works offline. Keep total repo size reasonable (resize chips to about 512 px).

---

## 3. Frozen decisions (do not change without telling the whole team)

These are fixed for v1. Changing any of them silently will break another track.

### Geography and time
- **Area of interest:** Deep Bay area, Hong Kong (Mai Po, Inner Deep Bay, San Tin, Nam Sang Wai and surrounding fishpond belt).
- **Showcase sites:** 2 to 3 only. Site IDs are `SITE_A`, `SITE_B`, `SITE_C`. Shabbir defines the exact polygons and records them in `contract/sites.json`.
- **Baseline window:** 2023-01-01 to 2024-12-31.
- **Current window:** 2025-01-01 to the last complete month before the run date.
- **Coordinate reference system: EPSG:4326 (WGS84), longitude then latitude, everywhere.** Compute areas in a metric projection (EPSG:32650 or an equal-area projection) but always publish geometry in EPSG:4326.
- **All timestamps are ISO 8601 UTC** with a `Z` suffix, for example `2026-10-09T10:00:00Z`. Dates alone are `YYYY-MM-DD`.
- **Units:** area in hectares (`area_ha`), backscatter in decibels (`dB`), NDWI unitless from -1 to 1.

### Detection rule (Track 1)
- Sentinel-1 VV, single orbit direction, 3x3 focal median despeckle, monthly median composites in dB.
- Sentinel-2 NDWI = (B3 - B8) / (B3 + B8), cloud-masked, monthly median composites.
- A pixel is flagged for a month when, compared with the **same calendar month** in the baseline:
  `delta_VV > +3.0 dB` AND `delta_NDWI < -0.25` AND the baseline was wet.
- **Persistence:** keep only pixels flagged in at least 4 of the last 6 usable months AND in the latest 2 usable months. This is what removes seasonal fishpond drain-down.
- Minimum mapping unit about 0.1 ha.
- Confidence tiers: `high` = both sensors agree and persistence at least 5 of 6; `medium` = persistence 4 of 6, or only one sensor available; `low` = anything weaker (kept in the file, hidden by default in the UI).

### Language and terminology
Output is bilingual. Use **Traditional Chinese (Hong Kong)**, never Simplified.

| English | Traditional Chinese |
|---|---|
| Deep Bay | 后海灣 |
| Wetland Conservation Area (WCA) | 濕地保育區 |
| Wetland Buffer Area (WBA) | 濕地緩衝區 |
| no net loss | 無淨損失 |
| wetland | 濕地 |
| fishpond | 魚塘 |
| preliminary observation | 初步觀察 |
| requires human review | 需人工覆核 |

Confirm each term against the actual source documents before shipping; where a document uses a different official term, follow the document.



---

## 4. Non-negotiable rules (all tracks)

1. **No personal data, ever.** Do not ingest, store, display or export land ownership records, owner names, HKID numbers, phone numbers, email addresses or individual addresses. Locations are identified by coordinates, site ID and area only. This is a PDPO requirement and a judging risk.
2. **No legal conclusions.** The system never states that something is illegal, unauthorised or in breach. Allowed wording: "possible", "preliminary", "indicator", "refer for inspection and verification". Every screen and every exported document carries the disclaimer below.
3. **Cite or abstain.** Any statement about what the rules require must carry a citation to a real, retrieved clause. If no relevant clause is retrieved, the system abstains and flags the item for human review. It never guesses.
4. **The demo never depends on a live external call.** Track 1 and Track 2 write their outputs to files. The UI reads those files. No Earth Engine call and no LLM call on stage.
5. **Never break the contract in section 5.** Adding a new optional field is fine. Renaming, removing or retyping an existing field is not, unless all three agree.

**Standard disclaimer (use this exact text):**
> English: "Satellite-derived indicator for screening purposes only. This is not a legal determination of unauthorised development. Findings require site verification by the relevant authority."
>
> 繁體中文:「本結果為衛星遙感篩查指標，僅供參考，並非對違例發展的法律認定。相關發現須由主管部門進行實地核實。」

---

## 5. THE DATA CONTRACT (v1.0)

Three files flow through the system:

```
Shabbir (Track 1)              Ruhan (Track 2)                 Bilal (Track 3)
data/anomalies_v1.geojson  ->  data/briefs/{anomaly_id}.json -> Streamlit UI + PDF/DOCX
data/chips/*.png           ------------------------------------>
```

JSON Schemas live in `contract/anomaly.schema.json` and `contract/brief.schema.json`.
**Every track validates its own output, and validates its input, against these schemas.** Use `jsonschema` in Python. A pipeline that writes an invalid file is a failed run, not a warning.

### 5.1 File A: `data/anomalies_v1.geojson` (Track 1 writes, Tracks 2 and 3 read)

A GeoJSON `FeatureCollection` in EPSG:4326.

```json
{
  "type": "FeatureCollection",
  "metadata": {
    "schema_version": "1.0",
    "generated_at": "2026-10-12T04:00:00Z",
    "aoi_name": "Deep Bay, Hong Kong",
    "baseline_window": ["2023-01-01", "2024-12-31"],
    "current_window": ["2025-01-01", "2026-09-30"],
    "sensors": ["Sentinel-1 VV", "Sentinel-2 SR"],
    "thresholds": {
      "delta_vv_db": 3.0,
      "delta_ndwi": -0.25,
      "despeckle": "3x3 focal median",
      "persistence_rule": ">=4 of last 6 months and flagged in latest 2",
      "min_area_ha": 0.1
    },
    "anomaly_count": 12
  },
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Polygon", "coordinates": [[[114.0512, 22.4981], [114.0530, 22.4981], [114.0530, 22.4968], [114.0512, 22.4968], [114.0512, 22.4981]]] },
      "properties": {
        "anomaly_id": "DB-0001",
        "site_id": "SITE_A",
        "centroid_lon": 114.0521,
        "centroid_lat": 22.4974,
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
        "zone_hint": "WBA",
        "optical_available": true,
        "chip_before_png": "chips/DB-0001_before.png",
        "chip_after_png": "chips/DB-0001_after.png"
      }
    }
  ]
}
```

**Field rules**

| Field | Type | Required | Rule |
|---|---|---|---|
| `anomaly_id` | string | yes | Format `DB-NNNN`, zero-padded, unique, **stable across reruns where possible** |
| `site_id` | string | yes | One of `SITE_A`, `SITE_B`, `SITE_C` |
| `centroid_lon`, `centroid_lat` | number | yes | EPSG:4326, 4+ decimal places |
| `area_ha` | number | yes | Hectares, greater than 0, 2 decimal places |
| `baseline_vv_db`, `current_vv_db`, `delta_vv_db` | number | yes | dB. `delta = current - baseline` |
| `baseline_ndwi`, `current_ndwi`, `delta_ndwi` | number | yes | -1 to 1. `delta = current - baseline` |
| `first_detection_date` | string | yes | `YYYY-MM-DD`, first day of the month first flagged |
| `persistence_count`, `persistence_total` | integer | yes | For example 5 of 6 |
| `confidence_tier` | string | yes | `high` \| `medium` \| `low` |
| `zone_hint` | string | yes | `WCA` \| `WBA` \| `OTHER` \| `UNKNOWN`. Use `UNKNOWN` when zoning data is unavailable. **It is a hint, not a legal determination.** |
| `optical_available` | boolean | yes | `false` when the detection is SAR-only (cloud cover) |
| `chip_before_png`, `chip_after_png` | string | yes | Path **relative to `data/`**, forward slashes. Use `null` if missing; consumers must handle `null` |
| `timeseries` | object | no | Optional Phase 2 field, see 5.4 |
| `optical_brightness_flag` | boolean | no | Optional Phase 2 field for plastic-lined ponds |

**Hard rules**
- Numbers are JSON numbers, never strings. No `NaN`, no `Infinity`. Use `null` for genuinely missing values, and only on fields marked optional or explicitly nullable (`chip_*`).
- Polygons must be valid and closed, with the first and last coordinate identical.
- Geometry may be `Polygon` or `MultiPolygon`. Consumers must handle both.
- The file is sorted by `confidence_tier` (high, medium, low) then by `area_ha` descending.

**Chips:** PNG, roughly 512x512, in `data/chips/`. Naming: `{anomaly_id}_before.png` and `{anomaly_id}_after.png`. Both show the same extent so they can be compared side by side.

### 5.2 File B: `data/briefs/{anomaly_id}.json` (Track 2 writes, Track 3 reads)

One file per anomaly, named exactly `{anomaly_id}.json`, for example `DB-0001.json`.

```json
{
  "schema_version": "1.0",
  "anomaly_id": "DB-0001",
  "status": "cited",
  "model": "qwen2.5-14b-instruct",
  "generated_at": "2026-10-12T06:30:00Z",
  "en": {
    "title": "Preliminary Observation: Possible Wetland Loss at Site A",
    "summary": "A 1.42 ha area within the Wetland Buffer Area shows a persistent transition from water-covered to dry or filled surface, first observed in April 2025 and present in 5 of the last 6 months.",
    "evidence": [
      "Affected area: 1.42 ha",
      "Radar backscatter rose 5.9 dB above the 2023-2024 baseline for the same month",
      "NDWI fell 0.35 below the same-month baseline",
      "First detected 2025-04, persistent in 5 of 6 recent months"
    ],
    "statutory_basis": [
      { "claim": "Developments within the Wetland Buffer Area are subject to assessment requirements under the relevant Town Planning Board guidelines.", "citation_ids": ["TPB12C-p7-c3"] }
    ],
    "recommended_action": "Refer for site inspection and zoning confirmation by the relevant authority.",
    "limitations": "Satellite-derived indicator for screening purposes only. This is not a legal determination of unauthorised development. Findings require site verification by the relevant authority."
  },
  "zh_hant": {
    "title": "初步觀察：A 地點可能出現濕地損失",
    "summary": "...",
    "evidence": ["..."],
    "statutory_basis": [ { "claim": "...", "citation_ids": ["TPB12C-p7-c3"] } ],
    "recommended_action": "...",
    "limitations": "本結果為衛星遙感篩查指標，僅供參考，並非對違例發展的法律認定。相關發現須由主管部門進行實地核實。"
  },
  "citations": [
    {
      "id": "TPB12C-p7-c3",
      "doc": "TPB PG-No. 12C",
      "doc_title_zh": "",
      "page": 7,
      "section": "Assessment requirements",
      "quote": "short verbatim snippet, 40 words maximum",
      "source_url": "https://..."
    }
  ],
  "human_review_required": false,
  "abstain_reason": null,
  "redaction_log": { "items_removed": 0, "types": [] },
  "metrics": { "latency_ms": 8400, "input_tokens": 3120, "output_tokens": 760 }
}
```

**Field rules**

| Field | Type | Required | Rule |
|---|---|---|---|
| `anomaly_id` | string | yes | Must exist in `anomalies_v1.geojson` |
| `status` | string | yes | `cited` \| `abstained_human_review` \| `error` |
| `en`, `zh_hant` | object | yes | Both always present, same structure |
| `*.evidence` | array of strings | yes | 3 to 6 short factual lines, derived from the GeoJSON numbers |
| `*.statutory_basis` | array | yes | Empty array when status is not `cited` |
| `citation_ids` | array of strings | yes | **Every ID must appear in the top-level `citations` array.** No exceptions |
| `citations[].quote` | string | yes | Verbatim from the source, **40 words maximum**, one quote per citation |
| `human_review_required` | boolean | yes | `true` whenever status is not `cited` |
| `abstain_reason` | string or null | yes | Plain-language reason when abstaining, otherwise `null` |
| `redaction_log` | object | yes | Counts only. **Never log the redacted values themselves** |
| `metrics` | object | no | For the cost and sustainability pitch |

**Status rules**
- `cited`: at least one statutory claim with verified citations. Normal display.
- `abstained_human_review`: no relevant clause was retrieved above threshold, or citation verification failed. `statutory_basis` is empty in both languages, `human_review_required` is `true`, `abstain_reason` is filled. The UI shows an amber panel. **This is a correct, successful outcome, not a bug.**
- `error`: generation failed. The UI shows a neutral notice. The brief still exists so the UI never hits a missing file.

**Track 2 must verify in code, not just in the prompt:** every `citation_id` was actually retrieved, and every `quote` string actually appears in the cited chunk. Drop any claim that fails. If nothing survives, abstain.

### 5.3 Overview file (optional, Phase 2): `data/briefs/_overview.json`
Same `en` / `zh_hant` structure plus `totals`: `{ "anomaly_count": 12, "total_area_ha": 18.4, "by_site": { "SITE_A": 9.1 }, "needing_review": 3 }`. Track 3 shows it on an overview tab if it exists, and hides the tab if it does not.

### 5.4 Optional Phase 2 field: `timeseries`
Inside an anomaly's `properties`:
```json
"timeseries": {
  "months": ["2023-01", "2023-02"],
  "vv_db": [-19.4, -19.9],
  "ndwi": [0.33, 0.30]
}
```
All three arrays have the same length. Track 3 charts it if present.

---

## 6. Repo layout

```
Spoonbill/
├── PROJECT_CONTEXT.md              <- this file
├── TRACK_1_REMOTE_SENSING_GIS.md
├── TRACK_2_GENAI_RAG_BACKEND.md
├── TRACK_3_FULLSTACK_STREAMLIT_UI.md
├── DECISIONS.md                    <- log of cross-track changes
├── contract/
│   ├── anomaly.schema.json
│   ├── brief.schema.json
│   ├── sites.json                  <- showcase site polygons and IDs
│   ├── mock_anomalies.geojson      <- Day 1, lets Tracks 2 and 3 start immediately
│   └── mock_briefs/DB-0001.json    <- one of each status: cited, abstained, error
├── data/                           <- the only shared output folder
│   ├── anomalies_v1.geojson
│   ├── chips/
│   └── briefs/
├── track1_gis/                     <- Shabbir only
├── track2_rag/                     <- Ruhan only
└── track3_app/                     <- Bilal only
```

**Validation helper every track runs before committing output:**

```python
import json, jsonschema

def validate(data_path, schema_path):
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)
    jsonschema.validate(data, schema)   # raises on failure
    print(f"OK: {data_path}")
```

Always open files with `encoding="utf-8"` and write JSON with `ensure_ascii=False`, or the Chinese text will be mangled.

---

## 7. Timeline and integration checkpoints

| Day | Date (adjust if needed) | Milestone |
|---|---|---|
| 1 | Mon 6 Oct | Contract frozen. Shabbir publishes `contract/mock_anomalies.geojson` and `contract/sites.json`. Ruhan publishes mock briefs (one of each status). **CP0:** all three can run against mocks |
| 3 | Wed 8 Oct | **CP1:** mock data flows end to end (GeoJSON -> brief -> UI) |
| 4 | Thu 9 Oct | Track 1 ships real `anomalies_v0.1.geojson`. **CP2:** at least 3 real anomalies visible with a real brief |
| 8 | Mon 13 Oct | **CP3: MVP complete.** Real `anomalies_v1.geojson`, all briefs generated, UI and exports working, backup demo video recorded, git tag `v1.0-mvp` |
| 9-12 | Tue 14 - Fri 17 Oct | Phase 2 optional enhancements only. Nothing that touches the contract |
| 13 | Sat 18 Oct | **Code freeze.** Critical bug fixes only. Tag `v1.0-final` |
| 14 | Sun 19 Oct | Rehearsal, final video, submission package |

**Daily ritual (10 minutes, pick a fixed time across both time zones):** each person says what they shipped, what is blocking them, and whether anything touches the contract. Anything that touches the contract gets one line in `DECISIONS.md`, which everyone then pastes into their AI session.

---

## 8. Instructions for the AI assistant reading this file

1. You are working on **one track only**. Build only inside that track's folder. Do not write or modify code in another track's folder.
2. **Treat section 5 as fixed.** Do not rename, remove or retype any contract field. If you believe a change is needed, stop and tell the developer so the team can agree. Adding a new **optional** field is acceptable.
3. **Validate against the schemas** in `contract/` on both input and output. Fail loudly on invalid data rather than silently coercing it.
4. Prefer **free and open-source** libraries. Do not introduce a paid service without asking.
5. Follow the non-negotiable rules in section 4: no personal data, no legal conclusions, cite or abstain, no live external calls in the demo path.
6. All files are UTF-8. Preserve Traditional Chinese correctly; never convert it to Simplified.
7. Build the **minimum runnable version first**, then improve. A working end-to-end path on Day 4 is worth more than a perfect component on Day 10.
8. Write small, readable functions with clear names. The developer is working fast and needs to be able to read and fix what you produce.
9. When something is ambiguous, state the assumption you are making in a comment and keep going. Do not invent new interfaces between tracks.
10. Do not fabricate data, citations, statutory clauses or results. If a value is unknown, use `null` and handle it.
