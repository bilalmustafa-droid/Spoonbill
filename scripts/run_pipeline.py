"""
Backend pipeline for Project Spoonbill. Run this manually whenever you want to
refresh the data the UI reads -- it does NOT run automatically or on a
schedule. The intended cadence (per PROJECT_CONTEXT.md / Track 1's own plan)
is roughly every 30 days once Track 1's real detection pipeline exists; for
now, run it by hand whenever the anomaly source file changes or you want
briefs regenerated.

What it does, in order:
1. Loads the anomaly FeatureCollection from SPOONBILL_ANOMALIES_PATH (default
   contract/mock_anomalies.geojson). This script does NOT generate anomaly
   detections itself -- that is Track 1's job (their own plan calls for a
   `step2.py` producing data/anomalies_v1.geojson, which does not exist in
   this repo yet). Point SPOONBILL_ANOMALIES_PATH at the real file once it
   exists; no code change needed here.
2. Ensures every feature has a brief -- cache hit from data/briefs/{id}.json
   if present, otherwise a live call through the existing RAG pipeline
   (track2_rag/rag/generator.py). This can take several minutes per anomaly
   on a cache miss (observed ~4 minutes per live Gemini call) -- plan runs
   accordingly, or use --skip-briefs to defer that step.
3. Computes dashboard stats from the loaded anomalies.
4. Copies the static sites reference (contract/sites.json).
5. Copies whatever chip PNGs exist in spatial/spoonbill_outputs_v2/ as raw
   assets -- these are NOT currently linked to specific anomaly_id values
   (Track 1 hasn't populated chip_before_png/chip_after_png yet), so no
   per-anomaly mapping is invented here; the UI gets the files but not a
   fabricated association.

Everything lands in one output folder (default `output/`) that the frontend
can read directly as static files -- no API server required for the demo.

Usage:
    python scripts/run_pipeline.py
    python scripts/run_pipeline.py --force          # regenerate every brief, ignore cache
    python scripts/run_pipeline.py --skip-briefs    # anomalies/stats/sites only, no RAG calls
    python scripts/run_pipeline.py --output-dir X   # write elsewhere
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

BRIEFS_CACHE_DIR = REPO_ROOT / "data" / "briefs"
SITES_SOURCE = REPO_ROOT / "contract" / "sites.json"
CHIPS_SOURCE_DIR = REPO_ROOT / "spatial" / "spoonbill_outputs_v2"


def ensure_brief(anomaly_id: str, feature: dict, force: bool, generator):
    """Returns (brief_dict, source) where source is 'cached' or 'generated'."""
    cache_path = BRIEFS_CACHE_DIR / f"{anomaly_id}.json"
    if cache_path.exists() and not force:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f), "cached"

    if generator is None:
        raise RuntimeError(
            "no cached brief and BriefGenerator is unavailable "
            "(missing GEMINI_API_KEY or a RAG dependency) -- "
            "set GEMINI_API_KEY and retry, or run without --force to use the existing cache"
        )

    brief = generator.generate_brief(feature)
    BRIEFS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(brief, f, ensure_ascii=False, indent=2)
    return brief, "generated"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="Regenerate every brief, ignoring the cache")
    parser.add_argument("--skip-briefs", action="store_true", help="Skip brief generation entirely")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "output"))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    briefs_out_dir = output_dir / "briefs"
    chips_out_dir = output_dir / "chips"
    briefs_out_dir.mkdir(parents=True, exist_ok=True)
    chips_out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/5] Loading anomalies from {anomalies_store.ANOMALIES_PATH} ...")
    feature_collection = anomalies_store.load_anomalies(force_reload=True)
    features = feature_collection.get("features", [])
    print(f"      loaded {len(features)} features")

    print("[2/5] Writing anomalies.geojson (pass-through, unmodified) ...")
    with open(output_dir / "anomalies.geojson", "w", encoding="utf-8") as f:
        json.dump(feature_collection, f, ensure_ascii=False, indent=2)

    generator = None
    generator_error = None
    brief_results = {}

    if args.skip_briefs:
        print("[3/5] Skipping brief generation (--skip-briefs)")
    else:
        needs_generation = args.force or any(
            not (BRIEFS_CACHE_DIR / f"{f['properties']['anomaly_id']}.json").exists()
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
            print("[3/5] All briefs already cached, skipping generator init")

        for feature in features:
            anomaly_id = feature["properties"]["anomaly_id"]
            t0 = time.time()
            try:
                brief, source = ensure_brief(anomaly_id, feature, args.force, generator)
                elapsed = round(time.time() - t0, 1)
                brief_results[anomaly_id] = {"status": "ok", "source": source, "seconds": elapsed}
                shutil.copy(BRIEFS_CACHE_DIR / f"{anomaly_id}.json", briefs_out_dir / f"{anomaly_id}.json")
                print(f"      {anomaly_id}: {source} ({elapsed}s)")
            except Exception as e:
                brief_results[anomaly_id] = {"status": "error", "error": str(e)}
                print(f"      {anomaly_id}: FAILED -- {e}")

    print("[4/5] Computing stats ...")
    stats = anomalies_store.compute_stats(feature_collection)
    with open(output_dir / "stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print("[5/5] Copying sites reference and chip images ...")
    if SITES_SOURCE.exists():
        shutil.copy(SITES_SOURCE, output_dir / "sites.json")
    else:
        print(f"      WARNING: {SITES_SOURCE} not found, skipping")

    chip_count = 0
    if CHIPS_SOURCE_DIR.exists():
        for png in CHIPS_SOURCE_DIR.glob("*.png"):
            shutil.copy(png, chips_out_dir / png.name)
            chip_count += 1
    print(f"      copied {chip_count} chip image(s) -- NOTE: not linked to any anomaly_id yet, "
          f"see chip_before_png/chip_after_png on each feature once Track 1 populates them")

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "anomalies_source": str(anomalies_store.ANOMALIES_PATH),
        "feature_count": len(features),
        "briefs": brief_results,
        "chip_count": chip_count,
        "chip_to_anomaly_mapping": "none (not yet available from Track 1)",
        "generator_available": generator is not None,
        "generator_error": generator_error,
    }
    with open(output_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\nDone. UI should read static files from: {output_dir.resolve()}")
    failed = [k for k, v in brief_results.items() if v.get("status") == "error"]
    if failed:
        print(f"WARNING: {len(failed)} brief(s) failed: {failed}")
        sys.exit(1)


if __name__ == "__main__":
    main()
