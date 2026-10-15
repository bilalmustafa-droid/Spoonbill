"""Fixture banner, title and the four headline metrics computed from the filtered set."""

from __future__ import annotations

import streamlit as st

from core.filters import review_count, total_area
from core.formatting import fmt_area, fmt_date
from core.i18n import t
from core.loader import BriefLoad
from core.models import Anomaly, Metadata

from .styles import esc


def fixture_banner(lang: str) -> None:
    text = esc(t("fixture_banner", lang))
    st.markdown(f'<div class="sb-banner" role="alert">⚠ {text}</div>', unsafe_allow_html=True)
    st.sidebar.markdown(f'<div class="sb-banner" role="alert" style="font-size:.85rem">⚠ {text}</div>',
                        unsafe_allow_html=True)


def title(lang: str) -> None:
    st.title(t("app_title", lang))
    st.caption(t("app_subtitle", lang))


def metrics(filtered: list[Anomaly], briefs: dict[str, BriefLoad], metadata: Metadata, lang: str) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("m_count", lang), len(filtered))
    c2.metric(t("m_area", lang), fmt_area(total_area(filtered), lang))
    c3.metric(t("m_review", lang), review_count(filtered, briefs), help=t("m_review_help", lang))
    c4.metric(t("m_latest", lang), fmt_date(metadata.current_window[1], lang), help=t("m_latest_help", lang))
