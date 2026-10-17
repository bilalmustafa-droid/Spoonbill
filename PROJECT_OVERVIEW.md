# Project Spoonbill — How It All Works

One page to present from, and one page to actually understand the code. Written after the three tracks were wired together; every file path and behavior below was checked against the real code, not recalled from memory.

## 1. The pitch, in two sentences

Hong Kong committed to "no net loss of wetland" for the Deep Bay / Mai Po fishpond belt. Spoonbill watches that commitment by detecting wetland-to-land conversions from satellite imagery, turning each detection into a citation-backed screening brief using HK's own planning guidelines, and showing both on a map a planning officer can actually use.

## 2. The three tracks, one sentence each

| Track | Folder | Job |
|---|---|---|
| **Track 1 — Remote Sensing** | `spatial/` | Detect wetland loss from Sentinel-1/2 satellite imagery, output `data/anomalies_v1.geojson` |
| **Track 2 — RAG / GenAI** | `track2_rag/` | Turn one detection into a bilingual, citation-backed legal brief using Gemini + retrieval over HK planning documents |
| **Track 3 — UI** | `frontend/track3_app/` | Streamlit dashboard a judge/officer looks at: map, filters, brief viewer, PDF/DOCX export |

Plus an **integration layer** (`track2_rag/api/`, `scripts/run_pipeline.py`) that makes the first two tracks' output land exactly where Track 3 expects it, in the exact shape it expects.

## 3. Tech stack

| Layer | Tech |
|---|---|
| Satellite data | Google Earth Engine Python API — Sentinel-1 (SAR, VV polarization) + Sentinel-2 (optical, NDWI) |
| Detection | Python, `shapely` for geometry, `jsonschema` for contract validation |
| RAG retrieval | Dense retrieval over a chunked statutory corpus: `chromadb` (vector store) + `sentence-transformers` (`BAAI/bge-m3` embedding model). `rank_bm25` is imported but not called in the live retrieval path — not a "hybrid" retriever yet, despite the class name. |
| Brief generation | Google Gemini (`google-generativeai`), prompted with retrieved statutory text chunks |
| Backend API (optional) | FastAPI + Uvicorn |
| UI | Streamlit, `streamlit-folium` (map), `python-docx` + `reportlab` (export) |
| Data contract | JSON Schema (`jsonschema`, Draft 2020-12) + Pydantic v2 (frontend's own stricter runtime model) |
| Corpus | 5 HK planning/EIA PDF guidance documents, chunked with PyMuPDF (`fitz`) |

No paid services. Gemini and Earth Engine both have free tiers used here.

## 4. How the files actually connect

```
spatial/step2.py                          track2_rag/rag/generator.py            frontend/track3_app/app.py
  (Earth Engine, SAR+NDWI fusion)            (Gemini + retrieval)                   (Streamlit)
        |                                         |                                      |
        v                                         v                                      v
data/anomalies_v1.geojson  ------------>  data/briefs/{anomaly_id}.json  ------>  reads both, renders map + brief
        ^                                         ^                                      ^
        |                                         |                                      |
  contract/anomaly.schema.json          contract/brief.schema.json           frontend/track3_app/core/models.py
  (what a valid detection                (what a valid brief                  (Pydantic v2 -- stricter than the
   must contain)                          must contain)                        JSON Schema, this is what actually
                                                                                 gates what renders)

                scripts/run_pipeline.py orchestrates the middle step:
                loads anomalies -> calls the generator for any missing brief
                -> reshapes the brief via track2_rag/api/brief_adapter.py
                -> writes everything into data/
```

**The one thing that makes this work with zero configuration:** `frontend/track3_app/core/config.py`'s `resolve_data_dir()` looks for `data/anomalies_v1.geojson` at the repo root first, before falling back to its own bundled demo fixtures. As long as that file exists and is valid, the UI shows real pipeline data automatically — nobody has to tell it where to look.

## 5. The data contract (the part all three tracks had to agree on)

Two schema files at `contract/`, both JSON Schema Draft 2020-12:

- **`contract/anomaly.schema.json`** — what `data/anomalies_v1.geojson` must contain. Every feature needs `anomaly_id` (`DB-####`), `site_id` (`SITE_A`/`SITE_B`/`SITE_C`), centroid, area, baseline/current VV (dB) and NDWI with their deltas, detection date, persistence count, confidence tier (`high`/`medium`/`low`), zone hint, an `optical_available` flag, and chip paths (nullable). `additionalProperties` isn't restricted, so extra fields like `synthetic: true` are allowed without breaking anything.
- **`contract/brief.schema.json`** — what `data/briefs/{id}.json` must contain. A brief is `cited` (has real citations), `abstained_human_review` (couldn't verify a citation, flagged for a human), or `error`. Citations must resolve to specific page/quote; every claim in the statutory basis must reference at least one citation id.

**Why this mattered in practice:** the real generator's raw output used different field names than this schema requires (`chunk_id` vs `id`, `document_title` vs `doc`, plain-string statutory basis vs `{claim, citation_ids}` objects). Every real brief would have shown as **invalid** in the UI without a reshaping step — see §7.

## 6. Module-by-module map

### Track 1 — `spatial/`
| File | Role |
|---|---|
| `step2.py` | The real detector. Sentinel-1 VV + Sentinel-2 NDWI monthly composites, 2023–2024 baseline climatology, a persistence filter (flagged ≥4 of last 6 months AND both of the latest 2), vectorizes surviving pixels, computes per-polygon stats, writes a schema-validated `anomalies_v1.geojson`. Needs a Google Earth Engine account + one-time browser login; `--self-test` proves the schema/export logic without needing Earth Engine at all. |
| `ruhan code.py` | A different, independent detector (optical-only, MNDWI-based before/after comparison) — not a diagnostic script. It is the one component in this project that has produced real before/after change signal over real imagery; `step2.py` has not yet returned a persistent detection for the site boxes tested (§9). Produces PNGs in `spoonbill_outputs_v2/`, not a GeoJSON. |

### Track 2 — `track2_rag/`
| File | Role |
|---|---|
| `main.py` | The FastAPI app. Mounts the integration router (§ below) and owns brief generation/caching (`fetch_or_generate_brief`). |
| `rag/retriever.py` | `HybridRetriever` — embeds the statutory corpus into Chroma with `BAAI/bge-m3`, retrieves top-k chunks for a query. Despite the name, `retrieve()` only queries the dense index; the BM25 sparse index it also builds is not called anywhere in the live path. |
| `rag/generator.py` | `BriefGenerator` — builds the prompt from an anomaly's properties + retrieved chunks, calls Gemini, runs a programmatic **cite-or-abstain guardrail** (drops any citation that doesn't verifiably match a retrieved chunk; forces `abstained_human_review` if none survive), then a **PDPO redaction pass** (regex-strips HKIDs/emails/phone numbers before anything is shown). |
| `rag/ingest.py` | One-off script: PDFs in `corpus/raw/` → `corpus/chunks.json`. Already run; chunks and the Chroma index are committed. |
| `batch_generate.py` | Standalone CLI for bulk brief generation. Superseded by `scripts/run_pipeline.py` for day-to-day use. |

### Integration layer — `track2_rag/api/` + `scripts/`
| File | Role |
|---|---|
| `api/anomalies_store.py` | Loads/caches the anomaly GeoJSON, filters by tier/site, computes dashboard stats. A missing file degrades gracefully (503 via the API); a malformed one fails loudly. |
| `api/brief_adapter.py` | Reshapes a brief from the generator's raw shape into the frontend's exact contract shape. Idempotent. Sources real document titles/URLs from `corpus/SOURCES.md` — never invents one. |
| `api/chips.py` | Safe chip-file resolution for the API path (traversal-proof, clean 404 when a chip isn't set). |
| `api/routes.py` | The new FastAPI routes: `/health`, `/api/anomalies*`, `/api/stats`, `/api/sites`, `/api/brief/{id}`. |
| `scripts/run_pipeline.py` | **The thing you actually run.** Loads anomalies, ensures every one has an adapted brief, writes `_overview.json`, copies chip assets — all into `data/`. Manual trigger only, never automatic. |
| `scripts/smoke_test.py` | Hits every API route, prints pass/fail. For the optional live-API path, not the UI. |

### Track 3 — `frontend/track3_app/`
| File | Role |
|---|---|
| `app.py` | Top-level wiring: resolves the data dir, loads anomalies/briefs/overview, lays out the page. |
| `core/config.py` | Path resolution (`resolve_data_dir`), constants, tier styling. **Contains the REPO_ROOT fix** — see §7. |
| `core/loader.py` | Reads and validates every contract file. Raises `ContractError` (human-readable) on any violation; never silently coerces bad data. |
| `core/models.py` | Pydantic v2 models mirroring the contract. This is the *real* gate on what data is accepted — stricter than the JSON Schema in a few places (e.g. `site_id` as a strict enum). |
| `core/filters.py`, `core/formatting.py`, `core/i18n.py` | Pure helper logic: filtering/sorting, number/date formatting (nulls always render as "not available", never 0 or blank), bilingual strings. |
| `core/content_guard.py` | Last-line screen on any upstream free text before it's rendered or exported. |
| `core/issues.py` | Auto-logs contract violations to `INTEGRATION_ISSUES.md` so the owning track sees them without digging through logs. |
| `ui/map_view.py` | Folium map, tier-colored polygons (plus a glyph/dash per tier, so it's colorblind-safe), click-to-select. |
| `ui/detail.py`, `ui/brief_view.py` | The right-hand detail panel and the brief renderer — handles every brief state (`cited`, `abstained_human_review`, `error`, `missing`, `invalid`) explicitly. |
| `ui/overview.py` | The optional dashboard tab, reads `data/briefs/_overview.json`. |
| `ui/demo.py` | A scripted click-path demo mode for live pitching. |
| `export/` | PDF (`reportlab`) and DOCX (`python-docx`) export, both built from one shared `report_model.py` so the two formats never drift apart. |

## 7. The three real bugs found and fixed while wiring this together

Worth mentioning in a presentation — these are the actual integration work, not boilerplate:

1. **The UI's "repo root" pointed one folder too shallow.** `core/config.py` computed its root as `track3_app/`'s parent, which is `frontend/` — not the true monorepo root. It could never find the real `data/`/`contract/` folders, so it silently always fell back to its own bundled demo fixtures. Two-line fix, now zero-config.
2. **The real brief output didn't match the UI's contract.** `generator.py` has always produced working, cited, bilingual briefs — but with different field names than the frontend's Pydantic model requires. Every real brief showed as "invalid" until `brief_adapter.py` reshaped it (without touching `generator.py` itself).
3. **The mock anomaly data was missing most required fields.** `contract/mock_anomalies.geojson` only had 6 of ~15 required properties. Completed using the project's own original frozen example values for consistency, each feature explicitly flagged `synthetic: true`.

## 8. How to run it

```
# 1. Refresh the data (only when you want new briefs or new detections)
python scripts\run_pipeline.py

# 2. Launch the UI
cd frontend\track3_app
run.bat
```

The UI never calls Earth Engine or Gemini itself — it only reads local files. Re-running the pipeline is the only way new data appears; the UI just reflects whatever's currently in `data/`.

Optional: the FastAPI layer (`API.md`) for live querying instead of static files — not required for the demo.

## 9. Honest state, for Q&A

- **The anomalies on screen are 3 mock examples**, clearly flagged `synthetic: true` in the raw data (though the UI's current model doesn't surface that flag visually — it's there in the file for anyone who inspects it).
- **The real detector (`spatial/step2.py`) runs against live Earth Engine data** and is methodologically faithful to the SAR+NDWI persistence approach — it just hasn't found a persistent detection in the two small site boxes tried so far. That's a real, diagnosed result (near-zero spatial-temporal overlap satisfying a deliberately strict rule), not a crash. Leading hypothesis for *why*: the wetness gate uses NDWI, and algae/floating vegetation on a healthy fishpond can push NDWI negative, incorrectly excluding real ponds before the detection rule ever runs — the same failure mode diagnosed in `ruhan code.py`'s MNDWI fix. Not yet re-tested in `step2.py`.
- **Briefs are real.** The Gemini + retrieval + cite-or-abstain + PDPO-redaction pipeline is genuinely live and was verified end-to-end with a real API call, not stubbed.
- **Chip images exist but aren't yet linked to specific anomalies** — the 20 PNGs in `spatial/spoonbill_outputs_v2/` are real before/after satellite imagery, just not tied to a `DB-000x` ID yet.
