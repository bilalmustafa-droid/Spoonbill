"""st.cache_data wrappers around core.loader. The fingerprint argument invalidates the cache when files change."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
from shapely.geometry import mapping, shape

from core import config, loader
from core.issues import log_issue
from core.models import AnomalyCollection

from . import state


@st.cache_data(show_spinner=False)
def anomalies(data_dir: str, fingerprint: str) -> AnomalyCollection:
    return loader.load_anomalies(Path(data_dir))


@st.cache_data(show_spinner=False)
def brief(data_dir: str, anomaly_id: str, fingerprint: str) -> loader.BriefLoad:
    return loader.load_brief_safe(Path(data_dir), anomaly_id)


def all_briefs(data_dir: str, ids: list[str], fingerprint: str) -> dict[str, loader.BriefLoad]:
    return {aid: brief(data_dir, aid, fingerprint) for aid in ids}


@st.cache_data(show_spinner=False)
def overview(data_dir: str, fingerprint: str) -> dict | None:
    return loader.load_overview(Path(data_dir))


@st.cache_data(show_spinner=False)
def simplified_features(data_dir: str, fingerprint: str) -> dict[str, dict]:
    """anomaly_id -> simplified GeoJSON geometry for map drawing (numbers shown elsewhere are untouched)."""
    collection = anomalies(data_dir, fingerprint)
    out = {}
    for a in collection.anomalies:
        geom = shape(a.geometry).simplify(config.SIMPLIFY_TOLERANCE_DEG, preserve_topology=True)
        out[a.id] = mapping(geom)
    return out


def report_issue(message: str, is_fixture: bool) -> None:
    """Log once per session, and never for fixture data."""
    seen: set = st.session_state.setdefault(state.LOGGED_ISSUES, set())
    if message in seen:
        return
    seen.add(message)
    log_issue(message, enabled=not is_fixture)
