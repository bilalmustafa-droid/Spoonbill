"""Demo mode for the live pitch: preloads the three strongest anomalies and a scripted click path.

Steps are derived from the data (never hardcoded IDs), so the same script works on fixtures and on
real data. Enable with `streamlit run app.py -- --demo`, SPOONBILL_DEMO=1, or the sidebar toggle.
"""

from __future__ import annotations

import streamlit as st

from core.filters import strongest
from core.i18n import t
from core.loader import BriefLoad
from core.models import AnomalyCollection

from . import state

PRELOADED = "demo_preloaded"


def build_steps(collection: AnomalyCollection, briefs: dict[str, BriefLoad]) -> list[dict]:
    top = strongest(collection.anomalies, 3)
    steps = [{"anomaly": a.id, "lang": "en", "note": ("demo_note_strongest", {"rank": i})}
             for i, a in enumerate(top, start=1)]
    if top:
        steps.append({"anomaly": top[0].id, "lang": "zh_hant", "note": ("demo_note_language", {})})
    abstained = [a for a in strongest(collection.anomalies, len(collection.anomalies))
                 if (b := briefs.get(a.id)) and b.state == "ok" and b.brief.status == "abstained_human_review"]
    if abstained:
        steps.append({"anomaly": abstained[0].id, "lang": None, "note": ("demo_note_review", {})})
    if top:
        steps.append({"anomaly": top[0].id, "lang": None, "note": ("demo_note_export", {})})
    return steps


def _make_visible(collection: AnomalyCollection, anomaly_id: str) -> None:
    """Widen filters just enough that the demo anomaly is shown on the map."""
    p = collection.by_id(anomaly_id).properties
    sites = st.session_state.get(state.SITES)
    if sites is not None and p.site_id not in sites:
        st.session_state[state.SITES] = list(sites) + [p.site_id]
    if p.confidence_tier == "low":
        st.session_state[state.SHOW_LOW] = True
    tiers = st.session_state.get(state.TIERS, [])
    if p.confidence_tier not in tiers:
        st.session_state[state.TIERS] = list(tiers) + [p.confidence_tier]
    dates = st.session_state.get(state.DATES)
    if dates and len(dates) == 2:
        from datetime import date
        d = date.fromisoformat(p.first_detection_date)
        st.session_state[state.DATES] = (min(dates[0], d), max(dates[1], d))


def apply_step(collection: AnomalyCollection, steps: list[dict], index: int) -> None:
    index = max(0, min(index, len(steps) - 1))
    step = steps[index]
    st.session_state[state.DEMO_STEP] = index
    _make_visible(collection, step["anomaly"])
    state.select_anomaly(step["anomaly"])
    if step["lang"]:
        st.session_state[state.LANG] = step["lang"]


def render(collection: AnomalyCollection, briefs: dict[str, BriefLoad], lang: str) -> None:
    steps = build_steps(collection, briefs)
    if not steps:
        return
    if not st.session_state.get(PRELOADED):
        st.session_state[PRELOADED] = True
        apply_step(collection, steps, 0)
        st.rerun()

    index = min(st.session_state.get(state.DEMO_STEP, 0), len(steps) - 1)
    step = steps[index]
    key, kwargs = step["note"]
    with st.container(border=True):
        st.markdown(f"**🎬 {t('demo_heading', lang)}** · {t('demo_step', lang, n=index + 1, total=len(steps))}")
        st.markdown(t(key, lang, **kwargs) + f"  \n`{step['anomaly']}`")
        c1, c2, c3 = st.columns([1, 1, 3])
        c1.button(t("demo_prev", lang), on_click=apply_step, args=(collection, steps, index - 1),
                  disabled=index == 0, width="stretch", key="demo_prev")
        c2.button(t("demo_next", lang), on_click=apply_step, args=(collection, steps, index + 1),
                  disabled=index == len(steps) - 1, type="primary", width="stretch", key="demo_next")
        top_ids = [s["anomaly"] for s in steps[:3]]
        with c3:
            cols = st.columns(len(top_ids))
            for i, (col, aid) in enumerate(zip(cols, top_ids)):
                col.button(aid, on_click=apply_step, args=(collection, steps, i), width="stretch",
                           key=f"demo_jump_{i}")
