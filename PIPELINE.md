# Project Spoonbill — Backend Pipeline and the UI's Data Folder

Two independent pipelines:

- **Backend pipeline** (this doc): runs manually, on demand, never automatically. It consolidates the anomaly data, generates/refreshes briefs, and writes everything the UI needs into `data/` at the repo root.
- **Frontend** (`frontend/track3_app/`): reads `data/` directly as static files, with zero configuration. It does not call a live API and does not auto-regenerate anything — it just reads whatever is currently on disk. Re-run the backend pipeline yourself whenever you want the UI to show something new; the UI picks it up next time it loads, nothing else needed.

The conceptual cadence (per Track 1's own plan in `spatial/TRACK_1_REMOTE_SENSING_GIS.md`) is roughly every 30 days once Track 1's real detection pipeline is reliably producing results. For now, run it by hand.

## Run it

```
python scripts/run_pipeline.py
```

Options:
- `--force` — regenerate every brief from scratch, ignoring the existing cache in `data/briefs/`. Each live generation call has been observed to take around 4 minutes, so only use this when you actually need fresh briefs.
- `--skip-briefs` — refresh `anomalies_v1.geojson`/`_overview.json` only, skip the RAG pipeline entirely (useful if `GEMINI_API_KEY` isn't configured, or you just changed the anomaly source and don't need new briefs).
- `--data-dir PATH` — write somewhere other than `data/` (advanced/testing only — the UI won't find it there without `SPOONBILL_DATA_DIR` set to match).

## What it writes

```
data/
├── anomalies_v1.geojson   # the frozen-contract FeatureCollection, passed through unmodified
├── manifest.json          # run metadata: when it ran, which source file was used, per-anomaly brief status
├── briefs/
│   ├── DB-0001.json       # one file per anomaly_id, reshaped to match the frontend's Brief model
│   ├── DB-0002.json
│   ├── DB-0003.json
│   └── _overview.json     # optional dashboard summary (frontend/track3_app/ui/overview.py)
├── chips/
│   └── *.png              # raw chip images copied as-is
└── archive/
    └── ...                 # old/empty results kept for reference, not read by anything
```

This is exactly where `frontend/track3_app/core/config.py`'s `resolve_data_dir()` looks first (origin `"repo"`), so the UI picks it up automatically — no env var, no `--data-dir` flag needed on the UI side.

## The brief-shape fix (why `brief_adapter.py` exists)

`track2_rag/rag/generator.py`'s real output (citations keyed by `chunk_id`/`document_title`/`page_number`/`verbatim_quote`, `statutory_basis` as plain strings) does not match what the frontend's Pydantic `Brief` model and `contract/brief.schema.json` actually require (citations keyed by `id`/`doc`/`doc_title_zh`/`page`/`section`/`quote`/`source_url`, `statutory_basis` as `{claim, citation_ids}` objects). Every real generated brief would show as **invalid** in the UI without this.

`track2_rag/api/brief_adapter.py` reshapes every brief — cached or freshly generated — before it's written to `data/briefs/`. It is idempotent (safe to run repeatedly) and sources document titles/URLs from `track2_rag/corpus/SOURCES.md`, never invents them. `doc_title_zh` falls back to the English title since no official Chinese title exists in that source; `citation_ids` on each claim lists every citation actually used in the brief, since the generator doesn't track which citation supports which specific claim and the schema rejects an empty list.

This does not touch `track2_rag/rag/generator.py` itself — the RAG pipeline keeps producing its original shape; the adapter runs as a separate step.

## Known limitations, read before demo day

- **`anomalies_v1.geojson` is still 3 hand-completed mock anomalies**, explicitly flagged `synthetic: true` in each feature's properties. Track 1's real detection script (`spatial/step2.py`) exists and runs against live Earth Engine data, but came back with 0 persistent anomalies in the two site boxes tried so far (confirmed not a bug — see the commit history on `spatial/step2.py` for the diagnostic numbers). Point `SPOONBILL_ANOMALIES_PATH` at a real `data/anomalies_v1.geojson` once Track 1 produces one with actual detections, then rerun this pipeline — no code change needed.
- **`chips/` has no anomaly_id linkage.** Every feature's `chip_before_png`/`chip_after_png` is `null`. The 20 PNGs copied into `data/chips/` come from `spatial/spoonbill_outputs_v2/` and are named by site/year, not by `DB-000x` — they're available as raw assets but nothing maps a specific chip to a specific anomaly.
- **`manifest.json` tells you if something's stale or failed.** Check `generator_available` and the per-anomaly `briefs` status before assuming `data/briefs/` is fully fresh.

The FastAPI app (`track2_rag/main.py`, documented in `API.md`) still works independently if you want live querying instead of static files — nothing about this pipeline removes or changes it.
