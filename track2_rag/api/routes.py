"""
Integration routes mounted onto the existing Track 2 FastAPI app
(track2_rag/main.py). These wrap existing modules rather than reimplementing
them -- brief generation stays in main.py's fetch_or_generate_brief, the RAG
pipeline stays in track2_rag/rag/.
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from track2_rag.api import anomalies_store, chips

router = APIRouter()

SITES_PATH = "contract/sites.json"


@lru_cache(maxsize=1)
def _load_sites() -> dict:
    with open(SITES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _anomalies_or_503() -> dict:
    try:
        return anomalies_store.load_anomalies()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Anomaly data source not available.")


@router.get("/health")
def health():
    import track2_rag.main as main_module

    anomalies_status = anomalies_store.get_cache_status()

    return {
        "status": "ok",
        "anomalies": anomalies_status,
        "rag": {
            "generator_ready": main_module.generator is not None,
            "generator_init_error": main_module.generator_init_error,
            "offline_mode": main_module.OFFLINE_MODE,
            "chroma_dir_present": Path(main_module.CHROMA_DIR).exists(),
            "chunks_file_present": Path(main_module.CHUNKS_PATH).exists(),
        },
        "gemini_api_key_configured": bool(
            __import__("os").getenv("GEMINI_API_KEY")
        ) or Path("track2_rag/.env").exists(),
    }


@router.get("/api/anomalies")
def get_anomalies(
    tier: Optional[str] = None,
    site_id: Optional[str] = None,
    include_low: bool = False,
):
    feature_collection = _anomalies_or_503()
    filtered = anomalies_store.filter_features(
        feature_collection, tier=tier, site_id=site_id, include_low=include_low
    )
    return {"type": "FeatureCollection", "features": filtered}


@router.get("/api/anomalies/{anomaly_id}")
def get_anomaly(anomaly_id: str):
    feature_collection = _anomalies_or_503()
    feature = anomalies_store.get_feature_by_id(feature_collection, anomaly_id)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Anomaly ID {anomaly_id} not found.")
    return feature


@router.get("/api/anomalies/{anomaly_id}/chips/{side}")
def get_chip(anomaly_id: str, side: Literal["before", "after"]):
    feature_collection = _anomalies_or_503()
    feature = anomalies_store.get_feature_by_id(feature_collection, anomaly_id)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Anomaly ID {anomaly_id} not found.")

    try:
        chip_path = chips.resolve_chip_path(feature, side)
    except chips.ChipNotAvailable as e:
        raise HTTPException(
            status_code=404,
            detail={"available": False, "anomaly_id": anomaly_id, "side": side, "reason": e.reason},
        )

    return FileResponse(chip_path, media_type="image/png")


@router.get("/api/stats")
def get_stats():
    feature_collection = _anomalies_or_503()
    return anomalies_store.compute_stats(feature_collection)


@router.get("/api/sites")
def get_sites():
    return _load_sites()


@router.post("/api/brief/{anomaly_id}")
def post_brief(anomaly_id: str):
    import track2_rag.main as main_module

    return main_module.fetch_or_generate_brief(anomaly_id)
