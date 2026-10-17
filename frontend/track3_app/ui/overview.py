"""The "Method and evidence" tab. Two independent sections, either of which
may be absent:

- render_evidence(): data/evidence_chips/manifest.json, real before/after
  crops from the live optical detector (spatial/ruhan code.py via
  build_demo_chips.py). Never tied to a specific anomaly_id -- see
  build_demo_chips.py for why pairing real imagery with a synthetic
  anomaly's numbers was ruled out. This is the primary content of the tab.
- render(): the optional data/briefs/_overview.json dashboard summary
  (Phase 2, no JSON Schema in contract v1.0), kept as a secondary section
  since it mostly restates numbers already on the header.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from core import loader
from core.content_guard import screen
from core.i18n import t


def _safe(value) -> str | None:
    return screen(value).text if isinstance(value, str) else None


def render_evidence(doc: dict, data_dir: Path, lang: str) -> None:
    st.markdown(f"### {t('evidence_heading', lang)}")
    st.markdown(t("evidence_intro", lang))
    for sample in doc.get("samples", []):
        before = loader.evidence_chip_path(data_dir, sample.get("before_file"))
        after = loader.evidence_chip_path(data_dir, sample.get("after_file"))
        if before is None or after is None:
            continue
        area = sample.get("approx_area_ha")
        caption = t(
            "evidence_caption", lang,
            area=f"{area:.2f}" if isinstance(area, (int, float)) else "?",
            site=sample.get("site_label", sample.get("site", "")),
            incident=sample.get("incident", ""),
        )
        left, right = st.columns(2)
        left.image(str(before), caption=f"{t('chip_before', lang)} · {caption}", width="stretch")
        right.image(str(after), caption=f"{t('chip_after', lang)} · {caption}", width="stretch")
    st.divider()


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
