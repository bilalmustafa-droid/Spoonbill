# Project Spoonbill — Backend Pipeline and Output Folder

Two independent pipelines:

- **Backend pipeline** (this doc): runs manually, on demand, never automatically. It consolidates the anomaly data, generates/refreshes briefs, computes stats, and writes everything the UI needs into one static output folder.
- **Frontend**: reads that output folder directly as static files. It does not call a live API and does not need to be rerun when the backend pipeline is rerun — it will pick up whatever is currently on disk the next time it reads.

The conceptual cadence (per Track 1's own plan in `spatial/TRACK_1_REMOTE_SENSING_GIS.md`) is roughly every 30 days once Track 1's real detection pipeline exists. For now, run it by hand whenever you want fresh output.

## Run it

```
python scripts/run_pipeline.py
```

Options:
- `--force` — regenerate every brief from scratch, ignoring the existing cache in `data/briefs/`. Each live generation call has been observed to take around 4 minutes, so only use this when you actually need fresh briefs.
- `--skip-briefs` — refresh anomalies/stats/sites only, skip the RAG pipeline entirely (useful if `GEMINI_API_KEY` isn't configured or you just want a fast refresh).
- `--output-dir PATH` — write somewhere other than `output/` (default).

## What the frontend should read

Point the UI at the `output/` folder (repo root, gitignored — it's regenerated, not committed):

```
output/
├── anomalies.geojson   # the frozen-contract FeatureCollection, passed through unmodified
├── stats.json          # dashboard aggregates (tier counts, total hectares, site breakdown, date window)
├── sites.json          # static AOI bbox + showcase site reference data
├── briefs/
│   └── DB-0001.json    # one file per anomaly_id, same shape as data/briefs/
├── chips/
│   └── *.png           # raw chip images copied as-is
└── manifest.json       # run metadata: when it ran, which source file was used, per-anomaly brief status, chip count
```

Read these as plain static files (`json.load(open("output/anomalies.geojson"))`, etc.) — no server process required.

## Known limitations, read before demo day

- **`anomalies.geojson` is still the 3-feature mock.** Track 1's real detection script (`step2.py` per their own plan, producing `data/anomalies_v1.geojson`) does not exist in this repo yet — only a diagnostic chip-generation script (`spatial/ruhan code.py`, needs live interactive Earth Engine auth) exists, and it does not produce anomaly polygons. The pipeline reads from `SPOONBILL_ANOMALIES_PATH` (default `contract/mock_anomalies.geojson`); once Track 1 delivers the real file, set that env var and rerun — no code change needed anywhere in this pipeline or the API.
- **`chips/` has no anomaly_id linkage.** The 20 PNGs come from `spatial/spoonbill_outputs_v2/` and are named by site/year, not by `DB-000x`. They're copied as raw assets so the UI has access to real imagery, but nothing in this repo maps a specific chip to a specific anomaly — that mapping doesn't exist yet and wasn't invented.
- **`manifest.json` tells you if something's stale or failed.** Check `generator_available` and the per-anomaly `briefs` status before trusting the briefs folder blindly — if a brief's `status` is `"error"`, the old cached version (if any) is still in `data/briefs/`, but `output/briefs/` won't have been refreshed for that one.

The FastAPI app (`track2_rag/main.py`, documented in `API.md`) still works independently if you want live querying instead of static files — nothing about this pipeline removes or changes it. The two are separate, equally valid ways to get at the same underlying data.
