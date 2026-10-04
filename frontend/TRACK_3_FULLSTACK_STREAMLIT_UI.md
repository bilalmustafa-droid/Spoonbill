# TRACK 3: Full-Stack Streamlit UI and Reporting (Project Spoonbill)

**Owner:** Full-Stack Developer
**Mission:** Deliver the interactive dashboard that judges, government staff and NGOs will actually see: map with anomaly overlays, side-by-side satellite evidence, confidence indicators, bilingual briefs, and one-click PDF/DOCX export. You are also the integrator, so you own the end-to-end demo.

> Assumed calendar (adjust if your deadline differs): Day 1 = Mon 5 Oct 2026, Day 8 = Mon 12 Oct, Day 12 = Fri 16 Oct, Days 13-14 = Sat/Sun 17-18 Oct (freeze and submission buffer).

---

## 0. Dependency map

```
Track 1 (GeoJSON + chips)  ->  Track 2 (brief JSON)  ->  Track 3 (render, export, demo)
```

You are never blocked if you build against the mock files from Day 1. Your rule: **the UI only reads files in `data/`, it never calls Earth Engine or an LLM directly** in the default demo path. That makes the demo fast and crash-proof.

## 1. Shared data contracts (v1, frozen on Day 1)

**From Track 1:** `data/anomalies_v1.geojson` (FeatureCollection in EPSG:4326) with `properties`:
`anomaly_id, site_id, centroid_lon, centroid_lat, area_ha, baseline_vv_db, current_vv_db, delta_vv_db, baseline_ndwi, current_ndwi, delta_ndwi, first_detection_date, persistence_count, persistence_total, confidence_tier (high | medium | low), zone_hint (WCA | WBA | OTHER | UNKNOWN), chip_before_png, chip_after_png`. Chips live in `data/chips/`.

**From Track 2:** `data/briefs/{anomaly_id}.json` with `status` (`cited`, `abstained_human_review`, `error`), `en` and `zh_hant` blocks (`title, summary, evidence[], statutory_basis[], recommended_action, limitations`), `citations[]` (`id, doc, page, section, quote`), `human_review_required`, `abstain_reason`.

The UI must handle every status gracefully (an abstained brief shows an amber "Human review required" panel, an error shows a neutral message, never a stack trace).

## 2. Suggested open-source stack

| Need | Primary | Notes |
|---|---|---|
| App framework | `streamlit` | Multipage optional, single page is faster |
| Map | `folium` + `streamlit-folium` | Alternative: `leafmap`, or `pydeck` |
| Geo handling | `geopandas`, `shapely` | |
| Charts | `plotly` or `altair` | |
| Image comparison | Two `st.image` columns for MVP; `streamlit-image-comparison` for the slider (Phase 2) | |
| PDF export | `WeasyPrint` (HTML to PDF) or `reportlab` | **Needs a CJK font** such as Noto Sans CJK TC bundled in the repo |
| DOCX export | `python-docx` | Set an East Asian font explicitly or Chinese may render as boxes |
| Tests | `pytest`, `streamlit.testing.v1.AppTest` | |
| Deployment | Streamlit Community Cloud, or Docker on any host | Always keep a local run script as fallback |

## 3. Screen design (build this, nothing more, in Phase 1)

1. **Sidebar:** language toggle (English / 繁體中文), site filter, confidence filter (default high and medium), date range, "Show low confidence" toggle.
2. **Top strip:** 3 to 4 headline metrics: number of anomalies, total hectares, number needing human review, last data date.
3. **Main left:** Folium map with base layer (satellite tiles plus OpenStreetMap), anomaly polygons coloured by confidence tier, tooltips (ID, area, zone), WCA/WBA overlay if Track 1 provides it, and click-to-select.
4. **Main right (detail panel for the selected anomaly):** confidence badge and persistence meter (for example "5 of 6 months"), metrics table (baseline vs. current VV and NDWI), before/after chips side by side, the brief in the chosen language with citations expandable, and the Export buttons.
5. **Footer:** methodology summary (3 lines) and disclaimer: "Satellite-derived indicator. Not a legal determination."

---

## PHASE 1: MUST-HAVE CORE SOLUTION (Days 1-8, high priority)

### Day 1 (Mon 5 Oct): Skeleton on mocks
- [ ] Freeze the contracts with Tracks 1 and 2 (15 minute call). Ask both for mock files today.
- [ ] Create repo structure: `app.py`, `ui/` (components), `export/`, `data/`, `assets/fonts/`, `requirements.txt`, `run.sh`. Own the monorepo layout and branch rules (each owner works in their own folder, small PRs to `main`).
- [ ] Streamlit app that loads the mock GeoJSON and shows polygons on a Folium map.
- **Checkpoint CP0:** `streamlit run app.py` shows a map with mock anomalies on all three laptops.

### Day 2 (Tue 6 Oct): Data layer and map interaction
- [ ] `data_access.py`: functions `load_anomalies()`, `load_brief(anomaly_id)`, `load_chip(path)` with schema validation and cached via `st.cache_data`. No UI code reads files directly.
- [ ] Colour polygons by tier, tooltips, click-to-select via `streamlit-folium` return value (`last_object_clicked` or feature properties).
- [ ] Sidebar filters working.
- **Validation:** selecting a polygon updates the detail panel; filters change what is drawn.

### Day 3 (Wed 7 Oct): Detail panel and brief rendering
- [ ] Detail panel: metrics table, confidence badge, persistence meter.
- [ ] Render `en` or `zh_hant` brief by language toggle, with the `statutory_basis` linked to `citations` (expander showing document, page and quote).
- [ ] Status handling: `cited` normal, `abstained_human_review` amber panel with the reason, `error` neutral notice.
- **Checkpoint CP1 (Day 3):** full mock path works: GeoJSON + mock brief -> map -> panel.
- **Validation:** all three statuses render without exceptions (test with three mock briefs).

### Day 4 (Thu 8 Oct): Real data integration (v0.1)
- [ ] Swap in Track 1's `anomalies_v0.1.geojson` and Track 2's first briefs.
- [ ] Log every contract mismatch to the owner the same day (use a shared `INTEGRATION_ISSUES.md`).
- **Validation:** at least 3 real anomalies display end to end with real chips and a real brief.

### Day 5 (Fri 9 Oct): Evidence panel and top metrics
- [ ] Side-by-side before/after chips (Sentinel-2 RGB and VV), captions with dates, and a small bar chart of baseline vs. current VV and NDWI.
- [ ] Headline metric strip and the footer disclaimer.
- [ ] Handle missing chips with a placeholder, not a crash.
- **Validation:** every high-tier anomaly shows two chips and the chart.

### Day 6 (Sat 10 Oct): Export v1 (PDF and DOCX)
- [ ] Build one HTML or document template (logo/title, anomaly ID, location, metrics table, before/after images, brief text in selected language, citations list, disclaimer, generated-at timestamp).
- [ ] PDF through WeasyPrint (or reportlab) with bundled Noto Sans CJK TC; DOCX through `python-docx` with East Asian fonts set.
- [ ] Download buttons via `st.download_button` (no temp-file leaks; generate in memory with `BytesIO`).
- **Validation:** exports open correctly in Word and a PDF viewer; Chinese characters render properly (no boxes); an abstained brief exports with the "human review required" banner.

### Day 7 (Sun 11 Oct): Hardening and demo path
- [ ] Add a **demo mode**: one button or env flag that preloads the best 3 anomalies and a scripted click path.
- [ ] Performance: map loads in under 3 seconds with cached data; large GeoJSON simplified (`shapely.simplify`) if needed.
- [ ] Add AppTest smoke tests: app starts, selecting an anomaly works, language toggle works, exports return non-empty bytes.
- [ ] Basic accessibility: readable contrast, colour-blind-safe tier colours with icons or labels, not colour alone.
- **Validation:** all smoke tests pass; a teammate who has never seen the app can complete the demo path in under 2 minutes.

### Day 8 (Mon 12 Oct): Integrate v1 and freeze MVP
- [ ] Load `anomalies_v1.geojson` and all `briefs/*.json`. Run the full flow for every anomaly once and record failures.
- [ ] Deploy (Streamlit Community Cloud or Docker) and record a **backup demo video** (3 to 5 minutes).
- [ ] Write the root `README.md` (setup, run, data folder layout, how to refresh data).
- **Checkpoint CP3:** fresh clone, one command, working demo with real data on a clean machine; MVP tag `v1.0-mvp` in git.
- **Validation:** the checklist in "Definition of done" below passes.

---

## PHASE 2: ADVANCED / OPTIONAL ENHANCEMENTS (Days 9-12, low priority, non-blocking)

| Day | Task | Output |
|---|---|---|
| 9 | **Swipe/slider before-after comparison** and time-series chart per anomaly (uses Track 1's optional `timeseries`); optional secondary optical-brightness confidence tier display (plastic-lined ponds) if Track 1 ships `optical_brightness_flag` | Richer evidence panel |
| 10 | **Custom theme and CSS** (`.streamlit/config.toml`, branded header, tier badges), dark/light mode check | Polished look |
| 11 | **Portfolio view:** overview tab with totals by site, cumulative area lost (Track 1's `ledger.json`), and the overview brief from Track 2; batch export of all high-tier anomalies into one PDF | Executive page and batch report |
| 12 | **Automated system carbon footprint calculator:** read `energy_log.json` and `runtime_log.json` from Tracks 1 and 2, show estimated energy and CO2e per anomaly processed, with the assumptions listed | Sustainability panel for the pitch |

Days 13-14: code freeze, rehearse the pitch with the live app, final video, submission package. No new features.

---

## Integration checkpoints (you own these)

| Checkpoint | Day | Pass condition |
|---|---|---|
| CP0 | 1 | All three can run the mock data in the app |
| CP1 | 3 | Mock GeoJSON + mock briefs render fully, including all statuses |
| CP2 | 5 | Real v0.1 data and first real briefs visible in the UI |
| CP3 | 8 | Fresh clone runs the full real-data MVP; backup video recorded |
| CP4 | 12 | All Phase 2 items that were attempted are merged or cleanly switched off |
| Freeze | 13 | Tag `v1.0-final`, only critical bug fixes afterwards |

## Definition of done (MVP, Day 8)

- [ ] App starts with one command and loads in under 5 seconds on a laptop.
- [ ] Map shows all anomalies with tier colours and working filters.
- [ ] Selecting an anomaly shows metrics, before/after chips, and a bilingual brief with citations.
- [ ] Abstained and error states look intentional.
- [ ] PDF and DOCX export work in both languages with correct Chinese characters.
- [ ] No personal data anywhere in the UI or exports; disclaimer visible.
- [ ] Backup demo video exists.

---

## RISK MANAGEMENT AND FALLBACKS

| # | Risk | Likelihood | Impact | Mitigation | Fallback |
|---|---|---|---|---|---|
| 1 | Upstream data is late or malformed | High | High | Build on mocks Day 1, validate with `jsonschema`, log mismatches immediately | Keep the mock-plus-v0.1 dataset as the demo data; show a "sample data" label honestly |
| 2 | Streamlit and Folium are slow or reload on every click | Medium | Medium | `st.cache_data`, simplify geometries, use `returned_objects` to limit what the map returns | Use `leafmap` or `pydeck`; or reduce to a selectbox of anomalies plus a static map of the selected one |
| 3 | PDF export fails (fonts, WeasyPrint system dependencies) | High | Medium | Bundle Noto Sans CJK TC, test on Day 6 on all OSs | Use `reportlab` with the bundled font; or produce DOCX only and convert with LibreOffice headless; last resort: export HTML with print stylesheet |
| 4 | DOCX Chinese text shows as boxes | Medium | Medium | Set `w:eastAsia` font on every run | Export Chinese briefs as PDF only, and DOCX in English |
| 5 | Deployment issues (memory limits, GDAL/geopandas install failures) | Medium | High | Deploy a test version on Day 4, pin versions | Docker image, or run locally from a laptop for the live demo with the recorded video as backup; avoid heavy dependencies (use `shapely` + `json` if `geopandas` fails) |
| 6 | Live pipeline calls (GEE or LLM) fail during the demo | Medium | Very high | Default path reads cached files only | "Demo mode" with pre-generated outputs; never call external services live on stage |
| 7 | Integration bugs discovered too late | Medium | High | CP1, CP2 and CP3 gates; one end-to-end run per day from Day 4 | Freeze scope, cut Phase 2 entirely, and spend the time on stability and the pitch |
| 8 | Vibecoded UI breaks when edited by AI repeatedly | Medium | Medium | Small components, tests on core flows, git tag after each working state | Roll back to the last tag; avoid large refactors after Day 8 |
| 9 | Personal data or legal overreach in the output | Low | Very high | Disclaimer on every screen and export; no ownership fields; do not call anything "illegal" | Strip free-text fields from exports; show metrics and citations only |
| 10 | Judges use a different device, language, or poor network | Medium | Medium | Responsive layout check, bundle assets locally, no CDN dependencies for fonts or icons | Hosted demo URL plus the recorded video and a PDF sample report in the submission |

**Definition of done for this track:** the deployed (or locally runnable) app passes the MVP checklist with real data, exports are verified in Word and PDF viewers, the backup video exists, and the submission package (README, video, sample exports) is assembled by Day 13.
