"""Sidebar: language, filters, reset and data provenance."""

from __future__ import annotations

from datetime import date

import streamlit as st

from core import config
from core.config import DataSource
from core.filters import FilterState, date_bounds
from core.formatting import fmt_date, fmt_timestamp
from core.i18n import t
from core.models import AnomalyCollection

from . import state
from .styles import esc

LANG_LABELS = {"en": "English", "zh_hant": "繁體中文"}


def language_selector() -> str:
    wk = state.prime_widget(state.LANG)
    st.sidebar.radio(
        "Language / 語言", options=list(config.LANGS), key=wk, horizontal=True,
        format_func=LANG_LABELS.get, on_change=state.sync_from_widget, args=(state.LANG,),
    )
    return st.session_state[state.LANG]


def _on_show_low_change() -> None:
    state.sync_from_widget(state.SHOW_LOW)
    tiers = [x for x in st.session_state[state.TIERS] if x != "low"]
    if st.session_state[state.SHOW_LOW]:
        tiers.append("low")
    st.session_state[state.TIERS] = tiers


def _reset(all_sites: list[str], bounds: tuple[date, date] | None) -> None:
    st.session_state[state.SITES] = list(all_sites)
    st.session_state[state.TIERS] = list(state.DEFAULT_TIERS)
    st.session_state[state.SHOW_LOW] = False
    st.session_state[state.DATES] = bounds


def _ensure_filter_defaults(all_sites: list[str], bounds: tuple[date, date] | None) -> None:
    st.session_state.setdefault(state.SITES, list(all_sites))
    st.session_state.setdefault(state.DATES, bounds)
    # Drop stored values that no longer exist in the data (for example after switching data folders).
    st.session_state[state.SITES] = [s for s in st.session_state[state.SITES] if s in all_sites]
    stored = st.session_state[state.DATES]
    if bounds and (not stored or len(stored) != 2 or stored[0] < bounds[0] or stored[1] > bounds[1]):
        st.session_state[state.DATES] = bounds


def filters(collection: AnomalyCollection, lang: str) -> FilterState:
    all_sites = sorted({a.properties.site_id for a in collection.anomalies})
    bounds = date_bounds(collection.anomalies)
    _ensure_filter_defaults(all_sites, bounds)

    sb = st.sidebar
    sb.subheader(t("filters", lang))

    # Translated option labels: one widget per language (see ui/state.py).
    sb.multiselect(t("site_filter", lang), options=all_sites, key=state.prime_widget(state.SITES, lang),
                   format_func=lambda s: t(s, lang), on_change=state.sync_from_widget, args=(state.SITES, lang))

    show_low = st.session_state[state.SHOW_LOW]
    tier_options = ["high", "medium"] + (["low"] if show_low else [])
    st.session_state[state.TIERS] = [x for x in st.session_state[state.TIERS] if x in tier_options]
    sb.multiselect(t("confidence_filter", lang), options=tier_options, key=state.prime_widget(state.TIERS, lang),
                   format_func=lambda x: f"{config.TIER_STYLE[x]['glyph']} {t(f'tier_{x}', lang)}",
                   on_change=state.sync_from_widget, args=(state.TIERS, lang))
    sb.toggle(t("show_low", lang), key=state.prime_widget(state.SHOW_LOW), on_change=_on_show_low_change)

    date_from = date_to = None
    if bounds:
        # value= puts the widget in range mode; the primed session value takes precedence.
        sb.date_input(t("date_filter", lang), value=bounds, min_value=bounds[0], max_value=bounds[1],
                      key=state.prime_widget(state.DATES), on_change=state.sync_from_widget,
                      args=(state.DATES,), format="YYYY-MM-DD")
        picked = st.session_state[state.DATES] or bounds
        # While the user is mid-selection the widget holds a single date; treat it as an open range.
        date_from = picked[0] if len(picked) >= 1 else None
        date_to = picked[1] if len(picked) >= 2 else None

    sb.button(t("reset_filters", lang), on_click=_reset, args=(all_sites, bounds), width="stretch")

    return FilterState(
        sites=tuple(st.session_state[state.SITES]),
        tiers=tuple(st.session_state[state.TIERS]),
        date_from=date_from,
        date_to=date_to,
    )


def provenance(collection: AnomalyCollection, source: DataSource, lang: str) -> None:
    md = collection.metadata
    origin_label = t(f"source_{source.origin}", lang)
    rows = [
        (t("prov_aoi", lang), md.aoi_name),
        (t("prov_generated", lang), fmt_timestamp(md.generated_at, lang)),
        (t("prov_baseline", lang), f"{fmt_date(md.baseline_window[0])} → {fmt_date(md.baseline_window[1])}"),
        (t("prov_current", lang), f"{fmt_date(md.current_window[0])} → {fmt_date(md.current_window[1])}"),
        (t("prov_sensors", lang), ", ".join(md.sensors)),
        (t("prov_source", lang), origin_label),
    ]
    body = "".join(f"<div><b>{esc(k)}:</b> {esc(v)}</div>" for k, v in rows)
    with st.sidebar.container(border=True):
        st.markdown(f"**{t('provenance', lang)}**")
        st.markdown(f'<div style="font-size:.85rem;line-height:1.5">{body}</div>', unsafe_allow_html=True)
