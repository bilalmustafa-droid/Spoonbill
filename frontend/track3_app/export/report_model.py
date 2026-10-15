"""Shared report content for PDF and DOCX, so both formats render identical text.

All free text is already screened by core.brief_content; withheld items are replaced by an explicit
notice. Nothing here is invented: every value comes from the anomaly, the brief or the i18n table.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core import loader
from core.brief_content import BriefContent, Text, prepare_brief_content
from core.formatting import (delta_label, fmt_area, fmt_coords, fmt_date, fmt_db, fmt_ndwi, fmt_timestamp,
                             persistence_label)
from core.i18n import disclaimer, t
from core.models import Anomaly, Brief


def _s(value: Text | None, lang: str) -> str:
    if value is None:
        return ""
    if value.withheld:
        return t("withheld", lang, reason=t(f"reason_{value.reason}", lang))
    return value.value or ""


def _brief_section(content: BriefContent | None, status_key: str, lang: str) -> dict:
    section = {"title": "", "summary": "", "evidence": [], "claims": [], "recommended_action": "",
               "limitations": "", "review": None, "notice": None, "meta": ""}
    if status_key == "missing":
        section["notice"] = t("pending_notice", lang)
        return section
    if status_key == "invalid":
        section["notice"] = t("invalid_notice", lang)
        return section
    if status_key == "error":
        section["notice"] = t("error_notice", lang)
        return section

    number_of = {c.id: i for i, c in enumerate(content.citations, start=1)}
    section.update(
        title=_s(content.title, lang),
        summary=_s(content.summary, lang),
        evidence=[_s(e, lang) for e in content.evidence],
        recommended_action=_s(content.recommended_action, lang),
        limitations=_s(content.limitations, lang),
        meta=t("brief_meta", lang, when=fmt_timestamp(content.generated_at, lang), model=content.model),
    )
    for claim in content.claims:
        section["claims"].append({
            "text": _s(claim.claim, lang),
            "refs": [f"[{number_of[c.id]}]" for c in claim.citations if c.id in number_of],
            "missing": t("citation_unavailable", lang, ids=", ".join(claim.missing_ids)) if claim.missing_ids else None,
        })
    if status_key == "abstained_human_review":
        section["review"] = {
            "heading": t("review_heading", lang),
            "body": t("review_body", lang),
            "reason_label": t("review_reason", lang),
            "reason": _s(content.abstain_reason, lang) or t("na", lang),
        }
    return section


def _citations(content: BriefContent | None, lang: str) -> list[dict]:
    if content is None:
        return []
    out = []
    for i, c in enumerate(content.citations, start=1):
        doc = c.doc + (f" / {c.doc_title_zh}" if lang == "zh_hant" and c.doc_title_zh else "")
        out.append({"number": i, "id": c.id, "doc": doc, "page": c.page, "section": c.section or t("na", lang),
                    "quote": c.quote, "source_url": c.source_url or t("no_source_url", lang)})
    return out


def build_report_model(anomaly: Anomaly, brief: Brief | None, lang: str, *, data_dir: Path,
                       is_fixture: bool, brief_state: str | None = None,
                       now: datetime | None = None) -> dict:
    """brief_state: "ok" | "missing" | "invalid" (defaults from whether brief is None)."""
    now = now or datetime.now(timezone.utc)
    p = anomaly.properties
    state = brief_state or ("missing" if brief is None else "ok")
    status_key = brief.status if (state == "ok" and brief is not None) else state
    content = prepare_brief_content(brief, lang) if status_key in ("cited", "abstained_human_review") else None

    location = [
        (t("site", lang), t(p.site_id, lang)),
        (t("coordinates", lang), fmt_coords(p.centroid_lon, p.centroid_lat, lang)),
        (t("zoning_label", lang), f"{t(f'zone_{p.zone_hint}', lang)} ({t('zone_note', lang)})"),
        (t("area", lang), fmt_area(p.area_ha, lang)),
        (t("first_detected", lang), fmt_date(p.first_detection_date, lang)),
        (t("persistence", lang), persistence_label(p.persistence_count, p.persistence_total, lang)),
        (t("tt_tier", lang), t(f"tier_{p.confidence_tier}", lang)),
    ]
    if not p.optical_available:
        location.append((t("radar_only", lang), t("radar_only_help", lang)))

    metrics = {
        "header": [t("metric", lang), t("baseline", lang), t("current", lang), t("delta", lang)],
        "rows": [
            [t("vv_row", lang), fmt_db(p.baseline_vv_db, lang), fmt_db(p.current_vv_db, lang),
             delta_label(p.delta_vv_db, "db", lang)],
            [t("ndwi_row", lang), fmt_ndwi(p.baseline_ndwi, lang), fmt_ndwi(p.current_ndwi, lang),
             delta_label(p.delta_ndwi, "ndwi", lang)],
        ],
    }

    synthetic = f" ({t('chip_synthetic', lang)})" if is_fixture else ""
    images = [
        {"caption": t("chip_before", lang) + synthetic, "path": loader.chip_path(data_dir, p.chip_before_png)},
        {"caption": t("chip_after", lang) + synthetic, "path": loader.chip_path(data_dir, p.chip_after_png)},
    ]

    return {
        "lang": lang,
        "title": t("report_title", lang),
        "anomaly_id": anomaly.id,
        "generated_label": t("report_generated", lang),
        "generated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
        "fixture_label": t("report_fixture", lang) if is_fixture else None,
        "status_label": t(f"status_{status_key}", lang),
        "status_key": status_key,
        "location": location,
        "metrics": metrics,
        "images": images,
        "image_missing_text": t("chip_missing", lang),
        "brief": _brief_section(content, status_key, lang),
        "citations": _citations(content, lang),
        "labels": {k: t(k, lang) for k in (
            "location_heading", "metrics_heading", "images_heading", "brief_heading", "summary", "evidence",
            "statutory_basis", "recommended_action", "limitations", "citations", "doc", "page", "section",
            "quote", "sources", "report_status", "disclaimer_label")},
        "disclaimer": disclaimer(lang),
    }


def export_filename(anomaly_id: str, lang: str, ext: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"Spoonbill_{anomaly_id}_{lang}_{now:%Y%m%d}.{ext}"
