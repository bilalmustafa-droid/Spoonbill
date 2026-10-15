"""Render the brief block for each status: cited, abstained_human_review, error, missing, invalid."""

from __future__ import annotations

import streamlit as st

from core.brief_content import BriefContent, ResolvedClaim, Text, prepare_brief_content
from core.formatting import fmt_timestamp
from core.i18n import t
from core.loader import BriefLoad
from core.models import Citation

from . import data
from .styles import esc


def _txt(value: Text, lang: str) -> str:
    """Display string for a screened text; withheld text becomes an explicit notice."""
    if value.withheld:
        return f"_{t('withheld', lang, reason=t(f'reason_{value.reason}', lang))}_"
    return value.value or ""


def _txt_html(value: Text, lang: str) -> str:
    if value.withheld:
        return f"<i>{esc(t('withheld', lang, reason=t(f'reason_{value.reason}', lang)))}</i>"
    return esc(value.value or "")


def _evidence(content: BriefContent, lang: str) -> None:
    if not content.evidence:
        return
    st.markdown(f"**{t('evidence', lang)}**")
    st.markdown("\n".join(f"- {_txt(e, lang)}" for e in content.evidence))


def _citation_details(c: Citation, lang: str) -> None:
    doc = c.doc + (f" / {c.doc_title_zh}" if lang == "zh_hant" and c.doc_title_zh else "")
    st.markdown(f"**{t('doc', lang)}:** {esc(doc)}  \n"
                f"**{t('page', lang)}:** {c.page} · **{t('section', lang)}:** {esc(c.section or t('na', lang))}")
    st.markdown(f"> {esc(c.quote)}")
    if c.source_url:
        st.markdown(f"[{t('open_source', lang)}]({c.source_url})")
    else:
        st.caption(t("no_source_url", lang))


def _claim(i: int, claim: ResolvedClaim, lang: str) -> None:
    st.markdown(f"{i}. {_txt(claim.claim, lang)}")
    if claim.missing_ids:
        st.markdown(
            f'<span class="sb-missing-cite" title="{esc(t("citation_unavailable_help", lang))}">⚠ '
            f'{esc(t("citation_unavailable", lang, ids=", ".join(claim.missing_ids)))}</span>',
            unsafe_allow_html=True,
        )
        st.caption(t("citation_unavailable_help", lang))
    for c in claim.citations:
        with st.expander(f"{c.doc} · {t('page', lang)} {c.page}"):
            _citation_details(c, lang)


def _cited(content: BriefContent, lang: str) -> None:
    st.markdown(f"#### {_txt(content.title, lang)}")
    st.markdown(_txt(content.summary, lang))
    _evidence(content, lang)
    st.markdown(f"**{t('statutory_basis', lang)}**")
    for i, claim in enumerate(content.claims, start=1):
        _claim(i, claim, lang)
    if content.recommended_action.value or content.recommended_action.withheld:
        st.markdown(f"**{t('recommended_action', lang)}**  \n{_txt(content.recommended_action, lang)}")
    if content.limitations.value or content.limitations.withheld:
        st.markdown(f"**{t('limitations', lang)}**  \n{_txt(content.limitations, lang)}")


def _abstained(content: BriefContent, lang: str) -> None:
    reason = _txt_html(content.abstain_reason, lang) if content.abstain_reason else esc(t("na", lang))
    st.markdown(
        f'<div class="sb-panel-amber" role="status"><h4>⚑ {esc(t("review_heading", lang))}</h4>'
        f'<div>{esc(t("review_body", lang))}</div>'
        f'<div style="margin-top:.5rem"><b>{esc(t("review_reason", lang))}:</b> {reason}</div></div>',
        unsafe_allow_html=True,
    )
    if content.title.value:
        st.markdown(f"#### {_txt(content.title, lang)}")
    if content.summary.value or content.summary.withheld:
        st.markdown(_txt(content.summary, lang))
    _evidence(content, lang)
    if content.recommended_action.value or content.recommended_action.withheld:
        st.markdown(f"**{t('recommended_action', lang)}**  \n{_txt(content.recommended_action, lang)}")
    if content.limitations.value or content.limitations.withheld:
        st.markdown(f"**{t('limitations', lang)}**  \n{_txt(content.limitations, lang)}")


def _grey(message: str) -> None:
    st.markdown(f'<div class="sb-panel-grey" role="status">{esc(message)}</div>', unsafe_allow_html=True)


def render(load: BriefLoad, lang: str, is_fixture: bool) -> None:
    st.markdown(f"### {t('brief_heading', lang)}")
    if load.state == "missing":
        _grey(t("pending_notice", lang))
        return
    if load.state == "invalid":
        _grey(t("invalid_notice", lang))
        data.report_issue(load.error or "invalid brief file", is_fixture)
        return

    brief = load.brief
    if brief.status == "error":
        _grey(t("error_notice", lang))   # never show upstream error text or stack traces
        return

    content = prepare_brief_content(brief, lang)
    for issue in content.issues:
        data.report_issue(issue, is_fixture)
    if brief.status == "cited":
        _cited(content, lang)
    else:
        _abstained(content, lang)
    st.caption(t("brief_meta", lang, when=fmt_timestamp(brief.generated_at, lang), model=brief.model))
