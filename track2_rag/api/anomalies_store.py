"""
Loads and caches the anomaly FeatureCollection that Track 1 (GIS) produces and
that Track 2 (RAG) and Track 3 (UI) both read. The GeoJSON contract is frozen:
this module must never reshape, rename, retype, or drop any property -- it
only loads, caches, and filters the feature list.

Path precedence: SPOONBILL_ANOMALIES_PATH env var, else
contract/mock_anomalies.geojson. This lets the real Track 1 output
(data/anomalies_v1.geojson) replace the mock later with zero code changes.

A *missing* file is a degraded-service condition: callers get a cached
"not loaded" state and /health reports it without the process crashing. A
*malformed* file (bad JSON, not a FeatureCollection, a feature with no
anomaly_id) is bad data: load_anomalies() raises and lets that propagate loud,
per the project's "fail loud on bad data, degrade gracefully on missing
services" rule.
"""
import json
import os
from pathlib import Path
from typing import Optional

ANOMALIES_PATH = os.getenv("SPOONBILL_ANOMALIES_PATH", "contract/mock_anomalies.geojson")

_cache: Optional[dict] = None
_cache_error: Optional[str] = None


class AnomalyDataError(Exception):
    """Raised when the anomaly GeoJSON file exists but is malformed."""


def _validate_feature_collection(data: dict, path: str) -> None:
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise AnomalyDataError(f"{path} is not a GeoJSON FeatureCollection")
    features = data.get("features")
    if not isinstance(features, list):
        raise AnomalyDataError(f"{path} has no 'features' array")
    for i, feature in enumerate(features):
        props = feature.get("properties") if isinstance(feature, dict) else None
        if not isinstance(props, dict) or not props.get("anomaly_id"):
            raise AnomalyDataError(f"{path}: feature at index {i} is missing properties.anomaly_id")


def load_anomalies(force_reload: bool = False) -> dict:
    """Returns the cached FeatureCollection, loading it on first call.

    Raises AnomalyDataError if the file exists but is malformed (loud failure).
    Returns None-equivalent state (via _cache staying None) if the file is
    missing -- callers should check get_cache_status() or catch the
    FileNotFoundError this raises and translate it to a 503.
    """
    global _cache, _cache_error
    if _cache is not None and not force_reload:
        return _cache

    if not Path(ANOMALIES_PATH).exists():
        _cache_error = f"file not found: {ANOMALIES_PATH}"
        raise FileNotFoundError(_cache_error)

    with open(ANOMALIES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    _validate_feature_collection(data, ANOMALIES_PATH)

    _cache = data
    _cache_error = None
    return _cache


def get_cache_status() -> dict:
    """Never raises -- used by /health to report readiness without risk."""
    resolved_path = None
    try:
        resolved_path = str(Path(ANOMALIES_PATH).resolve())
    except Exception:
        pass

    try:
        fc = load_anomalies()
        return {
            "path_configured": ANOMALIES_PATH,
            "path_resolved": resolved_path,
            "loaded": True,
            "feature_count": len(fc.get("features", [])),
            "error": None,
        }
    except Exception as e:
        return {
            "path_configured": ANOMALIES_PATH,
            "path_resolved": resolved_path,
            "loaded": False,
            "feature_count": None,
            "error": str(e),
        }


def filter_features(
    feature_collection: dict,
    tier: Optional[str] = None,
    site_id: Optional[str] = None,
    include_low: bool = False,
) -> list:
    """Pure filter over the feature list. Never mutates or reshapes a feature."""
    features = feature_collection.get("features", [])
    result = []
    for feature in features:
        props = feature.get("properties", {})
        confidence_tier = props.get("confidence_tier")

        if not include_low and confidence_tier == "low":
            continue
        if tier is not None and confidence_tier != tier:
            continue
        if site_id is not None and props.get("site_id") != site_id:
            continue

        result.append(feature)
    return result


def get_feature_by_id(feature_collection: dict, anomaly_id: str) -> Optional[dict]:
    for feature in feature_collection.get("features", []):
        if feature.get("properties", {}).get("anomaly_id") == anomaly_id:
            return feature
    return None


def compute_stats(feature_collection: dict) -> dict:
    """Aggregates dashboard stats from the live feature list.

    Null-handling rules (deliberate, not an oversight):
    - confidence_tier / site_id missing -> counted under an explicit
      "unknown" bucket, never merged into a real category and never dropped.
    - area_ha null -> excluded from the hectare sum (not coerced to 0, since
      0 ha is a meaningful value); the exclusion count is reported alongside
      so it's visible rather than silently under-reporting.
    - first_detection_date null -> excluded from the min/max window; if every
      feature lacks a date, the window is null, not an error.
    """
    from datetime import datetime, timezone

    features = feature_collection.get("features", [])

    tier_counts: dict = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
    site_breakdown: dict = {}
    total_area_ha = 0.0
    area_unknown_count = 0
    dates = []
    date_unknown_count = 0

    for feature in features:
        props = feature.get("properties", {})

        tier = props.get("confidence_tier") or "unknown"
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

        site_id = props.get("site_id") or "unknown"
        site_entry = site_breakdown.setdefault(site_id, {"count": 0, "total_area_ha": 0.0})
        site_entry["count"] += 1

        area_ha = props.get("area_ha")
        if area_ha is None:
            area_unknown_count += 1
        else:
            total_area_ha += area_ha
            site_entry["total_area_ha"] += area_ha

        date_str = props.get("first_detection_date")
        if date_str:
            dates.append(date_str)
        else:
            date_unknown_count += 1

    return {
        "total_anomalies": len(features),
        "tier_counts": tier_counts,
        "total_area_ha": round(total_area_ha, 4),
        "area_ha_unknown_count": area_unknown_count,
        "site_breakdown": site_breakdown,
        "first_detection_date_min": min(dates) if dates else None,
        "first_detection_date_max": max(dates) if dates else None,
        "date_unknown_count": date_unknown_count,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
