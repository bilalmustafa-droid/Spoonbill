"""Detail panel for the selected anomaly: identity, confidence, metrics, chips, timeseries, brief, export."""

from __future__ import annotations

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from core import loader
from core.config import DataSource
from core.formatting import (delta_label, fmt_area, fmt_coords, fmt_date, fmt_db, fmt_ndwi,
                             persistence_label)
from core.i18n import t
from core.loader import BriefLoad
from core.models import Anomaly, Metadata

from . import brief_view
from .styles import esc, persistence_meter_html, tier_badge_html


def _identity(a: Anomaly, lang: str) -> None:
    p = a.properties
    st.markdown(f"## {a.id}")
    st.caption(f"{t(p.site_id, lang)} · {t('coordinates', lang)}: "
               f"{fmt_coords(p.centroid_lon, p.centroid_lat, lang)}")
    chips = tier_badge_html(p.confidence_tier, lang)
    if not p.optical_available:
        chips += f'<span class="sb-chip" title="{esc(t("radar_only_help", lang))}">📡 {esc(t("radar_only", lang))}</span>'
    if p.optical_brightness_flag:
        chips += f'<span class="sb-chip">{esc(t("brightness_flag", lang))}</span>'
    st.markdown(chips, unsafe_allow_html=True)
    if not p.optical_available:
        st.caption(t("radar_only_help", lang))
    st.markdown(
        f"**{t('persistence', lang)}:** {persistence_meter_html(p.persistence_count, p.persistence_total)} "
        f"{esc(persistence_label(p.persistence_count, p.persistence_total, lang))}",
        unsafe_allow_html=True,
    )
    st.markdown(f"**{t('zoning_label', lang)}:** {t(f'zone_{p.zone_hint}', lang)}  \n"
                f"<small>{esc(t('zone_note', lang))}</small>", unsafe_allow_html=True)


def metrics_rows(a: Anomaly, lang: str) -> list[dict]:
    """Rows shared by the screen table (and mirrored in exports)."""
    p = a.properties
    return [
        {t("metric", lang): t("vv_row", lang), t("baseline", lang): fmt_db(p.baseline_vv_db, lang),
         t("current", lang): fmt_db(p.current_vv_db, lang), t("delta", lang): delta_label(p.delta_vv_db, "db", lang)},
        {t("metric", lang): t("ndwi_row", lang), t("baseline", lang): fmt_ndwi(p.baseline_ndwi, lang),
         t("current", lang): fmt_ndwi(p.current_ndwi, lang),
         t("delta", lang): delta_label(p.delta_ndwi, "ndwi", lang)},
    ]


def _metrics(a: Anomaly, lang: str) -> None:
    p = a.properties
    st.table(pd.DataFrame(metrics_rows(a, lang)).set_index(t("metric", lang)))
    c1, c2 = st.columns(2)
    c1.metric(t("area", lang), fmt_area(p.area_ha, lang))
    c2.metric(t("first_detected", lang), fmt_date(p.first_detection_date, lang))


def _chip(col, path: Path | None, caption: str, is_fixture: bool, lang: str) -> None:
    with col:
        if path is None:
            st.markdown(f'<div class="sb-chip-placeholder" role="img" aria-label="{esc(t("chip_missing", lang))}">'
                        f'{esc(t("chip_missing", lang))}</div>', unsafe_allow_html=True)
            st.caption(caption)
            return
        label = f"{caption} · {t('chip_synthetic', lang)}" if is_fixture else caption
        st.image(str(path), caption=label, width="stretch")


def _chips(a: Anomaly, source: DataSource, lang: str) -> None:
    p = a.properties
    left, right = st.columns(2)
    _chip(left, loader.chip_path(source.path, p.chip_before_png), t("chip_before", lang), source.is_fixture, lang)
    _chip(right, loader.chip_path(source.path, p.chip_after_png), t("chip_after", lang), source.is_fixture, lang)


def _timeseries(a: Anomaly, metadata: Metadata, lang: str) -> None:
    ts = a.properties.timeseries
    if ts is None or not ts.months:
        return
    st.markdown(f"**{t('timeseries', lang)}**")
    df = pd.DataFrame({"month": pd.to_datetime(ts.months, format="%Y-%m"), "vv": ts.vv_db, "ndwi": ts.ndwi})
    base = pd.DataFrame({"start": [pd.Timestamp(metadata.baseline_window[0])],
                         "end": [pd.Timestamp(metadata.baseline_window[1])],
                         "label": [t("baseline_period", lang)]})
    band = alt.Chart(base).mark_rect(opacity=0.12, color="#1F6F8B").encode(x="start:T", x2="end:T")
    panels = []
    for field, title, color in (("vv", t("vv_row", lang), "#1F6F8B"), ("ndwi", t("ndwi_row", lang), "#2B8A3E")):
        line = alt.Chart(df).mark_line(point=True, color=color).encode(
            x=alt.X("month:T", title=t("month", lang)),
            y=alt.Y(f"{field}:Q", title=title, scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("month:T", format="%Y-%m"), alt.Tooltip(f"{field}:Q", format=".2f")],
        )
        panels.append((band + line).properties(height=130, width="container"))
    # One chart object (two stacked panels) keeps it to a single Vega render in the browser.
    st.altair_chart(alt.vconcat(*panels), width="stretch")
    st.caption(t("baseline_period", lang) + ": " + f"{metadata.baseline_window[0]} → {metadata.baseline_window[1]}")


def render(a: Anomaly, brief_load: BriefLoad, source: DataSource, metadata: Metadata, lang: str,
           export_slot=None) -> None:
    _identity(a, lang)
    _metrics(a, lang)
    _chips(a, source, lang)
    _timeseries(a, metadata, lang)
    st.divider()
    brief_view.render(brief_load, lang, source.is_fixture)
    if export_slot is not None:
        st.divider()
        export_slot()
