# Project Spoonbill — Integration API

One FastAPI app (built on Track 2's existing `track2_rag/main.py`) serving everything the Track 3 UI needs: anomalies, stats, sites, chip images, and briefs.

## Start command

From the repo root (not from inside `track2_rag/`):

```
python -m uvicorn track2_rag.main:app --reload --port 8000
```

Install dependencies first:

```
pip install -r requirements.txt
```

Copy `.env.example` to `.env` at the repo root if you want to override any of the optional env vars (none are required — the app starts and serves anomalies/stats/sites with zero configuration).

### Environment variables

| Variable | Default | Effect |
|---|---|---|
| `GEMINI_API_KEY` | (read from `track2_rag/.env` if unset) | Needed only for live brief generation. Everything else works without it. |
| `SPOONBILL_ANOMALIES_PATH` | `contract/mock_anomalies.geojson` | Path to the anomaly GeoJSON FeatureCollection. Point this at `data/anomalies_v1.geojson` once Track 1 delivers it — no code change needed. |
| `SPOONBILL_OFFLINE` | unset | Set to `1` to disable all live Gemini calls. Brief endpoints then serve only cached `data/briefs/*.json` files and return 503 on a cache miss. Use for no-wifi demos. |

## Endpoints

### `GET /`
Legacy liveness route from Track 2, unchanged.
```
curl http://127.0.0.1:8000/
-> {"status": "online", "service": "Project Spoonbill RAG API"}
```

### `GET /health`
Readiness report. Never throws, even with everything missing.
```
curl http://127.0.0.1:8000/health
```
```json
{
  "status": "ok",
  "anomalies": {
    "path_configured": "contract/mock_anomalies.geojson",
    "path_resolved": "C:\\...\\contract\\mock_anomalies.geojson",
    "loaded": true,
    "feature_count": 3,
    "error": null
  },
  "rag": {
    "generator_ready": true,
    "generator_init_error": null,
    "offline_mode": false,
    "chroma_dir_present": true,
    "chunks_file_present": true
  },
  "gemini_api_key_configured": true
}
```

### `GET /api/anomalies`
The FeatureCollection, passed through unmodified. Query params: `tier`, `site_id`, `include_low` (default `false`).
```
curl "http://127.0.0.1:8000/api/anomalies"
curl "http://127.0.0.1:8000/api/anomalies?tier=high"
curl "http://127.0.0.1:8000/api/anomalies?include_low=true"
curl "http://127.0.0.1:8000/api/anomalies?site_id=mai_po_4p3ha"
```
`confidence_tier: "low"` features are excluded unless `include_low=true` — they are never dropped from the underlying data, only hidden by default in this listing.

### `GET /api/anomalies/{anomaly_id}`
Single feature lookup. 404 if not found.
```
curl http://127.0.0.1:8000/api/anomalies/DB-0001
```

### `GET /api/anomalies/{anomaly_id}/chips/{before|after}`
Serves the chip PNG bytes if the feature has a `chip_before_png`/`chip_after_png` property pointing at a real file. The current mock data has no chip fields, so this returns a clean 404 today — not a guessed image.
```
curl http://127.0.0.1:8000/api/anomalies/DB-0001/chips/before
```
404 body shape:
```json
{"available": false, "anomaly_id": "DB-0001", "side": "before", "reason": "no chip_before_png recorded for this anomaly"}
```
`{before|after}` is validated by FastAPI — any other value returns 422 automatically.

### `GET /api/stats`
Dashboard summary computed live from the loaded GeoJSON.
```
curl http://127.0.0.1:8000/api/stats
```
```json
{
  "total_anomalies": 3,
  "tier_counts": {"high": 0, "medium": 0, "low": 0, "unknown": 3},
  "total_area_ha": 5.37,
  "area_ha_unknown_count": 0,
  "site_breakdown": {"unknown": {"count": 3, "total_area_ha": 5.37}},
  "first_detection_date_min": "2025-04-15",
  "first_detection_date_max": "2025-06-10",
  "date_unknown_count": 0,
  "generated_at": "2026-10-15T12:00:00+00:00"
}
```
Missing `area_ha`/`confidence_tier`/`site_id`/`first_detection_date` values are counted explicitly (`unknown` bucket, `*_unknown_count`) rather than coerced to 0 or dropped silently.

### `GET /api/sites`
Static, hand-maintained reference data (AOI bounding box + showcase site names) — not generated detection output.
```
curl http://127.0.0.1:8000/api/sites
```

### `GET /api/v1/briefs/{anomaly_id}` (legacy, unchanged path)
### `POST /api/brief/{anomaly_id}` (new alias, same underlying logic)
Both call the same `fetch_or_generate_brief` function: serve from `data/briefs/{id}.json` if cached, else call the RAG pipeline (unless offline mode or the generator is unavailable, in which case 503).
```
curl http://127.0.0.1:8000/api/v1/briefs/DB-0001
curl -X POST http://127.0.0.1:8000/api/brief/DB-0002
```
- 404 if the anomaly_id doesn't exist.
- 503 `"Offline mode active..."` if `SPOONBILL_OFFLINE=1` and there's no cache hit.
- 503 `"BriefGenerator unavailable: ..."` if the RAG pipeline failed to initialize (e.g. missing dependency or API key) and there's no cache hit.
- A live Gemini failure never surfaces as an HTTP error — the generator's own cite-or-abstain guardrail returns a well-formed `status: "abstained_human_review"` brief as a normal 200 response instead.

## What's faked, cached, or degraded

- **Anomaly data is the 3-feature mock** (`contract/mock_anomalies.geojson`), not Track 1's real output — `data/anomalies_v1.geojson` doesn't exist yet. Swap via `SPOONBILL_ANOMALIES_PATH`.
- **Chips always 404 today** — the real PNGs in `spatial/spoonbill_outputs_v2/` are not linked to any anomaly_id; no mapping was fabricated.
- **Briefs for DB-0001/0002/0003 are served from a pre-generated disk cache** (`data/briefs/*.json`), not a live call, on every request against those three IDs.
- **CORS is wide open** (`allow_origins=["*"]`) — fine for a local demo, not production-ready.
- **`site_id` filter always returns empty** against current mock data — correct, not a bug (no mock feature has a `site_id`).

## Changes made to existing files

Only `track2_rag/main.py` was edited:
1. The `BriefGenerator` import and construction were combined into one try/except so a missing RAG dependency degrades to a 503 instead of crashing the whole process at import time.
2. Added an `SPOONBILL_OFFLINE` check that skips `BriefGenerator` construction entirely when set.
3. Refactored the body of `get_brief()` into `fetch_or_generate_brief()`, reused by both the legacy `GET /api/v1/briefs/{id}` route and the new `POST /api/brief/{id}` route. It now looks up anomalies through the shared `anomalies_store` module (configurable path) instead of its own inline two-path scan.
4. Mounted the new `track2_rag/api/routes.py` router.

Nothing in `spatial/` or `frontend/` was touched. `track2_rag/.env` was left untouched per instruction — rotate/clean up that secret separately.

## Smoke test

```
python -m uvicorn track2_rag.main:app --port 8000
python scripts/smoke_test.py
```

To also check offline-mode behavior, start a second server with `SPOONBILL_OFFLINE=1` set and run `python scripts/smoke_test.py --assume-offline` against it.
