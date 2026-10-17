"""
Backend pipeline for Project Spoonbill. Run this manually whenever you want to
refresh the data the UI reads -- it does NOT run automatically or on a
schedule. The intended cadence (per PROJECT_CONTEXT.md / Track 1's own plan)
is roughly every 30 days once Track 1's real detection pipeline is reliably
producing results; for now, run it by hand whenever the anomaly source file
changes or you want briefs regenerated.

Writes directly into data/ at the repo root -- this is exactly where
frontend/track3_app/core/config.py's resolve_data_dir() looks first, so the
UI picks this up automatically with zero configuration. No separate output
folder, no env var needed on the UI side.

What it does, in order:
1. Loads the anomaly FeatureCollection from SPOONBILL_ANOMALIES_PATH (default
   contract/mock_anomalies.geojson, which is now a complete, schema-valid
   file -- see contract/anomaly.schema.json). Point SPOONBILL_ANOMALIES_PATH
   at data/anomalies_v1.geojson once Track 1's spatial/step2.py produces real
   detections; no code change needed here, just an env var.
2. Writes it to data/anomalies_v1.geojson, pass-through, unmodified.
3. Ensures every feature has a brief in data/briefs/{id}.json -- cache hit if
   present, otherwise a live call through the existing RAG pipeline
   (track2_rag/rag/generator.py). This can take several minutes per anomaly
   on a cache miss (observed ~4 minutes per live Gemini call). Every brief,
   cached or fresh, is passed through brief_adapter.adapt_brief_for_frontend()
   before being written, since the generator's raw output does not match the
   frontend's Pydantic Brief model (different citation field names, plain-
   string statutory_basis) -- see track2_rag/api/brief_adapter.py for why.
4. Writes data/briefs/_overview.json (the optional Phase 2 dashboard summary
   frontend/track3_app/ui/overview.py reads).
5. Copies whatever chip PNGs exist in spatial/spoonbill_outputs_v2/ into
   data/chips/ as raw assets -- NOT linked to any anomaly_id (Track 1 hasn't
   populated chip_before_png/chip_after_png yet), so no per-anomaly mapping
   is invented; every current feature has those fields set to null.

Usage:
    python scripts/run_pipeline.py
    python scripts/run_pipeline.py --force          # regenerate every brief, ignore cache
    python scripts/run_pipeline.py --skip-briefs    # anomalies/overview only, no RAG calls
    python scripts/run_pipeline.py --data-dir X     # write elsewhere (advanced/testing only)
"""
import argparse
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from track2_rag.api import anomalies_store
from track2_rag.api.brief_adapter import adapt_brief_for_frontend

SITES_SOURCE = REPO_ROOT / "contract" / "sites.json"
CHIPS_SOURCE_DIR = REPO_ROOT / "spatial" / "spoonbill_outputs_v2"


def ensure_brief(briefs_dir: Path, anomaly_id: str, feature: dict, force: bool, generator):
    """Returns (brief_dict, source) where source is 'cached' or 'generated'.
    Always returns the frontend-adapted shape, regardless of source."""
    cache_path = briefs_dir / f"{anomaly_id}.json"
    if cache_path.exists() and not force:
        with open(cache_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        adapted = adapt_brief_for_frontend(raw)
        if adapted != raw:  # upgrade a legacy-shaped cache file in place
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(adapted, f, ensure_ascii=False, indent=2)
        return adapted, "cached"

    if generator is None:
        raise RuntimeError(
            "no cached brief and BriefGenerator is unavailable "
            "(missing GEMINI_API_KEY or a RAG dependency) -- "
            "set GEMINI_API_KEY and retry, or run without --force to use the existing cache"
        )

    brief = adapt_brief_for_frontend(generator.generate_brief(feature))
    briefs_dir.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(brief, f, ensure_ascii=False, indent=2)
    return brief, "generated"


def build_overview(feature_collection: dict, brief_results: dict) -> dict:
    features = feature_collection.get("features", [])
    total_area = sum(f["properties"].get("area_ha") or 0 for f in features)
    by_site: dict = {}
    for f in features:
        site = f["properties"].get("site_id") or "unknown"
        by_site[site] = by_site.get(site, 0) + 1
    needing_review = sum(
        1 for aid, r in brief_results.items()
        if r.get("status") == "ok" and r.get("human_review_required")
    )
    return {
        "en": {
            "title": "Deep Bay Wetland Monitoring Overview",
            "summary": f"{len(features)} anomal{'y' if len(features) == 1 else 'ies'} currently tracked "
                       f"across {len(by_site)} site(s), totalling {total_area:.2f} ha.",
        },
        "zh_hant": {
            "title": "深圳灣濕地監測概覽",
            "summary": f"目前追蹤 {len(features)} 個異常點，分布於 {len(by_site)} 個地點，總面積 {total_area:.2f} 公頃。",
        },
        "totals": {
            "anomaly_count": len(features),
            "total_area_ha": round(total_area, 2),
            "needing_review": needing_review,
            "by_site": by_site,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="Regenerate every brief, ignoring the cache")
    parser.add_argument("--skip-briefs", action="store_true", help="Skip brief generation entirely")
    parser.add_argument("--data-dir", default=str(REPO_ROOT / "data"))
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    briefs_dir = data_dir / "briefs"
    chips_dir = data_dir / "chips"
    briefs_dir.mkdir(parents=True, exist_ok=True)
    chips_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/5] Loading anomalies from {anomalies_store.ANOMALIES_PATH} ...")
    feature_collection = anomalies_store.load_anomalies(force_reload=True)
    features = feature_collection.get("features", [])
    print(f"      loaded {len(features)} feature(s)")

    print(f"[2/5] Writing {data_dir / 'anomalies_v1.geojson'} (pass-through, unmodified) ...")
    with open(data_dir / "anomalies_v1.geojson", "w", encoding="utf-8") as f:
        json.dump(feature_collection, f, ensure_ascii=False, indent=2)

    generator = None
    generator_error = None
    brief_results: dict = {}

    if args.skip_briefs:
        print("[3/5] Skipping brief generation (--skip-briefs)")
    else:
        needs_generation = args.force or any(
            not (briefs_dir / f"{f['properties']['anomaly_id']}.json").exists()
            for f in features
        )
        if needs_generation:
            print("[3/5] At least one brief needs live generation -- initializing BriefGenerator ...")
            try:
                from track2_rag.rag.generator import BriefGenerator
                generator = BriefGenerator("track2_rag/chroma_db", "track2_rag/corpus/chunks.json")
            except Exception as e:
                generator_error = str(e)
                print(f"      WARNING: BriefGenerator unavailable ({e}); only cached briefs will be used")
        else:
            print("[3/5] All briefs already cached, re-shaping for the frontend contract only")

        for feature in features:
            anomaly_id = feature["properties"]["anomaly_id"]
            t0 = time.time()
            try:
                brief, source = ensure_brief(briefs_dir, anomaly_id, feature, args.force, generator)
                elapsed = round(time.time() - t0, 1)
                brief_results[anomaly_id] = {
                    "status": "ok", "source": source, "seconds": elapsed,
                    "human_review_required": brief.get("human_review_required", False),
                }
                print(f"      {anomaly_id}: {source} ({elapsed}s)")
            except Exception as e:
                brief_results[anomaly_id] = {"status": "error", "error": str(e)}
                print(f"      {anomaly_id}: FAILED -- {e}")

    print(f"[4/5] Writing {briefs_dir / '_overview.json'} ...")
    overview = build_overview(feature_collection, brief_results)
    with open(briefs_dir / "_overview.json", "w", encoding="utf-8") as f:
        json.dump(overview, f, ensure_ascii=False, indent=2)

    print("[5/5] Copying chip images (raw assets, not yet linked to any anomaly_id) ...")
    chip_count = 0
    if CHIPS_SOURCE_DIR.exists():
        for png in CHIPS_SOURCE_DIR.glob("*.png"):
            shutil.copy(png, chips_dir / png.name)
            chip_count += 1
    print(f"      copied {chip_count} chip image(s)")

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "anomalies_source": str(anomalies_store.ANOMALIES_PATH),
        "feature_count": len(features),
        "briefs": brief_results,
        "chip_count": chip_count,
        "generator_available": generator is not None,
        "generator_error": generator_error,
    }
    with open(data_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\nDone. UI reads static files directly from: {data_dir.resolve()}")
    failed = [k for k, v in brief_results.items() if v.get("status") == "error"]
    if failed:
        print(f"WARNING: {len(failed)} brief(s) failed: {failed}")
        sys.exit(1)


if __name__ == "__main__":
    main()
