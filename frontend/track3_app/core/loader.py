"""Read and validate contract files. Fails loudly on contract violations; never coerces bad data.

No Streamlit imports here; the UI wraps these functions with st.cache_data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator
from pydantic import ValidationError
from shapely.geometry import shape

from . import config
from .models import AnomalyCollection, Brief

# Rounding tolerance for "delta = current - baseline" when each value is published already rounded.
_DELTA_TOL_DB = 0.15
_DELTA_TOL_NDWI = 0.015


class ContractError(Exception):
    """A data file violates contract v1.0. The message is human-readable and safe to show in the UI."""

    def __init__(self, source: str, problems: list[str]):
        self.source = source
        self.problems = problems
        shown = "\n".join(f"  - {p}" for p in problems[:15])
        more = f"\n  ... and {len(problems) - 15} more" if len(problems) > 15 else ""
        super().__init__(f"{source} does not match contract v1.0:\n{shown}{more}")


# --------------------------------------------------------------------------- helpers

def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-standard JSON constant {name} (NaN/Infinity are not allowed by the contract)")


def read_json_strict(path: Path) -> Any:
    """UTF-8 JSON read that rejects NaN and Infinity."""
    label = path.name
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f, parse_constant=_reject_constant)
    except UnicodeDecodeError as exc:
        raise ContractError(label, [f"file is not valid UTF-8 ({exc.reason})"]) from exc
    except json.JSONDecodeError as exc:
        raise ContractError(label, [f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"]) from exc
    except ValueError as exc:
        raise ContractError(label, [str(exc)]) from exc


@lru_cache(maxsize=4)
def _validator(schema_path: Path) -> Draft202012Validator:
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _schema_problems(doc: Any, schema_path: Path) -> list[str]:
    errors = sorted(_validator(schema_path).iter_errors(doc), key=lambda e: list(e.absolute_path))
    problems = []
    for err in errors:
        where = "/".join(str(p) for p in err.absolute_path) or "(root)"
        problems.append(f"{where}: {err.message}")
    return problems


def _pydantic_problems(exc: ValidationError) -> list[str]:
    return [f"{'/'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]


def _geometry_problems(feature: dict, index: int) -> list[str]:
    problems = []
    geom = feature["geometry"]
    polygons = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    for poly in polygons:
        for ring in poly:
            if ring[0] != ring[-1]:
                problems.append(f"features/{index}/geometry: ring is not closed (first != last coordinate)")
    if not problems:
        shp = shape(geom)
        if not shp.is_valid:
            problems.append(f"features/{index}/geometry: invalid polygon geometry")
    return problems


def _consistency_warnings(collection: AnomalyCollection) -> list[str]:
    warnings = []
    for a in collection.anomalies:
        p = a.properties
        if abs((p.current_vv_db - p.baseline_vv_db) - p.delta_vv_db) > _DELTA_TOL_DB:
            warnings.append(f"{p.anomaly_id}: delta_vv_db {p.delta_vv_db} != current - baseline "
                            f"({p.current_vv_db} - {p.baseline_vv_db})")
        if abs((p.current_ndwi - p.baseline_ndwi) - p.delta_ndwi) > _DELTA_TOL_NDWI:
            warnings.append(f"{p.anomaly_id}: delta_ndwi {p.delta_ndwi} != current - baseline "
                            f"({p.current_ndwi} - {p.baseline_ndwi})")
        if p.persistence_count > p.persistence_total:
            warnings.append(f"{p.anomaly_id}: persistence_count {p.persistence_count} > "
                            f"persistence_total {p.persistence_total}")
    if collection.metadata.anomaly_count != len(collection.anomalies):
        warnings.append(f"metadata.anomaly_count is {collection.metadata.anomaly_count} but the file "
                        f"contains {len(collection.anomalies)} features")
    return warnings


# --------------------------------------------------------------------------- public API

def load_anomalies(data_dir: Path) -> AnomalyCollection:
    """Read data_dir/anomalies_v1.geojson, validate against the JSON Schema, parse into models."""
    path = Path(data_dir) / config.ANOMALIES_FILENAME
    label = config.ANOMALIES_FILENAME
    if not path.is_file():
        raise ContractError(label, [f"file not found: {path}"])
    doc = read_json_strict(path)

    problems = _schema_problems(doc, config.ANOMALY_SCHEMA_PATH)
    if problems:
        raise ContractError(label, problems)

    for i, feature in enumerate(doc["features"]):
        problems.extend(_geometry_problems(feature, i))
    ids = [f["properties"]["anomaly_id"] for f in doc["features"]]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        problems.append(f"duplicate anomaly_id values: {', '.join(duplicates)}")
    if problems:
        raise ContractError(label, problems)

    try:
        collection = AnomalyCollection(
            metadata=doc["metadata"],
            anomalies=[{"geometry": f["geometry"], "properties": f["properties"]} for f in doc["features"]],
        )
    except ValidationError as exc:
        raise ContractError(label, _pydantic_problems(exc)) from exc

    warnings = _consistency_warnings(collection)
    return collection.model_copy(update={"warnings": warnings}) if warnings else collection


def load_brief(data_dir: Path, anomaly_id: str) -> Brief | None:
    """Return the brief for anomaly_id, or None when the file does not exist (analysis pending)."""
    path = Path(data_dir) / config.BRIEFS_DIRNAME / f"{anomaly_id}.json"
    if not path.is_file():
        return None
    label = f"{config.BRIEFS_DIRNAME}/{path.name}"
    doc = read_json_strict(path)
    problems = _schema_problems(doc, config.BRIEF_SCHEMA_PATH)
    if problems:
        raise ContractError(label, problems)
    if doc["anomaly_id"] != anomaly_id:
        raise ContractError(label, [f"anomaly_id inside the file is {doc['anomaly_id']!r}, expected {anomaly_id!r}"])
    try:
        return Brief.model_validate(doc)
    except ValidationError as exc:
        raise ContractError(label, _pydantic_problems(exc)) from exc


BriefState = Literal["ok", "missing", "invalid"]


@dataclass(frozen=True)
class BriefLoad:
    """Outcome of loading one brief, so the UI can render every case without try/except."""
    state: BriefState
    brief: Brief | None = None
    error: str | None = None


def load_brief_safe(data_dir: Path, anomaly_id: str) -> BriefLoad:
    try:
        brief = load_brief(data_dir, anomaly_id)
    except ContractError as exc:
        return BriefLoad(state="invalid", error=str(exc))
    return BriefLoad(state="missing") if brief is None else BriefLoad(state="ok", brief=brief)


def load_overview(data_dir: Path) -> dict | None:
    """Optional data/briefs/_overview.json (Phase 2). None when absent; ContractError if not a JSON object."""
    path = Path(data_dir) / config.BRIEFS_DIRNAME / config.OVERVIEW_FILENAME
    if not path.is_file():
        return None
    doc = read_json_strict(path)
    if not isinstance(doc, dict):
        raise ContractError(f"{config.BRIEFS_DIRNAME}/{config.OVERVIEW_FILENAME}", ["top level must be a JSON object"])
    return doc


def chip_path(data_dir: Path, relative: str | None) -> Path | None:
    """Resolve a chip path relative to data_dir. None when the field is null, the file is missing,
    or the path would escape data_dir."""
    if not relative:
        return None
    base = Path(data_dir).resolve()
    candidate = (base / Path(*relative.split("/"))).resolve()
    if not candidate.is_relative_to(base) or not candidate.is_file():
        return None
    return candidate


def data_fingerprint(data_dir: Path) -> str:
    """Cheap cache key that changes when any data file changes (mtime + size of every file)."""
    base = Path(data_dir)
    parts = []
    for p in sorted(base.rglob("*.json")) + sorted(base.glob("*.geojson")):
        stat = p.stat()
        parts.append(f"{p.relative_to(base)}:{stat.st_mtime_ns}:{stat.st_size}")
    return "|".join(parts)
