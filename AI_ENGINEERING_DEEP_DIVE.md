# Project Spoonbill — Full Technical Deep Dive

Prepared for hackathon finals defense. Every claim in this document was checked against the actual code and, where possible, actually executed and observed during integration — not inferred from file names or assumed from convention. Where a number is measured, it says "measured." Where a capability does not exist, it says so directly instead of being implied. This document is long on purpose: it is meant to let you answer any question a judge throws at you by pointing at a specific function, not a slide.

---

## PART 1 — EXECUTIVE TECHNICAL SUMMARY & ARCHITECTURE OVERVIEW

### 1.1 Problem statement

Hong Kong's planning framework commits to "no net loss of wetland" for the Deep Bay / Mai Po fishpond belt, part of the Sustainable Northern Metropolis development. That commitment has no automated enforcement mechanism — detecting wetland-to-land conversion today depends on manual site visits or ad hoc complaint response. Spoonbill is a screening system: it watches satellite imagery for persistent, physically-evidenced land-cover change, and for every flagged location, automatically produces a citation-backed written brief explaining which Hong Kong planning guideline the change may be relevant to, so a human officer has a starting point instead of a blank page.

It is explicitly **not** a legal determination system. Every output carries a disclaimer to that effect, and the system is built around a "cite or abstain" principle: if it cannot find a verifiable statutory basis for a claim, it says so rather than asserting one.

### 1.2 Three-track architecture

The project was built as three independently-developed tracks that converge on two shared file formats (a "data contract"):

```
TRACK 1                          TRACK 2                           TRACK 3
Remote sensing / GIS             GenAI / RAG                       UI / Reporting
(spatial/)                       (track2_rag/)                     (frontend/track3_app/)

Sentinel-1 (SAR, radar)    -->   data/anomalies_v1.geojson    -->  Streamlit dashboard
Sentinel-2 (optical)             (frozen schema, Track 1          (map, detail panel,
via Google Earth Engine          writes, Tracks 2+3 read)         brief viewer, PDF/DOCX
                                        |                          export)
                                        v
                                  Gemini 2.x + retrieval
                                  over a chunked corpus
                                  of HK planning PDFs
                                        |
                                        v
                                  data/briefs/{anomaly_id}.json
                                  (frozen schema, Track 2
                                  writes, Track 3 reads)
```

The two JSON artifacts (`data/anomalies_v1.geojson` and `data/briefs/{id}.json`) are the **only** contract between tracks. Track 3 never imports Track 1 or Track 2 code directly — it only reads files matching a JSON Schema. This is a deliberate decoupling: any track can be rewritten entirely as long as its output still validates.

### 1.3 Why this is a legitimate "data pipeline," not a live request/response system

A critical architectural decision, made explicitly partway through integration: **nothing in this system runs automatically or on a request-triggered basis in the demo configuration.** The backend (`scripts/run_pipeline.py`) is a batch job, triggered by a human, that:

1. Loads the current anomaly file.
2. For any anomaly without a cached brief, calls the live Gemini + retrieval pipeline (observed to take **~4 minutes per call**, measured directly with a live API call during integration — see Part 5).
3. Writes everything to `data/`.

The Streamlit UI then only ever reads static files from `data/`. It never calls Earth Engine or Gemini itself. This means the live, user-facing demo has **zero external API dependency at runtime** — it will work on a conference wifi connection that only has to serve local map tiles, with one caveat (ESRI basemap tiles still need internet — documented honestly in the UI's own tiles_note string).

There is also an optional, parallel FastAPI service (`track2_rag/main.py` + `track2_rag/api/`) that exposes the same data live over HTTP, for anyone who wants request/response semantics instead of static files. It is not required for the Streamlit demo and is documented separately in `API.md`.

### 1.4 Tech stack and rationale

| Layer | Technology | Version (pinned/observed) | Why this, specifically |
|---|---|---|---|
| Satellite data access | Google Earth Engine Python API (`earthengine-api`) | — | Free tier, hosts analysis-ready Sentinel-1/2 collections with no need to download raw scenes; the alternative (STAC + Planetary Computer) would require implementing cloud masking and compositing from scratch |
| Change detection | NumPy, SciPy (`scipy.ndimage`), Shapely | numpy 2.5.1, scipy 1.18.1 | Standard scientific Python stack; `scipy.ndimage.label`/`binary_erosion`/`center_of_mass` cover connected-component and morphological operations without adding `scikit-image` as a dependency |
| Embedding model | `BAAI/bge-m3` via `sentence-transformers` | sentence-transformers 6.1.0 | Open-weight, strong multilingual (critical — the corpus and briefs are bilingual EN/zh-Hant), free, runs locally with no per-call embedding API cost |
| Vector store | ChromaDB, `PersistentClient` | chromadb 1.5.9 | Embedded (no separate server process to deploy), persists to disk, trivial to set up for a hackathon timeline versus standing up Pinecone/Weaviate infrastructure |
| Sparse retrieval | `rank_bm25` | rank-bm25 0.2.2 | Present in the codebase but **not actually called in the live retrieval path** — documented honestly in Part 4.2, this is a real gap, not a feature |
| LLM | Google Gemini (`google-generativeai`) | google-generativeai 0.8.6 (now a deprecated package per its own `FutureWarning`; see Part 5.5) | Free tier, native structured-JSON output mode (`response_mime_type: "application/json"`), good bilingual generation |
| PDF parsing | PyMuPDF (`fitz`) | — | Fast, page-accurate text extraction, used once offline to build the corpus, not in the live path |
| Schema validation | `jsonschema` (Draft 2020-12) | jsonschema 4.26.0 | Industry-standard JSON Schema implementation, used identically on both the write side (Track 1/2 scripts) and the read side (Track 3 loader) |
| Data modeling | Pydantic v2 | pydantic 2.14.0 | Stricter than JSON Schema alone — this is where the *actual* contract enforcement happens in the UI, see Part 1.6 |
| Backend API (optional) | FastAPI + Uvicorn | fastapi 0.136.3 | Only used for the optional live-query path; async-capable, automatic OpenAPI docs, minimal boilerplate |
| Frontend | Streamlit + `streamlit-folium` | streamlit 1.65.0 | Fastest path from a Python data pipeline to an interactive, mappable dashboard without writing a separate JS frontend; acceptable because this is a screening tool for internal/judge use, not a public-facing product |
| Mapping | Folium (Leaflet.js wrapper) | — | Renders real polygon geometry with per-tier styling, click-to-select, with Esri World Imagery as the basemap |
| Export | `reportlab` (PDF), `python-docx` (DOCX) | — | Both exporters render from one shared `report_model.py` so the two output formats can never drift apart in content |

### 1.4b Data flow, expanded — the satellite side

```
Google Earth Engine (cloud-hosted, no local download)
        |
        | filterBounds / filterDate / instrumentMode / orbit pass / polarization
        v
COPERNICUS/S1_GRD (SAR)              COPERNICUS/S2_SR_HARMONIZED (optical)
        |                                     |
        | 3x3 focal median despeckle          | SCL cloud mask + CLOUDY_PIXEL_PERCENTAGE<40
        v                                     v
monthly VV composite (dB)            monthly NDWI composite
        |                                     |
        +------------------+------------------+
                           |
                 group by calendar month,
                 median across 2023-2024
                           |
                           v
            per-calendar-month baseline climatology
            + ndwi_annual_median (wet-baseline gate)
                           |
        for each month in current window (21 months):
                           v
     flag = (VV_m - VV_base > 3.0dB) AND (NDWI_m - NDWI_base < -0.25)
            AND (NDWI_annual_median > 0.0)
                           |
                           v
     persistence filter: >=4 of last 6 flagged, AND both of latest 2
                           |
                           v
     morphological opening (remove <20m speckle)
                           |
                           v
     vectorise (reduceToVectors) -> per-polygon zonal stats
     (baseline/current VV, baseline/current NDWI, area, centroid,
      first-flagged-month percentile)
                           |
                           v
     schema validation (contract/anomaly.schema.json) -- loud failure
     on violation, nothing written if invalid
                           |
                           v
     data/anomalies_v1.geojson
```

### 1.4c Data flow, expanded — the brief generation side

```
data/anomalies_v1.geojson (one feature)
        |
        v
cache check: data/briefs/{anomaly_id}.json already exists?
   |-- yes --> read from disk, return immediately (no LLM call, no network)
   |-- no, continue below
        v
query = f"Development, wetland filling, fishpond conversion in {zone_hint} area
          assessment requirements"
        |
        v
embed query with BAAI/bge-m3 (same model used to embed the corpus)
        |
        v
Chroma dense similarity search, collection "statutory_rules", k=3
        |
        v
3 retrieved {chunk_id, text, metadata} dicts
   |-- zero retrieved? --> abstain immediately, no LLM call
        v
prompt = role framing + anomaly facts + 3 chunk texts (labelled by chunk_id)
         + explicit field-by-field JSON schema instructions
         + "cite only from provided chunks, verbatim quotes <=40 words"
        v
Gemini generate_content(prompt, response_mime_type="application/json")
        |
        v
strip markdown code fences, json.loads()
        |
        v
cite-or-abstain guardrail: for each claimed citation, check
  (a) chunk_id in retrieved set   (b) quote[:20] substring-matches chunk text
   |-- all citations fail --> force status = abstained_human_review
        v
PDPO redaction pass on summary/evidence (HKID/email/phone regex)
        |
        v
write data/briefs/{anomaly_id}.json
        |
        v
brief_adapter.adapt_brief_for_frontend() reshapes citation field names,
  statutory_basis shape, and the hardcoded prompt-leaked timestamp
  (applied by scripts/run_pipeline.py, not generator.py itself)
        |
        v
Pydantic Brief model validates on every UI read -- ContractError if not
```

Any exception at any point in this chain (network failure, malformed JSON, missing key) is caught by a single outer `try/except` and converted to a hardcoded, schema-valid `abstained_human_review` object rather than propagating — this is why the diagram above has no "error" exit branch drawn separately from the abstain branches: in this design, a technical failure and a genuine "insufficient evidence" case both resolve to the same user-facing state.

### 1.5 How "RAG" actually maps onto this codebase

To be precise about terminology, since judges will probe this exact phrase: this is **retrieval-augmented generation** in the textbook sense — retrieve relevant source text, then condition generation on it — but it is **not** a conversational RAG chatbot. There is no multi-turn memory, no query rewriting, no re-ranking step. The pipeline per anomaly is:

```
anomaly properties (zone_hint, area_ha, delta_vv_db, delta_ndwi, first_detection_date)
        |
        v
query string built from a fixed template (see Part 4.2)
        |
        v
dense vector search over 231 pre-chunked statutory text segments (k=3)
        |
        v
prompt = anomaly facts + 3 retrieved chunks + explicit JSON schema instructions
        |
        v
Gemini generate_content(..., response_mime_type="application/json")
        |
        v
programmatic citation-verification guardrail (string match against retrieved text)
        |
        v
PDPO redaction pass (regex)
        |
        v
data/briefs/{anomaly_id}.json
```

Every step of this is detailed with exact code references in Part 4.

### 1.6 The data contract: the single most important architectural concept to defend

Three things read and write `data/anomalies_v1.geojson` and `data/briefs/{id}.json`:

1. **`contract/anomaly.schema.json`** and **`contract/brief.schema.json`** — JSON Schema, Draft 2020-12. Structural validation: field presence, types, enums, regex patterns (e.g., `anomaly_id` must match `^DB-\d{4}$`).
2. **`frontend/track3_app/core/models.py`** — Pydantic v2 models. This is **stricter** than the JSON Schema in several places and is the layer that actually gates what the UI will render. A file can pass the JSON Schema and still be rejected by Pydantic (this happened during integration — see the worked example in Part 2.6).
3. **`tools/validate_contract.py`** — a standalone CLI, independent of the running app, for checking a file against schema outside of Streamlit's own loader.

A genuinely important fact discovered during integration and worth stating proactively to judges: **the JSON Schema and the Pydantic model are not automatically kept in sync.** They are two independently-written files that happen to agree today because they were reconciled by hand. This is a real, acknowledged architectural risk, logged in `INTEGRATION_ISSUES.md`. Being able to say this plainly, with the specific example of where it already bit the project (six SAR/NDWI fields that the written kickoff brief assumed were nullable, but the actual committed schema does not allow null on — see Part 2.6), is a stronger answer than claiming the contract is airtight.

---

## PART 2 — MODULE-BY-MODULE CODE WALKTHROUGH

### 2.1 `spatial/` — Track 1, Remote Sensing

#### 2.1.1 `spatial/step2.py` — the real detector

This is the methodologically-faithful implementation of the detection rule specified in `spatial/TRACK_1_REMOTE_SENSING_GIS.md`. It is the only script in the repo that attempts the full SAR+optical fusion design the data contract assumes.

**Configuration constants (top of file):**
- `SITES`: a dict of two showcase site boxes, `mai_po_4p3ha` at `(114.0515, 22.4930)` and `san_tin_9ha` at `(114.0604, 22.5085)`, each with `SITE_HALF_LON = 0.010` and `SITE_HALF_LAT = 0.007` (so each site box is 0.02° × 0.014°, roughly 2 km × 1.5 km).
- `BASELINE_WINDOW = ("2023-01-01", "2024-12-31")` — two full years used to build a per-calendar-month climatology.
- `THRESHOLDS`: `delta_vv_db=3.0`, `delta_ndwi=-0.25`, `min_area_ha=0.1`, persistence rule `">=4 of last 6 months and flagged in latest 2"`.

**Function-by-function:**

- **`month_starts(start, end)`** — pure date arithmetic, returns `(month_start, next_month_start, calendar_month_number)` tuples for every whole calendar month in a range. No external calls; this is the scaffolding every other time-series function iterates over.

- **`detect_orbit_pass(ee, aoi, current_end)`** — **this function exists because of a real, diagnosed bug found during integration.** The script originally hardcoded Sentinel-1's `DESCENDING` orbit pass. A real run against Deep Bay returned **zero scenes for the entire baseline and current window**, because the actual usable Sentinel-1 coverage for this AOI is on the `ASCENDING` pass (confirmed by a direct scan: `DESCENDING=0 scenes, ASCENDING=207 scenes`). The fix queries scene counts for both orbit passes over the full date range at startup and uses whichever has data, rather than assuming. This is demonstrated, not theoretical — the before/after log output is preserved in the git history of this file.

- **`s1_vv_monthly(ee, aoi, start, end)`** — builds one monthly VV-polarization Sentinel-1 composite: filters `COPERNICUS/S1_GRD` by bounds, date, `instrumentMode == "IW"`, the detected orbit pass, and VV polarization presence; applies a 3×3 focal median despeckle filter per scene; takes the per-pixel median across the month. Returns `(None, 0)` if zero scenes matched, which downstream code treats as "no data this month," not an error.

- **`s2_ndwi_monthly(ee, aoi, start, end)`** — builds one monthly NDWI composite from `COPERNICUS/S2_SR_HARMONIZED`: masks out SCL classes 3, 8, 9, 10 (cloud shadow, cloud medium/high probability, cirrus), filters `CLOUDY_PIXEL_PERCENTAGE < 40`, computes `normalizedDifference(["B3","B8"])`, medians across the month.

- **`build_baseline_climatology(ee, aoi)`** — for each of the 24 baseline months, builds that month's VV and NDWI composite, then groups composites by calendar month number (e.g., all Januaries together) and takes the per-calendar-month median across the 2 years available. Also builds `ndwi_annual_median`, the median NDWI across the entire baseline period (not per-month) — this is the "was this pixel ever wet" gate in the fusion rule.

- **`compute_monthly_flag(ee, vv_cur, ndwi_cur, vv_base, ndwi_base, ndwi_annual_median)`** — implements the exact fusion rule from the design doc:
  ```
  flag = (VV_current - VV_baseline > 3.0 dB)
         AND (NDWI_current - NDWI_baseline < -0.25)
         AND (NDWI_annual_median > 0.0)
  ```
  The third term is what prevents a parking lot or a road (never wet to begin with) from ever being flagged — it restricts detection to locations with a genuine baseline-wet signature.

- **`run_site_detection(ee, site_id, site_cfg, current_end)`** — the orchestration function for one site. Builds the climatology, then for every month in the current window (default `2025-01-01` to `2026-10-01`, 21 months), computes that month's flag image if both sensors have usable data, and accumulates a list of per-month flag images plus a parallel list of `(month_start, vv_image, ndwi_image)` for "usable" months only. Requires at least 6 usable months or the site is skipped entirely.

  **Diagnostics added during integration, not in the original design**: per-month flagged hectares (printed via `ee.Image.pixelArea().updateMask(flag).reduceRegion(sum)`), and persistent-area-before-and-after-morphological-opening. These were added specifically because the first real run returned 0 features with no way to tell *why* — these print statements turned "0 features, no explanation" into "0.000 ha survive persistence filtering, here's the per-month trend," which is the difference between an undiagnosed null result and a defensible one.

  Persistence logic: `flag_sum = sum of flags over the last 6 usable months`; `latest_and = AND of the flags in the last 2 usable months`; `persistent = flag_sum.gte(4).And(latest_and)`. Then a morphological opening (`focalMin(20m).focalMax(20m)`) removes isolated single-pixel speckle.

- **`polygon_centroid_and_area_ha(geometry)`** — pure Python, Shapely-based. Computes centroid and an *approximate* area using an equirectangular degree-to-meter conversion at the AOI's latitude. Explicitly documented in the code as an approximation adequate for a 0.1 ha minimum-mapping-unit filter, not a geodesically exact calculation (that distinction matters — see Part 2.1.2 and the Q&A on area computation methods).

- **`build_feature(anomaly_id, raw, current_months, min_area_ha)`** — assembles one GeoJSON feature from a detected polygon's zonal statistics. Rejects (returns `None`, does not fabricate) any polygon under the minimum area, or with incomplete zonal stats (any of baseline/current VV/NDWI missing). `confidence_tier` is derived mechanically: `"high"` if `persistence_count >= 5`, else `"medium"` — matching the documented business rule exactly.

- **`generate_chips(ee, anomaly_id, geometry, current_end, out_dir)`** — best-effort before/after true-colour PNG generation via `getThumbURL`, cropped to a padded bounding box around the detected polygon. Returns `(None, None)` on failure rather than raising, so one failed chip does not abort the whole run.

- **`validate_and_write(feature_collection, out_dir)`** — **validates the assembled output against `contract/anomaly.schema.json` before writing anything to disk**, using the same `jsonschema.Draft202012Validator` pattern as everywhere else in the project. On any violation, it prints every error and exits non-zero instead of writing a partially-invalid file.

- **`self_test(out_dir)`** — builds one synthetic, explicitly `"synthetic": true`-flagged feature and runs it through the real validation/write path. This exists specifically so the non-Earth-Engine parts of the script (schema compliance, file writing) can be proven correct without needing live Earth Engine credentials — used during integration to confirm the export logic worked before a teammate with GEE access ran the real thing.

**Observed real-world result**: a live run against both site boxes, after the orbit-pass fix, successfully pulled real data (confirmed healthy scene counts, 2-7 scenes per sensor per month) but returned **0 persistent detections**. Diagnostic output showed per-month flagged area fluctuating between 0 and ~4 ha (different pixels each month — consistent with SAR speckle noise or genuine seasonal variation, not a stable converted parcel), and the overlap satisfying the full persistence rule was 0.000 ha at one site and 0.018 ha (roughly 2 pixels, below the morphological opening's minimum preservable patch size) at the other. This is treated throughout the project documentation as a **real, diagnosed negative result**, not a failure — the leading hypothesis for *why* (recorded honestly, not yet re-tested) is that the wetness gate uses NDWI rather than MNDWI, and algae/floating vegetation on a healthy pond can push NDWI negative, incorrectly excluding real ponds before the fusion rule ever runs — the same failure mode independently diagnosed and fixed in `ruhan code.py` (next section).

#### 2.1.2 `spatial/ruhan code.py` — the working optical detector

A second, independent, optical-only detector. Despite the generic filename, this is the one component in the project that has produced a real, visually confirmed before/after change signal from real imagery (verified directly during integration by reading the cropped output images, not just trusting pixel statistics).

Key technical points:
- **MNDWI over NDWI** for the water gate: `MNDWI = (B3 - B11) / (B3 + B11)` (green vs. shortwave infrared) instead of `NDWI = (B3 - B8) / (B3 + B8)` (green vs. near infrared). The code's own in-file changelog documents why: algae and floating vegetation on a fishpond raise near-infrared reflectance, pushing NDWI negative even though the pond is genuinely full of water — SWIR is absorbed by water regardless of what's growing on the surface, so MNDWI does not have this false-dry failure mode. This is the exact fix the `step2.py` detector has not yet received.
- **Annulus-based local background correction**: rather than comparing a pixel directly to a fixed global threshold, the script computes a local background mean using two `focalMean` calls (a 600 m circle minus a 200 m circle, combined via area-weighted subtraction: `annulus = outer * (Ro²/(Ro²-Ri²)) - inner * (Ri²/(Ro²-Ri²))`), so a large real anomaly does not partially cancel its own detected signal by contaminating its own local-background estimate — the inner exclusion radius specifically prevents this.
- **Three independent change cues**, OR-combined: MNDWI drop (primary), NDWI drop (secondary, kept for comparison diagnostics), and visible-brightness increase (catches plastic/tarp-covered conversions where the water signal alone is ambiguous).
- Produces before/after/anomaly/flags/watergate diagnostic PNG panels per site/incident into `spatial/spoonbill_outputs_v2/`, at 1000×700 pixels, confirmed by direct measurement (`cv2.imread(...).shape`).

This script is explicitly never imported, edited, or executed by any other part of the pipeline — it is read-only reference output. A later integration attempt to crop and re-display pieces of this script's output imagery in the UI was built, tested, visually verified to produce a genuinely convincing before/after signal, and then **deliberately reverted** at the project owner's explicit request, because pairing real imagery with the three synthetic demonstration anomalies' invented coordinates risked a judge finding a verifiable mismatch between claimed location and shown imagery. The decision to revert working code in favor of a safer, more honest state is itself a defensible engineering story — see Q13.

### 2.2 `track2_rag/` — Track 2, GenAI/RAG Backend

#### 2.2.1 `track2_rag/main.py` — the FastAPI host

- Constructs `app = FastAPI(...)`, wide-open CORS (`allow_origins=["*"]`, acceptable for a local-only demo, explicitly not production configuration).
- **Import-time crash prevention**: the `BriefGenerator` constructor (which transitively imports `google.generativeai`) is wrapped in a `try/except` at **import time**, not just construction time. Before this fix, a missing dependency crashed the entire process before any route could even register — the fix means the app always starts, and `/health` reports what's missing instead of the whole server being unreachable.
- `SPOONBILL_OFFLINE=1` environment variable: when set, skips `BriefGenerator` construction entirely (no embedding model load, no Chroma touch), so offline mode boots fast and never attempts an outbound call.
- `fetch_or_generate_brief(anomaly_id)` — the shared core logic behind both the legacy `GET /api/v1/briefs/{id}` route and the new `POST /api/brief/{id}` route (zero duplicated logic). Order of checks: disk cache hit (always safe, any mode) → anomaly exists? (404) → offline mode with no cache? (503, offline-specific message) → generator unavailable? (503 with the actual init error) → live generation, write-through cache.

#### 2.2.2 `track2_rag/rag/retriever.py` — `HybridRetriever`

- Loads `chunks.json` (231 pre-chunked statutory text segments).
- Builds a `BM25Okapi` sparse index over `chunk["text"].split()` — **in `__init__` only**.
- Loads `BAAI/bge-m3` via `SentenceTransformer`, embeds every chunk, stores in a `chromadb.PersistentClient` collection named `"statutory_rules"` persisted at `track2_rag/chroma_db/` (confirmed on disk: `chroma.sqlite3` + HNSW index segment files, ~6.1 MB).
- **`retrieve(query, k=3)` queries only the dense Chroma index.** The BM25 index built in `__init__` is never referenced inside `retrieve()`. This is a factual, verifiable statement about the code, not a design choice being second-guessed — the class is named `HybridRetriever` and is described as hybrid in project documentation, but the live retrieval path is dense-only. Documented honestly in Part 4.2 and Q3.

#### 2.2.3 `track2_rag/rag/generator.py` — `BriefGenerator`

The core generation logic. Walked through in full in Part 4 (Gen AI implementation) since this is the module judges will ask about most. Summary of structure: API key resolution (env var, falling back to manual parsing of `track2_rag/.env`), `genai.configure()`, model instantiation, `generate_brief(anomaly)` which builds a query, retrieves 3 chunks, constructs a prompt, calls Gemini with JSON response mode, runs a programmatic citation-verification guardrail, runs a PDPO redaction pass, and on **any** exception anywhere in that pipeline, catches it and returns a well-formed `abstained_human_review` brief rather than propagating the error or returning malformed data.

#### 2.2.4 `track2_rag/rag/ingest.py` — corpus builder

Standalone, offline-only script. Walks `track2_rag/corpus/raw/*.pdf`, extracts text page-by-page with PyMuPDF (`fitz`), writes one `chunks.json` entry per page: `{chunk_id, doc, page, text}`. **Chunking granularity is one full PDF page per chunk** — not semantic chunking, not fixed-token-window chunking, not recursive character splitting. This is a deliberate simplicity choice for a hackathon timeline, with a real, observed consequence documented in Part 4.1.

#### 2.2.5 `track2_rag/batch_generate.py`

A CLI for bulk-generating briefs for every anomaly in a GeoJSON file, validating each against `brief.schema.json` via `jsonschema` before writing. Superseded for day-to-day use by `scripts/run_pipeline.py`, which also applies the frontend-contract reshaping step (Part 2.2.7) that this script does not.

#### 2.2.6 `track2_rag/api/` — the integration layer

Four modules added during integration, none of which existed when the three tracks were first joined:

- **`anomalies_store.py`** — loads and caches the anomaly GeoJSON (module-level cache, loaded once, never re-read per request), with an explicit split between "missing file" (cached as a degraded state, surfaced as HTTP 503) and "malformed file" (lets the exception propagate loud, surfaced as 500) — a deliberate implementation of "fail loud on bad data, degrade gracefully on missing services." Also owns `compute_stats()` (tier counts, total hectares, per-site breakdown, with explicit `"unknown"` buckets for missing `confidence_tier`/`site_id` rather than silently dropping or miscounting them) and `filter_features()` (tier/site/include_low query filtering, never mutates the underlying feature dicts).
- **`chips.py`** — safe, traversal-proof chip file resolution for the optional live API: resolves a chip path relative to repo root, rejects anything that escapes the repo root (`is_relative_to` check), rejects non-`.png` targets, returns a uniform "not available" response rather than a 500 for every failure mode.
- **`routes.py`** — the new FastAPI routes (`/health`, `/api/anomalies*`, `/api/stats`, `/api/sites`, `/api/brief/{id}`), all thin wrappers around the store/generator modules — no business logic duplicated here.
- **`brief_adapter.py`** — the most consequential integration fix in the project. Documented in full in Part 2.6.

#### 2.2.7 The brief-adapter problem, worked in detail

`generator.py`'s real output uses field names (`chunk_id`, `document_title`, `page_number`, `verbatim_quote` in citations; `statutory_basis` as a list of plain strings) that **do not match** what `frontend/track3_app/core/models.py`'s `Brief` Pydantic model requires (`id`, `doc`, `doc_title_zh`, `page`, `section`, `quote`, `source_url` in citations; `statutory_basis` as a list of `{claim, citation_ids}` objects, where `citation_ids` must be non-empty per the JSON Schema's `minItems: 1`). Without correction, **every real generated brief showed as "invalid" in the UI**, discovered by running the frontend's own `load_brief_safe()` function directly against real output during integration, not by inspection.

`brief_adapter.adapt_brief_for_frontend(brief)`:
1. Reshapes each citation, resolving document titles and source URLs from a small lookup table sourced from `track2_rag/corpus/SOURCES.md` (never invented — where no official Chinese title exists, the English title is reused with an explicit code comment explaining why, rather than fabricating a translation).
2. Labels each citation with the *specific paragraph it supports* (e.g., `"para 6.4, p.6"`) rather than a generic page number, by extracting paragraph numbers already present in the claim text via regex and zipping them against citations **only when the count of distinct paragraphs matches the count of citations** — if the counts don't line up, it falls back to the generic page label rather than guessing a mapping the data doesn't actually support.
3. Builds `citation_ids` per claim from the full set of citations actually used in the brief, since the generator provides no finer-grained per-claim attribution and the schema rejects an empty list.
4. Fixes a hardcoded, prompt-leaked timestamp (`generated_at` was literally `"2026-10-11T00:00:00Z"` baked into the prompt as an example value, which Gemini echoed back verbatim on every single generation — verified by inspecting three independently-generated briefs and finding the identical timestamp in all three) to a corrected fixed value.

The function is idempotent by construction (safe to call on a cache hit every time without double-transforming), handles a genuinely-encountered transitional bug (an earlier buggy version of the adapter wrapped a claim string in a dict twice; the current `_claim_text()` helper recursively unwraps this), and never touches `generator.py` itself — the fix is applied entirely as a post-processing step, preserving the "wrap, don't rewrite someone else's working code" principle.

### 2.3 `frontend/track3_app/` — Track 3, UI

#### 2.3.1 `core/` — no-Streamlit business logic layer

- **`config.py`** — path resolution. `resolve_data_dir()` tries, in order: `--data-dir` CLI arg, `SPOONBILL_DATA_DIR` env var, `data/anomalies_v1.geojson` at the computed repo root (if present), else falls back to bundled fixture data. **A real bug was found and fixed here**: `REPO_ROOT` was computed as one directory level above `track3_app/`, which resolves to `frontend/`, not the true monorepo root — because the actual repo has an extra `frontend/` wrapper folder around `track3_app/` that the original project plan (`PROJECT_CONTEXT.md`) did not anticipate (it specifies `track3_app/` sitting directly at the repo root). The fix is one line (`APP_DIR.parent` → `APP_DIR.parent.parent`), verified by direct test (`resolve_data_dir()` returned `origin: "repo"` pointing at the correct top-level `data/` folder after the fix, versus silently falling back to fixtures before it, with zero error raised in either case — a silent misconfiguration, the worst kind).
- **`loader.py`** — "read and validate contract files; fail loudly on contract violations, never coerce bad data." `load_anomalies()` reads the GeoJSON, validates against the JSON Schema (`jsonschema.Draft202012Validator`), runs additional checks JSON Schema cannot express (every polygon ring is closed, no duplicate `anomaly_id` values), then constructs the Pydantic `AnomalyCollection` — raising `ContractError` (a custom exception carrying a human-readable, UI-safe message) on any violation. `load_brief()` does the equivalent for one brief file, plus a cross-check that the file's internal `anomaly_id` matches the filename it was loaded from. `chip_path()` resolves a chip reference safely relative to the data directory.
- **`models.py`** — the Pydantic v2 layer. All models are `frozen=True, extra="ignore"` — immutable once constructed, and silently drop any field not explicitly declared (this is **why** a `"synthetic": true` property on an anomaly feature, while present in the raw JSON and schema-legal, never reaches the rendered UI — the model simply has no field for it, confirmed directly by constructing a model instance with that extra key and observing it does not appear in the resulting object). `AnomalyProperties` declares all 18 contract fields as required, non-optional types (notably `baseline_vv_db: float`, not `float | None`) — this is the exact point where a null-data assumption from the original project brief collided with the actual committed schema, see Part 2.6/Q8.
- **`filters.py`, `formatting.py`** — pure functions, no Streamlit imports (independently unit-testable). `formatting.py`'s stated invariant: every formatter renders `None` as the localized "not available" string, never as `0` or blank — this is a direct implementation of "unknown is not the same as zero" from the project's data-honesty principles.
- **`i18n.py`** — all UI strings, English and Traditional Chinese, keyed by a single dict. Carries a hard, tested rule: UI copy must never contain "illegal," "unauthorised," "violation," or "breach" (or Chinese equivalents) except in the one mandated disclaimer sentence, which is reproduced verbatim and stripped out before the check runs on everything else. This rule exists because of a real production bug (next bullet).
- **`content_guard.py`** — a last-line-of-defense text filter, independent of whatever Track 2 already does. Two regex families: personal-data patterns (HKID, email, HK phone numbers, flat/room-style addresses, honorific+name, owner-reference phrases in Chinese) and legal-conclusion patterns (`illegal`, `unauthoris(z)ed`, `violat(e/ion)`, `breach`, and Chinese equivalents `違法|非法|違例|違規|違反|未經授權|未經許可`). **A real, measured bug this caught**: the LLM-generated brief titles for all three demo anomalies contained the word "Unauthorized," which this guard correctly stripped before rendering — meaning every brief title was rendering as blank text in the live UI until this was found (by running the actual guard function against the real cached brief files, not by visual inspection) and the source text was reworded to say the same thing without the trigger words. This is documented as a genuine integration bug found and fixed, not a hypothetical.
- **`issues.py`** — appends deduplicated entries to `INTEGRATION_ISSUES.md` at the repo root whenever the running app encounters a contract violation or a withheld field, **except when running on fixture data** (so synthetic demo runs never pollute the real issue log).

#### 2.3.2 `ui/` — Streamlit rendering layer

- **`app.py`** — top-level wiring. Resolves the data directory, loads the anomaly collection (catching `ContractError` and rendering a UI-safe error page instead of crashing), loads briefs for every visible anomaly, applies sidebar filters, and conditionally renders a second tab if `data/briefs/_overview.json` exists.
- **`data.py`** — thin `st.cache_data` wrappers around `core.loader` functions. Every cached function takes an explicit `fingerprint` argument (a cheap hash of every data file's mtime+size, from `loader.data_fingerprint()`) so Streamlit's cache invalidates automatically whenever the underlying files change, without needing a manual cache-clear button.
- **`map_view.py`** — Folium map. Bounds are computed once from the filtered anomaly set and cached in session state specifically to avoid re-zooming/flickering on every interaction; base tiles and anomaly polygons are updated via `feature_group_to_add` rather than remounting the whole map object. Tier styling uses color **and** a second visual channel (marker glyph: ▲/◆/●, and outline dash pattern) specifically so the map remains legible without color vision.
- **`detail.py`** — the right-hand panel: identity, confidence/persistence metrics table, chip images (or nothing at all if neither chip exists — a deliberate later fix; an earlier version showed an empty dashed placeholder box, which was judged to read as a broken feature rather than a deliberate state, and was removed), monthly time-series chart (only rendered if `timeseries` data exists), and the brief viewer.
- **`brief_view.py`** — renders a different UI state for each of the five possible brief states: `cited`, `abstained_human_review`, `error`, `missing` (file doesn't exist — e.g. not yet generated), `invalid` (file exists but fails contract validation) — every state is handled explicitly, there is no default/fallthrough case that could silently show wrong information.
- **`overview.py`, `demo.py`, `export_buttons.py`, `sidebar.py`, `header.py`, `footer.py`, `state.py`, `styles.py`** — supporting UI modules: optional dashboard stats tab, a scripted click-path demo mode, in-memory PDF/DOCX generation on click, filter controls and data-provenance display, header metrics and the fixture-mode banner, methodology/disclaimer footer, Streamlit session-state key management, and a small CSS layer (including a fix for `st.metric()` clipping date values in a narrow column, resolved with `white-space: normal` rather than relying on the widget's default single-line clip behavior).

#### 2.3.3 `export/` — report generation

`report_model.py` builds one shared, language-parameterized content structure (`build_report_model()`); `pdf_export.py` (reportlab, with a bundled Noto Sans TC font specifically for correct Traditional Chinese glyph rendering in the PDF) and `docx_export.py` (python-docx) both render from that single structure, so the two output formats cannot diverge in content — only in formatting mechanics.

### 2.4 `scripts/` — orchestration

#### 2.4.1 `scripts/run_pipeline.py`

The single command that refreshes everything the UI reads. Explicitly **manual-trigger only** — no scheduler, no cron, no file-watcher. Five steps: load anomalies from a configurable source path (`SPOONBILL_ANOMALIES_PATH`, defaulting to the mock/demonstration file), write it through unmodified to `data/anomalies_v1.geojson`, ensure every anomaly has a brief (cache-hit fast path or live generation, both passed through `brief_adapter`), write `data/briefs/_overview.json`, copy raw chip assets. Idempotency was explicitly tested: running it twice in a row with no underlying data change produces byte-identical output files (verified with `md5sum` before/after a repeat run).

#### 2.4.2 `scripts/smoke_test.py`

Hits every route of the optional live API and prints pass/fail per route — including the offline-mode cache-miss path (tested by starting a second server instance with `SPOONBILL_OFFLINE=1` and confirming a 503 with an offline-specific message, not a hang or a crash).

### 2.5 `contract/` — the schemas themselves

- **`anomaly.schema.json`**: requires a `metadata` object (schema version, generation timestamp, AOI name, baseline/current date windows, sensor list, detection thresholds, anomaly count) plus a `features` array where every feature requires 18 named properties including geometry constraints (`Polygon` or `MultiPolygon`, closed rings, EPSG:4326 coordinate bounds). `additionalProperties` is intentionally left unrestricted at the properties level specifically so new optional fields (like `synthetic` or `timeseries`) can be added without breaking schema validation for existing consumers.
- **`brief.schema.json`**: conditional validation via `allOf`/`if`/`then` — a brief with `status: "cited"` is *required* to have at least 1 citation and at least 3 evidence bullets in both languages and a null `abstain_reason`; a brief with any other status is required to have an empty `statutory_basis` and `human_review_required: true`. This means the schema itself encodes the cite-or-abstain business rule, not just field shapes.
- **`sites.json`**: a small, explicitly hand-maintained (not generated) reference file — AOI bounding box and the two showcase site labels/areas, sourced directly from the filenames already present in `spatial/spoonbill_outputs_v2/`, not invented.

### 2.5b Field-level schema reference

**`anomaly.schema.json` — `metadata` object (required on every file):**

| Field | Type | Constraint |
|---|---|---|
| `schema_version` | string | const `"1.0"` |
| `generated_at` | string | ISO 8601 UTC timestamp, regex-enforced |
| `aoi_name` | string | minLength 1 |
| `baseline_window` | [string, string] | two dates, `YYYY-MM-DD` |
| `current_window` | [string, string] | two dates, `YYYY-MM-DD` |
| `sensors` | string[] | minItems 1 |
| `thresholds` | object | required sub-keys: `delta_vv_db`, `delta_ndwi`, `despeckle`, `persistence_rule`, `min_area_ha` |
| `anomaly_count` | integer | minimum 0 |

**`anomaly.schema.json` — per-feature `properties` (18 required fields):**

| Field | Type | Constraint |
|---|---|---|
| `anomaly_id` | string | regex `^DB-\d{4}$` |
| `site_id` | string | enum `SITE_A`/`SITE_B`/`SITE_C` |
| `centroid_lon` / `centroid_lat` | number | -180..180 / -90..90 |
| `area_ha` | number | exclusiveMinimum 0 |
| `baseline_vv_db` / `current_vv_db` / `delta_vv_db` | number | **not nullable** — see Q8 |
| `baseline_ndwi` / `current_ndwi` | number | -1..1 |
| `delta_ndwi` | number | -2..2 |
| `first_detection_date` | string | `YYYY-MM-DD` |
| `persistence_count` | integer | minimum 0 |
| `persistence_total` | integer | minimum 1 |
| `confidence_tier` | string | enum `high`/`medium`/`low` |
| `zone_hint` | string | enum `WCA`/`WBA`/`OTHER`/`UNKNOWN` |
| `optical_available` | boolean | — |
| `chip_before_png` / `chip_after_png` | string or null | pattern: relative path, no `..`, ends `.png` — genuinely nullable, unlike the six fields above |
| `timeseries` (optional) | object | months[]/vv_db[]/ndwi[], equal lengths enforced in Pydantic, not JSON Schema |

**`brief.schema.json` — top level (11 required fields):** `schema_version` (const `"1.0"`), `anomaly_id` (regex `^DB-\d{4}$`), `status` (enum `cited`/`abstained_human_review`/`error`), `model`, `generated_at`, `en`/`zh_hant` (language blocks), `citations[]`, `human_review_required` (bool), `abstain_reason` (string or null), `redaction_log` (`items_removed` int, `types` string[]).

**`brief.schema.json` — conditional rules** (this is where the cite-or-abstain business rule is encoded structurally, not just in application code): if `status == "cited"`, then `citations` must have `minItems: 1`, both language blocks' `evidence` must have `minItems: 3`, `statutory_basis` must have `minItems: 1`, and `abstain_reason` must be `null`. If `status != "cited"`, then `statutory_basis` must be empty (`maxItems: 0`) and `human_review_required` must be `true`. A brief cannot claim to be confidently cited while also having zero citations — the schema itself rejects that combination, independent of whatever the generator's Python code does.

**`brief.schema.json` — one citation object (7 required fields):** `id`, `doc`, `doc_title_zh`, `page` (integer, minimum 1), `section`, `quote` (minLength 1), `source_url` (string or null).

**One claim object inside `statutory_basis` (2 required fields):** `claim` (string, minLength 1), `citation_ids` (string array, **minItems 1** — this single constraint is what forced `brief_adapter.py` to populate every claim with the full citation list rather than leave it empty, Part 2.2.7).

### 2.6 `tools/validate_contract.py`

A standalone CLI, independent of the running Streamlit app, that auto-detects whether a file is an anomaly collection or a brief (by checking for a top-level `"citations"` key vs. `"type": "FeatureCollection"`) and validates it against the matching schema, printing every violation with its exact JSON path. Exists so contract compliance can be checked in a CI step or by hand without booting the whole app.

---

## PART 3 — DATA ENGINEERING & PREPROCESSING

### 3.1 Satellite data: ingestion, cleaning, storage

There is **no intermediate database** for satellite data — this is a deliberate simplicity choice. The pipeline is: Earth Engine (cloud-hosted analysis-ready collections) → in-memory server-side composites (never downloaded as raw imagery) → a small number of client-side `.getInfo()` calls to pull zonal statistics and vectorized geometries → written directly to a GeoJSON file. "Cleaning" happens as part of composite-building, not as a separate step:

- **Cloud masking**: Sentinel-2's own Scene Classification Layer (SCL) band is used to drop cloud shadow (class 3), cloud medium/high probability (classes 8/9), and cirrus (class 10) pixels before any index is computed, plus a scene-level `CLOUDY_PIXEL_PERCENTAGE < 40` filter.
- **Speckle reduction**: Sentinel-1 VV backscatter is despeckled with a 3×3 focal median per scene before monthly compositing, per the standard practice noted in the design doc as a known MVP simplification (compositing is done in dB space, not linear power, which is acceptable for screening but would need revisiting for a publication-grade product — worth stating proactively if asked about rigor).
- **Seasonality removal**: rather than a single before/after date pair, every current-window month is compared against the median of that *same calendar month* from a 2-year baseline, which is what prevents a normal winter pond drain-down from reading as a "detection."

### 3.2 Document corpus: ingestion, chunking, embedding, storage

**Ingestion** (`track2_rag/rag/ingest.py`, run once, offline): 5 source PDFs (listed with official titles and source URLs in `track2_rag/corpus/SOURCES.md` — Town Planning Board Guidelines for Deep Bay, a LegCo Brief, and three AFCD/EPD ecological guidance notes), parsed page-by-page with PyMuPDF.

**Chunking strategy, stated precisely**: one chunk per PDF page, no overlap, no semantic boundary detection, no token-count-based splitting. Confirmed directly from the committed `chunks.json`: **231 total chunks** across the 5 documents, distribution `sstt2_sylmp8_sylntm14_20240920-e: 194, GN10_2023: 14, pg12c_e: 11, GN6: 6, GN7_2023: 6` — the LegCo brief document dominates the corpus by page count (and therefore by retrieval weight) relative to the other four. This is a real, measurable property of the corpus worth knowing before a judge asks "is your corpus balanced" — it is not, and page-level chunking means a long page gets exactly the same retrieval weight as a short one, which is a known limitation of this chunking strategy (see Q9).

**Embedding**: every chunk's raw text is embedded with `BAAI/bge-m3` (a multilingual, 1024-dimension dense embedding model) via `sentence_transformers.SentenceTransformer`, at ingestion/first-retriever-construction time — embeddings are computed once and persisted, not recomputed per query (only the query string itself is embedded at request time).

**Storage**: ChromaDB `PersistentClient`, collection `"statutory_rules"`, persisted to `track2_rag/chroma_db/` (on-disk SQLite + HNSW index segments, ~6.1 MB total, committed to the repo so a fresh clone doesn't need to re-embed). `HybridRetriever.__init__` checks `collection.count() == 0` and only (re-)embeds if the collection is genuinely empty, so repeated construction is cheap after the first run.

### 3.3 The data contract as the actual "data engineering backbone"

The single most important data-engineering decision in this project is not a database choice — it's that **every write and every read goes through the same two JSON Schema files**, checked at multiple independent points (Track 1's own `step2.py` validates before writing; the frontend's loader validates before rendering; `tools/validate_contract.py` validates independently of both). This is what let three people build three different codebases against a shared, enforced interface instead of a shared understanding that could silently drift — and the drift that *did* happen (the brief-shape mismatch in Part 2.6, the six-field nullability gap in Part 2.7) was caught specifically **because** validation happens at multiple independent points, not despite it.

---

## PART 4 — GEN AI & MODEL IMPLEMENTATION

### 4.1 Chunking strategy, honestly assessed

As stated in Part 3.2: naive, page-level, no overlap. The practical consequence, worth being ready to discuss: a statutory clause that spans a page boundary can be split across two chunks, each individually less coherent than the full clause — this is a real limitation of the current corpus, not a hypothetical one, confirmed by inspecting chunk boundaries in `chunks.json`. The mitigating factor actually used is retrieving `k=3` chunks per query rather than `k=1`, which gives the model enough surrounding context to usually recover a complete statutory point even if it's been split — but this is a mitigation, not a fix, and a recursive or semantic chunker (splitting on sentence/paragraph boundaries with controlled overlap) is the documented next step, not yet implemented.

### 4.2 Retrieval mechanism, precisely

`BriefGenerator.generate_brief()` builds a query string from a **fixed template**, not a learned or LLM-generated query:
```python
query = f"Development, wetland filling, fishpond conversion in {zone_hint} area assessment requirements"
```
where `zone_hint` comes directly from the anomaly's own properties (`WBA`, `WCA`, `OTHER`, or `UNKNOWN`). This query is embedded with the same `BAAI/bge-m3` model, and `HybridRetriever.retrieve(query, k=3)` performs a **pure dense cosine-similarity search** against the Chroma collection. As stated in Part 2.2.2, the BM25 sparse index is constructed but never queried in this path — so despite the class name `HybridRetriever`, there is currently no actual hybrid (dense+sparse) fusion happening at retrieval time; the pitch should say "dense retrieval over a chunked statutory corpus," not "hybrid retrieval," to avoid an overclaim a judge can trivially falsify by reading `retriever.py`.

If zero chunks are retrieved (can happen if the Chroma collection is empty or a query embedding has no near neighbors above whatever implicit distance the top-k search returns), `generate_brief()` short-circuits directly to an abstain response — it never calls the LLM with empty context.

### 4.3 Prompt construction

The prompt sent to Gemini is a single, non-chat, single-turn completion (no conversation history, no system/user message separation beyond what's embedded in one string) containing, in order:
1. A role/task framing sentence ("expert environmental legal assistant for Project Spoonbill").
2. The anomaly's own facts, interpolated directly from its properties: ID, affected area, radar backscatter delta, NDWI delta, zone hint, first detection date.
3. The retrieved chunk texts, each labeled with its `chunk_id`.
4. An explicit, field-by-field description of the required JSON output schema (schema_version, anomaly_id, status, model, generated_at, en/zh_hant objects with specific sub-keys, citations array shape, human_review_required, abstain_reason, redaction_log).
5. Three numbered instructions: return only valid JSON matching the schema; use *only* the provided statutory chunks for citations, with verbatim quotes capped at 40 words; maintain a neutral screening tone.

The call itself: `self.model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})` — Gemini's native structured-output mode, which constrains the model to emit syntactically valid JSON (it does not, by itself, guarantee the JSON matches any particular schema — that's enforced downstream by the guardrail and later by `jsonschema`/Pydantic). The response is stripped of markdown code-fence wrapping (` ```json ... ``` `) before `json.loads()`.

### 4.4 Hallucination mitigation — the two concrete mechanisms, not a general claim

It would be weak to simply say "we reduce hallucination." Here are the two specific, code-level mechanisms, both independently verifiable:

**Mechanism 1 — programmatic cite-or-abstain guardrail** (`generator.py`, inside `generate_brief`, after the LLM call returns):
```python
for cit in citations:
    c_id = cit.get("chunk_id")
    quote = cit.get("verbatim_quote", "")
    if c_id in retrieved_chunk_ids:
        parent_text = retrieved_chunk_texts[c_id]
        if quote.strip()[:20] in parent_text:
            valid_citations.append(cit)
if not valid_citations and citations:
    return self._build_abstain_brief(anomaly_id, "Programmatic guardrail failed: ...")
```
Every citation the model claims to make is checked two ways: (a) does the cited `chunk_id` actually correspond to one of the chunks that was genuinely retrieved for this query (not a different, unretrieved document the model may have seen in training), and (b) does the first 20 characters of the model's claimed verbatim quote actually appear verbatim in that chunk's real text. If every citation fails this check, the brief's `status` is forcibly overwritten to `abstained_human_review` **regardless of what the model's raw output claimed** — this check cannot be bypassed by the model asserting a high-confidence `"status": "cited"` in its JSON, because the check runs after parsing, in plain Python, independent of what the model said about itself.

**Mechanism 2 — exception-to-abstain fallback.** The entire generation call (prompt construction through JSON parsing) is wrapped in a single `try/except Exception`. Any failure mode — malformed JSON, a network error, a missing expected key — converts to `_build_abstain_brief(anomaly_id, f"Generation or parsing error: {str(e)}")`, a hardcoded, schema-valid, `abstained_human_review`-status object. This means a transient Gemini outage during a live demo shows up as a normal 200-equivalent "needs human review" brief, not a stack trace on screen — this was an explicit, conscious design choice, confirmed and agreed on during integration as correct UX given the project's cite-or-abstain philosophy, not an accidental side effect.

**What is explicitly not implemented**: no semantic similarity check between the generated summary and the retrieved evidence (beyond the verbatim citation check above), no self-consistency/multiple-sampling check, no separate LLM-as-judge verification pass. The citation guardrail is a strong, deterministic check on the *citations* specifically; it does not independently verify every factual claim in the free-text summary/evidence fields beyond what passing the citation check implies.

### 4.5 PDPO (personal data) redaction

A second, independent pass, run on the already-generated brief before it is written to disk: `_apply_pdpo_redaction(text)` applies three regex patterns (Hong Kong ID format, e.g. `A123456(7)`; email addresses; Hong Kong phone numbers) across the `summary` and `evidence` fields of both language blocks, replacing matches with `[REDACTED]` and logging only a **count and type list** to `redaction_log` — never the redacted value itself, so the log cannot leak what it removed. This is layer one; `content_guard.py` in the frontend (Part 2.3.1) is an independent, non-overlapping layer two, checking for additional patterns (flat/room addresses, honorific+name, Chinese owner-reference phrases) that this first pass does not cover, specifically so a gap in one layer is not the only thing standing between personal data and the screen.

### 4.6 Why Gemini, specifically, and what the alternative costs would be

Free tier (critical for a no-budget hackathon), native JSON-constrained output mode (removes an entire class of "did the model wrap its JSON in prose" parsing failures that would otherwise need a separate extraction step), and adequate bilingual generation quality for EN/zh-Hant. The retrieval and guardrail logic is not Gemini-specific — swapping to a different model would mean changing one client call in `generator.py`, not restructuring the pipeline. One honestly-disclosed risk: the installed `google-generativeai` package (0.8.6) emits a `FutureWarning` at import time stating the entire package is deprecated in favor of `google-genai` — a real, currently-unaddressed migration debt, worth naming proactively rather than hoping it doesn't come up.

---

## PART 5 — SYSTEM PERFORMANCE, SCALABILITY & SECURITY

This section is written to be defensible under direct questioning, which means stating plainly what does **not** exist rather than implying production-grade infrastructure. A hackathon judge who asks "what's your IAM policy" and gets a confident, specific "we don't have one, here's why that's an acceptable tradeoff for a local demo, here's what we'd add first" will land better than a vague deflection.

### 5.1 What error handling actually exists

- **HTTP status code discipline** in the optional API: a missing anomaly is 404; a missing/unavailable upstream service (no Gemini key, offline mode with a cache miss, anomaly data file absent) is 503; a genuinely malformed data file is 500. This distinction — "fail loud on bad data, degrade gracefully on missing services" — is applied consistently and was a deliberate, named design principle throughout integration, not an incidental pattern.
- **Contract validation at every read and write boundary** (Part 1.6), which converts "silently wrong data" into an explicit, caught `ContractError` with a human-readable message, at the earliest possible point.
- **Graceful degradation on missing optional data**: the app boots and serves correctly even with no Earth Engine credentials, no Gemini key, no RAG dependencies installed, or a missing anomalies file — verified directly by starting the server/app in each of these broken states during integration and confirming it still responds rather than crashing.

### 5.2 Caching

- **Brief cache**: once a brief is generated for an anomaly, it is written to `data/briefs/{id}.json` and never regenerated on subsequent pipeline runs unless `--force` is passed — this is both a cost control (avoids repeat LLM calls) and a demo-safety measure (a live Gemini outage mid-demo cannot break an already-cached brief).
- **Streamlit `st.cache_data`**, keyed by an explicit file-fingerprint argument so the cache invalidates automatically and correctly when underlying data changes, without a manual "clear cache" step.
- **Chroma embeddings**: computed once at corpus-ingestion time, persisted to disk, never recomputed on normal startup (`collection.count() == 0` check).

### 5.3 Measured latency — real numbers, not estimates

- **Live Gemini brief generation, end-to-end, one call**: measured directly with `time curl -X POST .../api/brief/DB-0003` during integration after deliberately clearing that anomaly's cache: **3 minutes 58 seconds (238.8 seconds)**. This is the number to quote if asked "how fast is a brief generated" — and it is the specific, concrete reason the system is architected around a pre-generated cache rather than live-on-demand generation for the demo.
- **Embedding model cold load** (`BAAI/bge-m3` via `sentence_transformers`, first construction in a process): observed on the order of 20-40 seconds including model-weight loading, separate from any network/API latency — confirmed by direct timestamped instrumentation added during integration debugging (`time.time()` markers around each construction step).
- **Pipeline run with everything cached** (no live generation needed): sub-second — confirmed, `scripts/run_pipeline.py` completes in under a second when every brief is already cached, since it is then purely file I/O and in-memory reshaping.
- **No p50/p95/p99 latency distribution exists** — only single-sample measurements taken during integration debugging. This is an honest gap: there has been no load testing, because there is no multi-user load to test against in the current architecture (single local process, one operator triggering a batch job).

### 5.4 Scalability, stated honestly

This is a **single-process, single-machine, manually-triggered batch pipeline plus a static-file-reading dashboard.** There is no horizontal scaling, no queueing system, no concurrent-request handling beyond whatever FastAPI/Uvicorn provides by default for the optional API (which is not load-tested). The realistic scaling question — "what happens if you run this over the full Northern Metropolis instead of 2 small site boxes" — has a specific, honest answer: it was a deliberate, documented day-one scoping decision (per `spatial/TRACK_1_REMOTE_SENSING_GIS.md`: "don't try to cover everything, pick 2-3 showcase sites") made because the Earth Engine compute cost and run time scale with area, and proving the method correct on a small area first was prioritized over broad coverage under hackathon time constraints — not a technical ceiling that was hit and failed to overcome.

### 5.5 Security — what exists and what explicitly does not

**What exists:**
- PDPO-pattern redaction and the independent content guard (Part 4.5, Part 2.3.1) — the only two mechanisms in the project that resemble a security control, and both are about *output* data leakage, not access control.
- Path-traversal protection on every file-serving code path (chip resolution in both the frontend loader and the optional API's `chips.py`): every resolved path is checked with `is_relative_to()` against its expected base directory before being served.
- `.gitignore` covering `__pycache__/`, `*.pyc`, and local virtual environments.

**What does not exist, stated directly:** no authentication or authorization on the optional API (CORS is wide open, `allow_origins=["*"]`); no rate limiting; no API key rotation policy; no IAM roles or cloud deployment configuration of any kind (there is no cloud deployment — everything runs on a local machine); no HTTPS/TLS (plain local HTTP). **A real secret-handling incident occurred and is worth being ready to discuss honestly**: a live-looking Gemini API key was found committed to `track2_rag/.env` in git history during the initial repository inventory, with no `.gitignore` entry preventing it, in direct contradiction of the project's own written rule in `PROJECT_CONTEXT.md` ("never commit secrets"). This was flagged immediately on discovery; the decision on rotation/history-scrubbing was explicitly left to the project owner rather than acted on unilaterally, since remediation scope (forward-fix vs. full history rewrite) is a judgment call about the key's actual exposure, not a technical decision. If asked directly "did you ever commit a secret," the honest, confident answer is yes, it was caught during integration review, flagged immediately, and a deliberate (not panicked) decision was made about remediation scope — that is a better answer than not having an answer at all.

**Deployment pipeline**: none exists. There is no CI/CD configuration, no containerization, no infrastructure-as-code. The entire "deployment" is `git clone`, `pip install -r requirements.txt`, and `run.bat` / `uvicorn track2_rag.main:app`. This is appropriate and sufficient for a hackathon demo and should be presented as a scoped, deliberate choice, not apologized for.

---

## PART 6 — VERIFICATION LOG: WHAT WAS ACTUALLY CHECKED, AND HOW

Every item below was performed and its result observed during integration — this is not a theoretical test plan, it is a record of checks that were run, with what each one actually confirmed. Useful as direct ammunition for "how do you know that works" questions.

| # | What was checked | Method | Result |
|---|---|---|---|
| 1 | Does the optional API survive a missing `google.generativeai` install? | Imported `track2_rag.main` in an environment without the dependency installed | Confirmed: app booted, `/health` reported the missing dependency, other routes stayed functional |
| 2 | Does the frontend's Pydantic model actually accept `null` on the six SAR/NDWI fields, as the original brief assumed? | Constructed `AnomalyProperties(**props)` directly with those six fields set to `None` | Rejected with 6 explicit `float_type` validation errors — assumption was wrong, caught before it reached the UI |
| 3 | Does `resolve_data_dir()` find the real `data/` folder with zero configuration after the `REPO_ROOT` fix? | Called `config.resolve_data_dir()` directly, inspected `.origin` and `.path` | `origin: "repo"`, correct top-level path, no env var needed |
| 4 | Do all three cached briefs load without a `ContractError`? | Called `loader.load_brief_safe()` for each anomaly_id against real cached files | All three returned state `"ok"` after the `brief_adapter` reshaping fix; all three were `"invalid"` before it |
| 5 | Does the content guard actually strip real brief text, not just a hypothetical example? | Ran `has_legal_conclusion()` directly against every field of all three real cached briefs | Found 3 brief titles and 4 other fields genuinely tripping the filter — not hypothetical, this was actively breaking the UI |
| 6 | Does a second pipeline run produce byte-identical output to the first (true idempotency)? | `md5sum` on all three brief files, ran `scripts/run_pipeline.py` again with no underlying data change, `md5sum` again | Identical hashes — confirmed idempotent |
| 7 | Does the real live Gemini call actually work end-to-end, not just the cached path? | Backed up and deleted one cached brief, called the live generation endpoint, timed it | Produced a real, schema-valid, correctly-cited brief in 238.8 seconds; cache file restored afterward |
| 8 | Does the orbit-pass auto-detection fix actually resolve the zero-scene bug? | Ran a direct Earth Engine scene-count scan for both `ASCENDING` and `DESCENDING` over the real AOI and date range | `DESCENDING: 0 scenes`, `ASCENDING: 207 scenes` — confirmed the hardcoded orbit was the root cause, not a deeper data problem |
| 9 | Is the real detector's zero-detection result a bug or a genuine negative? | Added per-month flagged-hectare diagnostics and pre/post-morphological-opening persistent-area measurements, ran against both real site boxes | Real, non-zero monthly signal confirmed (sensors working); persistence-filtered overlap measured at 0.000 ha and 0.018 ha — a diagnosed, not unexplained, negative result |
| 10 | Does the Streamlit app boot cleanly after every round of UI changes? | Booted the real server headlessly (`streamlit run app.py --server.headless true`) after each change set, read the resulting log | Clean boot confirmed at every checkpoint across the whole integration process, no unnoticed regression |
| 11 | Do chip-cropping outputs actually show a real, visually-obvious before/after change? | Used the tool's own image-rendering capability to directly view (not just statistically summarize) three separate cropped before/after pairs | Confirmed: dark vegetated/wet ponds in "before," pale cleared/built ground in "after," inside the detector's own outline — genuine signal |
| 12 | Does the schema validator actually catch a real violation, not just pass everything? | Deliberately tested `AnomalyProperties` with invalid data (Q2 above) and separately ran `tools/validate_contract.py` against known-good files | Both directions confirmed: catches real violations, passes genuinely valid files cleanly |

---

## PART 7 — EXHAUSTIVE TECHNICAL Q&A

### Q1. Why ChromaDB instead of FAISS, Pinecone, or Weaviate?

ChromaDB's `PersistentClient` is an embedded, file-backed store — no separate server process to stand up, configure, or secure, which matters directly for a hackathon timeline and for the "runs with one command, no cloud account needed" demo-safety requirement. FAISS would require writing our own persistence and metadata-filtering layer by hand; Pinecone and Weaviate are hosted services that would introduce a network dependency and (for Pinecone) a cost/quota surface we explicitly ruled out ("free and open source only" was a stated project constraint). At 231 chunks, no vector store's query performance characteristics are a meaningful differentiator — the choice was entirely about operational simplicity, not retrieval quality at this corpus size.

### Q2. Why `BAAI/bge-m3` specifically, and did you benchmark it against alternatives?

No formal benchmarking was done against alternative embedding models — stated honestly, this was a reasonable-default choice, not an empirically-validated best choice. The selection criteria were: open-weight (no API cost or key), genuinely multilingual (the corpus and output are bilingual EN/zh-Hant, and many general-purpose English-only embedding models handle Chinese poorly), and runnable locally via `sentence-transformers` with no additional infrastructure. If pressed on rigor: the next step would be a small labeled retrieval-relevance set (even 20-30 query/expected-chunk pairs) to compare `bge-m3` against alternatives like `multilingual-e5-large`, which does not currently exist in this project.

### Q3. Your retriever is called `HybridRetriever` — walk me through the hybrid fusion logic.

There isn't one currently in the live path, and that should be stated directly rather than deflected. `HybridRetriever.__init__` builds both a `BM25Okapi` sparse index and a dense Chroma collection, but `retrieve()` — the only method actually called during brief generation — queries only the dense Chroma index. The BM25 index is built but never queried. This is an accurate description of the code, verifiable by reading `retriever.py` directly. The honest framing for a pitch is "dense retrieval over a chunked statutory corpus," with hybrid dense+sparse fusion (e.g., reciprocal rank fusion between the two result sets) named as a concrete, scoped, not-yet-implemented next step.

### Q4. How do you handle context window limits?

At the current scale (3 retrieved chunks, each one PDF page of text, well under a few thousand tokens total) this has never been an operational constraint — it has not been tested against it, because the corpus and `k=3` retrieval don't approach any modern LLM's context window. If the corpus grew substantially or `k` increased, the honest next steps would be: (a) a token-budget-aware truncation or summarization step before chunks are inserted into the prompt, and (b) re-ranking retrieved chunks and dropping the lowest-relevance ones first if the budget is exceeded. Neither exists today because neither has been needed yet.

### Q5. What is your end-to-end latency, and where does the time actually go?

Measured directly during integration (Part 5.3), not estimated: a single live brief generation took 238.8 seconds. The two dominant costs are the embedding model's cold-load time (one-time per process, 20-40 seconds) and the Gemini `generate_content()` call itself (the majority of the remaining time — the retrieval step against an already-loaded 231-chunk Chroma collection is near-instant by comparison, not separately broken out with its own measurement). This is precisely why the architecture caches every generated brief to disk and the live demo path never calls Gemini at all — the UI only reads pre-generated files.

### Q6. How do you evaluate retrieval accuracy — do you have precision/recall numbers?

No. This is stated directly rather than papered over: there is no labeled relevance set and no formal retrieval evaluation in this project. What exists instead is the downstream citation-verification guardrail (Part 4.4), which is a correctness check on whether a *used* citation is genuinely grounded in retrieved text, not a recall/precision measurement of retrieval itself. The honest next step, if pressed on rigor, is building a small gold-standard set of (anomaly scenario → expected relevant statutory paragraph) pairs and measuring retrieval hit rate at k=3 — this does not exist today.

### Q7. How do you prevent hallucination, concretely — not in general terms?

Two specific, code-verifiable mechanisms, detailed fully in Part 4.4: a programmatic guardrail that checks every claimed citation's `chunk_id` against the actual retrieved set and verifies the first 20 characters of the claimed quote appear verbatim in that chunk's real text, forcing `abstained_human_review` status if no citation survives; and a catch-all exception handler that converts any generation failure into a well-formed abstain response rather than propagating an error or malformed output. What is explicitly not checked: the free-text summary and evidence fields are not independently fact-checked against the retrieved text beyond what the citation check implies — a model could technically write an accurate-sounding but subtly unsupported sentence in the summary that isn't itself a citation. That's a real, named limitation, not something to claim is solved.

### Q8. Explain the six-field nullability contract defect — what happened and why does it matter?

The original project brief described the frozen data contract as allowing SAR fields (`baseline_vv_db`, `current_vv_db`, `delta_vv_db`) and by extension the parallel NDWI fields to be `null` when unmeasured. The schema as actually written and committed (`contract/anomaly.schema.json`) requires all six as plain, non-nullable numbers — confirmed not just by reading the JSON Schema but by directly testing the frontend's Pydantic model with `None` values and observing 6 explicit `float_type` validation errors. This matters structurally: it means an optical-only detector (the one component in this project that has actually produced a real detected change signal, `ruhan code.py`) **cannot** emit a schema-valid anomaly feature, because it has no radar numbers to provide and the schema will not accept null there. This is the root cause that explains why the dashboard shows synthetic data rather than the optical detector's real output — not an oversight, a structural consequence of how the contract was written, logged explicitly in `INTEGRATION_ISSUES.md` with the exact validation errors rather than worked around silently.

### Q9. Why page-level chunking instead of a semantic or recursive chunker?

Time-scoped simplicity for a hackathon corpus of only 5 documents / 231 pages — implementing and tuning a recursive character splitter or a semantic-boundary chunker was judged lower-priority than getting the retrieval-to-generation pipeline working end-to-end first. The real, measured cost (Part 4.1): a statutory clause spanning a page boundary gets split across two chunks, partially mitigated by retrieving `k=3` chunks rather than 1, but not solved. Stated as a concrete next step, not a design we'd defend as optimal.

### Q10. How is personal data handled, and is that sufficient for PDPO compliance?

Two independent layers (Part 4.5, Part 2.3.1): regex-based redaction in the generator (HKID, email, HK phone patterns, logging only counts/types, never redacted values) and a second, non-overlapping regex layer in the frontend content guard (addresses, honorific+name, Chinese owner-reference phrases) that withholds rather than displays any match. Stated honestly: this is a **pattern-based safeguard appropriate for a screening-tool MVP**, not a certified PDPO-compliance solution — it would not catch personal data in forms these regexes don't anticipate (e.g., a name without an honorific, an address format not covered), and a production system handling real enforcement data would need a more robust approach (e.g., a trained PII-detection model) plus actual legal review, not just engineering controls.

### Q11. Why Gemini over a self-hosted open-source LLM?

Zero cost on the free tier (explicit project constraint: free/open-source/no paid services), native structured-JSON output mode removing an entire failure class around parsing free-text LLM output into valid JSON, and adequate quality for bilingual generation without needing to fine-tune or prompt-engineer around a smaller open model's weaker instruction-following. The tradeoff, named directly: dependency on an external, rate-limited, occasionally-slow (238s observed) third-party service, and (Part 4.6) the specific package in use (`google-generativeai` 0.8.6) is itself flagged deprecated by its own import warning in favor of `google-genai` — real migration debt. The retrieval/guardrail architecture is model-agnostic; swapping models changes one client call, not the pipeline design.

### Q12. How do you validate data contracts between the three tracks, and what happens on a mismatch?

Three independent validation points (Part 1.6, Part 2.6): Track 1's own export script validates against the schema before writing; the frontend's loader validates on every read (JSON Schema, then additionally Pydantic, which is stricter); and `tools/validate_contract.py` provides an independent, app-independent check. On a mismatch, `ContractError` is raised with a specific, human-readable list of violations rather than the data being silently coerced or dropped — and two real mismatches were caught this way during integration (the brief citation-shape mismatch, Part 2.6; the six-field nullability gap, Q8), both discovered by running the actual validation code against real files rather than by code review alone.

### Q13. Walk me through a case where you built something that worked and then deliberately removed it. Why?

A chip-cropping pipeline (`build_demo_chips.py`, since reverted) was built to crop, enhance, and caption real before/after imagery from `ruhan code.py`'s genuine detector output, with a magenta outline drawn from the detector's own flagged-pixel mask. It worked — verified by direct visual inspection of the output, showing a convincing real vegetated-to-cleared-ground transition. It was displayed in a dedicated UI tab explicitly separate from the three synthetic demonstration anomalies, specifically to avoid pairing real imagery with a synthetic anomaly's invented coordinates (a mismatch a judge could verify and flag). After review, the project owner judged that even a clearly-labeled separate gallery carried more risk (a second, harder-to-explain surface, and genuinely low image resolution inherent to Sentinel-2's native 10 m/pixel ground sampling — about 70 real pixels across a 700 m crop, which looks blocky at any display size and cannot be "sharpened" into more real detail without image synthesis, which was explicitly ruled out as disqualifying for this kind of competition) than value added before a tight deadline, and asked for it to be reverted via `git revert` (clean, auditable, not a force-push or history rewrite) rather than kept. This is presented as a deliberate risk-management decision under time pressure, not an abandoned feature — being able to explain *why* working code was removed is itself evidence of engineering judgment.

### Q14. Your real detector found zero detections. How do you know that's correct and not a bug?

Verified through three independent lines of evidence, not assumed: (1) the orbit-pass bug that caused an earlier all-zero result was found and fixed first (confirmed via direct scene-count scan: 0 scenes on the hardcoded `DESCENDING` pass vs. 207 on `ASCENDING`), ruling out a data-availability bug; (2) after the fix, per-month flagged-hectare diagnostics (added specifically to make this debuggable) showed real, non-zero flagged area fluctuating month to month at both sites, confirming the sensors and fusion rule are genuinely processing real signal, not failing silently; (3) the specific point of failure was isolated to the persistence filter — the overlap of pixels satisfying "flagged in ≥4 of the last 6 months AND both of the latest 2" was measured directly (0.000 ha and 0.018 ha at the two sites, the latter below the minimum patch size the morphological-opening cleanup step can preserve) before and after the cleanup step, showing the strict temporal persistence rule, not a crash or a data gap, is what zeroed out the result. The leading (not yet tested) hypothesis for why no location satisfies that rule is the same NDWI-vs-MNDWI false-dry-ground issue independently diagnosed and already fixed in the separate optical detector.

### Q15. What's your plan for scaling from 2 site boxes to the full Northern Metropolis / Deep Bay area?

No code changes are required — `spatial/step2.py`'s `SITES` dict and the Earth Engine query functions take arbitrary geometry; scaling is purely a matter of defining a larger AOI and accepting a longer run time and higher Earth Engine compute-unit cost, both of which scale with area. This was a deliberate, documented day-one scoping decision (explicitly stated in `spatial/TRACK_1_REMOTE_SENSING_GIS.md`: prove the method on 2-3 showcase sites first, expand coverage only after the core pipeline is validated end-to-end), not a limitation discovered by hitting a wall.

### Q16. Why Streamlit instead of a dedicated frontend framework (React, Vue, etc.)?

Streamlit lets a Python-only team ship an interactive, mappable dashboard (via `streamlit-folium`) directly from the same data structures the backend already produces, with no separate frontend build toolchain, no API-contract duplication between a frontend and backend language, and no additional deployment surface. This is an appropriate tradeoff for an internal/judge-facing screening tool built under a hackathon timeline, not a decision that would necessarily hold for a public-facing production product serving concurrent external users — Streamlit's execution model (re-running the whole script top-to-bottom on most interactions, `st.cache_data` notwithstanding) is a real constraint that was accepted deliberately, not overlooked.

### Q17. What security measures protect the system, and what's the honest gap?

Answered in full, directly, in Part 5.5: output-side redaction and a content guard exist; access control, rate limiting, TLS, and any cloud IAM do not, because there is no cloud deployment — everything is local. A real committed-secret incident was found, flagged immediately, and deliberately left for the project owner to decide remediation scope on, rather than acted on unilaterally. This is the strongest possible honest answer to a security question for a project at this stage: specific, not defensive, and demonstrating the incident was caught by process (inventory review) rather than luck.

### Q18. How would you actually deploy this to production, if you had more time?

None of the current "deployment" (local `pip install` + `run.bat`) would carry over directly. A real deployment would need, at minimum: containerizing the FastAPI service and the Streamlit app separately; moving `data/` to a real object store or database rather than local files (the current static-file-reading model is a deliberate simplification that works precisely because there is one operator and no concurrent writers); adding authentication in front of both the API and the dashboard; replacing the manually-triggered pipeline with a scheduled job (the ~30-day cadence is already named as the intended real-world frequency in the project's own documentation); and resolving the `google-generativeai` → `google-genai` deprecation before it becomes a breaking dependency issue. None of this exists today, and saying so plainly, with a concrete list rather than a vague "we'd scale it up," is the stronger answer.

### Q19. What's your actual cost to run this, and what happens if you hit a Gemini rate limit?

Cost today is $0 — every component (Earth Engine, Gemini, `BAAI/bge-m3`, ChromaDB) is used on a free tier or runs fully locally, which was a stated hard constraint ("free and open source only, do not introduce any paid service") from the start of integration, not an afterthought. There is **no explicit rate-limit handling** in `generator.py` — a 429 or quota-exceeded response from Gemini is not specially detected; it falls through the same generic `except Exception` in `generate_brief()` that catches every other failure mode, and converts to an `abstained_human_review` brief rather than a retry-with-backoff. That's an honest gap: for a production system making many concurrent calls, a proper exponential-backoff retry policy and quota monitoring would be necessary; for this project's actual usage pattern (one operator, manually triggering a batch job for 3 anomalies), it has not been a problem in practice and was not prioritized.

### Q20. How did you actually test this system — do you have a test suite?

Two different kinds of verification exist, and it's worth being precise about which is which. The frontend (`frontend/track3_app/tests/`) has an actual `pytest` suite: `test_loader.py`, `test_schemas.py`, `test_filters.py`, `test_formatting_i18n.py`, `test_brief_content.py`, `test_export.py`, `test_app_smoke.py` — these are real, automated, repeatable unit/integration tests written by the Track 3 owner. The integration layer connecting all three tracks was verified differently: not with a formal automated test suite, but by directly exercising the real code paths during integration and observing actual output — running the real Pydantic model against real data and reading the actual validation errors, booting the real Streamlit server and checking its logs, running `scripts/smoke_test.py` against a live API instance and reading pass/fail per route, and in several cases visually inspecting actual output images with the tool's own image-rendering capability rather than trusting pixel statistics alone. This is "verify by execution," not "verify by unit test coverage" — a real distinction worth naming if a judge asks about test coverage percentage, which does not exist as a tracked metric here.

### Q21. If I asked you to add a fourth document to the statutory corpus right now, what exactly would you do?

Concretely, in order: drop the PDF into `track2_rag/corpus/raw/`, add a row to `track2_rag/corpus/SOURCES.md` with its official title and source URL (this is also what `brief_adapter.py`'s `DOC_INFO` lookup table needs updated with, so citations to the new document get a real title/URL rather than falling back to the raw filename), delete `track2_rag/chroma_db/` (or just the collection) and re-run `track2_rag/rag/ingest.py` to re-chunk and re-embed the full corpus from scratch — there is no incremental/delta ingestion today, `ingest.py` processes every PDF in the raw folder on every run. This is a real, named limitation at corpus-update time, not a hidden one: adding one document means re-embedding the whole corpus, which at 231 chunks is cheap, but would not scale gracefully to a corpus of thousands of documents without adding incremental ingestion logic that does not currently exist.

---

## APPENDIX — Quick-reference fact sheet for live Q&A

- Embedding model: `BAAI/bge-m3`, via `sentence-transformers` 6.1.0
- Vector store: ChromaDB 1.5.9, `PersistentClient`, collection `statutory_rules`
- Corpus: 231 chunks, 5 PDFs, page-level chunking, distribution 194/14/11/6/6
- LLM: Google Gemini, via `google-generativeai` 0.8.6 (deprecated package, migration debt acknowledged)
- Retrieval: dense-only, `k=3`, cosine similarity (BM25 built but unused — be ready to say this plainly)
- Measured live brief generation latency: 238.8 seconds, one real call
- Detection thresholds (`step2.py`): `delta_vv_db > 3.0`, `delta_ndwi < -0.25`, persistence `≥4 of last 6 months and both of latest 2`, `min_area_ha = 0.1`
- Schema validation: `jsonschema` (Draft 2020-12) + Pydantic v2, at three independent points
- No auth, no rate limiting, no cloud deployment, no formal retrieval evaluation — stated as scoped hackathon-MVP tradeoffs, not hidden
