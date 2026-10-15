"""PDF and DOCX download buttons. Files are generated in memory, only when the button is clicked."""

from __future__ import annotations

import streamlit as st

from core.config import CJK_FONT_PATH, DataSource
from core.i18n import t
from core.loader import BriefLoad
from core.models import Anomaly
from export import build_report_model, export_filename, render_docx, render_pdf


def make_exporters(anomaly: Anomaly, brief_load: BriefLoad, source: DataSource, lang: str):
    """Return zero-argument callables producing PDF and DOCX bytes (st.download_button runs them lazily)."""
    def model() -> dict:
        return build_report_model(anomaly, brief_load.brief, lang, data_dir=source.path,
                                  is_fixture=source.is_fixture, brief_state=brief_load.state)
    return (lambda: render_pdf(model())), (lambda: render_docx(model()))


def render(anomaly: Anomaly, brief_load: BriefLoad, source: DataSource, lang: str) -> None:
    st.markdown(f"**{t('export_heading', lang)}**")
    pdf_bytes, docx_bytes = make_exporters(anomaly, brief_load, source, lang)
    font_ok = CJK_FONT_PATH.is_file()
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            t("export_pdf", lang), data=pdf_bytes, file_name=export_filename(anomaly.id, lang, "pdf"),
            mime="application/pdf", key=f"dl_pdf_{anomaly.id}_{lang}", disabled=not font_ok,
            on_click="ignore", width="stretch", icon=":material/picture_as_pdf:",
        )
    with c2:
        st.download_button(
            t("export_docx", lang), data=docx_bytes, file_name=export_filename(anomaly.id, lang, "docx"),
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key=f"dl_docx_{anomaly.id}_{lang}", on_click="ignore", width="stretch",
            icon=":material/description:",
        )
    if not font_ok:
        st.warning(t("export_font_missing", lang))
