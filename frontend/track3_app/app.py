"""Project Spoonbill, Track 3: Streamlit dashboard.

Reads only local files (anomalies GeoJSON, chips, brief JSON). Never calls Earth Engine or an LLM.

Run:  streamlit run app.py                     (data folder auto-resolved, see core/config.py)
      streamlit run app.py -- --data-dir PATH  (explicit data folder)
      streamlit run app.py -- --demo           (demo mode: scripted click path)
"""

from __future__ import annotations

import sys

import streamlit as st

from core import config, loader
from core.filters import filter_anomalies
from core.i18n import t
from core.loader import ContractError
from ui import data, demo, detail, export_buttons, footer, header, map_view, overview, sidebar, state, styles

st.set_page_config(page_title="Project Spoonbill", page_icon="🛰️", layout="wide")


def _select_options(filtered, lang: str) -> None:
    ids = [a.id for a in filtered]
    by_id = {a.id: a for a in filtered}
    current = st.session_state.get(state.SELECTED)
    if current not in by_id:
        if current is not None:
            st.caption(t("selection_hidden", lang))
        current = ids[0]           # default to the strongest visible detection
        state.select_anomaly(current)

    def label(aid: str) -> str:
        p = by_id[aid].properties
        return f"{config.TIER_STYLE[p.confidence_tier]['glyph']} {aid} · {t(p.site_id, lang)} · {p.area_ha:.2f} {t('ha', lang)}"

    st.selectbox(t("select_anomaly", lang), options=ids, format_func=label,
                 key=state.prime_widget(state.SELECTED, lang), on_change=state.sync_from_widget,
                 args=(state.SELECTED, lang), help=t("map_hint", lang))


def _main_view(collection, filtered, briefs, source, lang: str) -> None:
    geoms = data.simplified_features(str(source.path), fingerprint)
    left, right = st.columns([55, 45], gap="large")
    with left, st.container(key="map_col"):   # sticky via CSS in ui/styles.py
        map_view.render(filtered, geoms, st.session_state.get(state.SELECTED), lang)
    with right:
        if not filtered:
            st.info(t("no_matches", lang))
            return
        _select_options(filtered, lang)
        anomaly = collection.by_id(st.session_state[state.SELECTED])
        brief_load = briefs[anomaly.id]
        detail.render(anomaly, brief_load, source, collection.metadata, lang,
                      export_slot=lambda: export_buttons.render(anomaly, brief_load, source, lang))


source = config.resolve_data_dir(sys.argv[1:])
state.init_defaults()
styles.inject()
lang = sidebar.language_selector()

if source.is_fixture:
    header.fixture_banner(lang)
header.title(lang)

try:
    fingerprint = loader.data_fingerprint(source.path)
    collection = data.anomalies(str(source.path), fingerprint)
except ContractError as exc:
    st.error(t("contract_error", lang))
    st.code(str(exc), language="text")
    data.report_issue(str(exc).splitlines()[0] + " " + "; ".join(exc.problems[:5]), source.is_fixture)
    footer.render(None, lang)
    st.stop()

if collection.warnings:
    with st.expander(f"⚠ {t('consistency_warning', lang)} ({len(collection.warnings)})"):
        st.markdown("\n".join(f"- {w}" for w in collection.warnings))
    for w in collection.warnings:
        data.report_issue(f"anomalies_v1.geojson consistency: {w}", source.is_fixture)

briefs = data.all_briefs(str(source.path), [a.id for a in collection.anomalies], fingerprint)
filter_state = sidebar.filters(collection, lang)
filtered = filter_anomalies(collection.anomalies, filter_state)
sidebar.provenance(collection, source, lang)
demo_on = st.sidebar.toggle(t("demo_mode", lang), value=config.demo_mode_requested(sys.argv[1:]), key="demo_on")

if demo_on:
    demo.render(collection, briefs, lang)

header.metrics(filtered, briefs, collection.metadata, lang)

overview_doc = None
try:
    overview_doc = data.overview(str(source.path), fingerprint)
except ContractError as exc:
    data.report_issue(str(exc), source.is_fixture)

evidence_doc = None
try:
    evidence_doc = data.evidence_gallery(str(source.path), fingerprint)
except ContractError as exc:
    data.report_issue(str(exc), source.is_fixture)

if overview_doc or evidence_doc:
    tab_map, tab_overview = st.tabs([t("tab_map", lang), t("tab_overview", lang)])
    with tab_map:
        _main_view(collection, filtered, briefs, source, lang)
    with tab_overview:
        if evidence_doc:
            overview.render_evidence(evidence_doc, source.path, lang)
        if overview_doc:
            overview.render(overview_doc, lang)
else:
    _main_view(collection, filtered, briefs, source, lang)

footer.render(collection.metadata, lang)
