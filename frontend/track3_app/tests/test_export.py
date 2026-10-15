import io
import zipfile
from datetime import datetime, timezone

import pytest

from core import loader
from export import build_report_model, export_filename, render_docx, render_pdf

CASES = {"cited": "DB-0003", "abstained_human_review": "DB-0005", "error": "DB-0007", "missing": "DB-0008"}


def _model(fixture_dir, anomaly_id, lang):
    col = loader.load_anomalies(fixture_dir)
    bl = loader.load_brief_safe(fixture_dir, anomaly_id)
    return build_report_model(col.by_id(anomaly_id), bl.brief, lang, data_dir=fixture_dir, is_fixture=True,
                              brief_state=bl.state)


@pytest.mark.parametrize("lang", ["en", "zh_hant"])
@pytest.mark.parametrize("status", list(CASES))
def test_pdf_and_docx_non_empty(fixture_dir, status, lang):
    model = _model(fixture_dir, CASES[status], lang)
    assert model["status_key"] == status
    pdf = render_pdf(model)
    assert pdf.startswith(b"%PDF") and len(pdf) > 5_000
    assert b"NotoSansTC" in pdf                      # bundled CJK font embedded
    docx = render_docx(model)
    with zipfile.ZipFile(io.BytesIO(docx)) as z:
        body = z.read("word/document.xml").decode("utf-8")
        footer = z.read("word/footer1.xml").decode("utf-8")
    assert model["disclaimer"] in body and model["disclaimer"] in footer
    assert CASES[status] in body
    if lang == "zh_hant":
        assert 'w:eastAsia="Microsoft JhengHei"' in body
        assert "初步觀察報告" in body


def test_report_model_contents(fixture_dir):
    cited = _model(fixture_dir, "DB-0003", "en")
    assert cited["fixture_label"]
    assert cited["citations"] and cited["citations"][0]["number"] == 1
    assert any(c["missing"] for c in cited["brief"]["claims"])            # unresolvable citation flagged
    abstained = _model(fixture_dir, "DB-0005", "zh_hant")
    assert abstained["brief"]["review"]["heading"] == "需人工覆核"
    assert abstained["brief"]["claims"] == []
    assert abstained["images"][0]["path"] is None                          # null chip handled
    assert _model(fixture_dir, "DB-0008", "en")["brief"]["notice"]
    assert _model(fixture_dir, "DB-0007", "en")["brief"]["notice"]


def test_export_filename():
    now = datetime(2026, 10, 12, tzinfo=timezone.utc)
    assert export_filename("DB-0001", "zh_hant", "pdf", now) == "Spoonbill_DB-0001_zh_hant_20261012.pdf"
