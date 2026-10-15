"""Footer: methodology summary pulled from metadata.thresholds, and the disclaimer in the current language."""

from __future__ import annotations

import streamlit as st

from core.formatting import fmt_date
from core.i18n import disclaimer, t
from core.models import Metadata

from .styles import esc


def methodology_text(metadata: Metadata | None, lang: str) -> str | None:
    if metadata is None:
        return None
    th = metadata.thresholds
    return t(
        "methodology_text", lang,
        sensors=", ".join(metadata.sensors),
        b0=fmt_date(metadata.baseline_window[0]), b1=fmt_date(metadata.baseline_window[1]),
        c0=fmt_date(metadata.current_window[0]), c1=fmt_date(metadata.current_window[1]),
        dvv=f"{th.delta_vv_db:+.1f}", dndwi=f"{th.delta_ndwi:+.2f}",
        despeckle=th.despeckle, persistence=th.persistence_rule, min_area=f"{th.min_area_ha:g}",
    )


def render(metadata: Metadata | None, lang: str) -> None:
    method = methodology_text(metadata, lang)
    method_html = (f"<div><b>{esc(t('methodology', lang))}.</b> {esc(method)}</div>" if method else "")
    st.markdown(
        f'<div class="sb-footer">{method_html}'
        f'<div class="sb-disclaimer" role="note"><b>{esc(t("disclaimer_label", lang))}:</b> '
        f'{esc(disclaimer(lang))}</div></div>',
        unsafe_allow_html=True,
    )
