"""Optional overview tab (data/briefs/_overview.json, Phase 2). Shown only when the file exists.

The overview has no JSON Schema in contract v1.0, so only the documented keys are read and every value
passes through the content guard.
"""

from __future__ import annotations

import streamlit as st

from core.content_guard import screen
from core.i18n import t


def _safe(value) -> str | None:
    return screen(value).text if isinstance(value, str) else None


def render(doc: dict, lang: str) -> None:
    block = doc.get(lang) or doc.get("en") or {}
    title = _safe(block.get("title"))
    summary = _safe(block.get("summary"))
    if title:
        st.markdown(f"### {title}")
    if summary:
        st.markdown(summary)
    totals = doc.get("totals")
    if isinstance(totals, dict):
        st.markdown(f"**{t('overview_totals', lang)}**")
        cols = st.columns(3)
        if isinstance(totals.get("anomaly_count"), int):
            cols[0].metric(t("m_count", lang), totals["anomaly_count"])
        if isinstance(totals.get("total_area_ha"), (int, float)):
            cols[1].metric(t("m_area", lang), f"{totals['total_area_ha']:.2f} {t('ha', lang)}")
        if isinstance(totals.get("needing_review"), int):
            cols[2].metric(t("m_review", lang), totals["needing_review"])
        by_site = totals.get("by_site")
        if isinstance(by_site, dict) and by_site:
            st.bar_chart({t(k, lang) if k in ("SITE_A", "SITE_B", "SITE_C") else k: v for k, v in by_site.items()
                          if isinstance(v, (int, float))})
