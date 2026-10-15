"""End-to-end smoke test with streamlit.testing.v1.AppTest on fixture data."""

import pytest
from streamlit.testing.v1 import AppTest

from conftest import APP_DIR
from core import config, loader
from ui.export_buttons import make_exporters

APP = str(APP_DIR / "app.py")


@pytest.fixture
def app(monkeypatch, fixture_dir):
    monkeypatch.setenv(config.ENV_DATA_DIR, str(fixture_dir))
    monkeypatch.delenv(config.ENV_DEMO, raising=False)
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def _all_markdown(at) -> str:
    return "\n".join(m.value for m in at.markdown)


def test_app_starts_with_banner_disclaimer_and_metrics(app):
    text = _all_markdown(app)
    assert "FIXTURE MODE: synthetic demo data, not real satellite results" in text
    assert config.FIXTURE_MARKER  # banner driven by fixture detection
    assert "Satellite-derived indicator for screening purposes only." in text
    assert [m.label for m in app.metric][:4] == ["Anomalies shown", "Total area", "Requiring human review",
                                                  "Imagery up to"]
    assert app.metric[0].value == "8"          # low tier hidden by default


def test_select_anomaly_and_states(app):
    sel = app.selectbox(key="w_selected_id_en")
    assert sel.value == "DB-0001"              # strongest visible detection preselected
    sel.set_value("DB-0005").run()
    assert not app.exception
    assert "Requires human review" in _all_markdown(app)
    app.selectbox(key="w_selected_id_en").set_value("DB-0007").run()
    assert "could not be generated" in _all_markdown(app)
    app.selectbox(key="w_selected_id_en").set_value("DB-0008").run()
    assert "Analysis pending" in _all_markdown(app)
    app.selectbox(key="w_selected_id_en").set_value("DB-0003").run()
    assert "Citation unavailable" in _all_markdown(app)


def test_language_toggle_keeps_selection_and_filters(app):
    app.selectbox(key="w_selected_id_en").set_value("DB-0005").run()
    app.multiselect(key="w_f_sites_en").set_value(["SITE_B"]).run()
    app.radio(key="w_lang").set_value("zh_hant").run()
    assert not app.exception
    assert app.title[0].value == "黑臉琵鷺計劃：后海灣濕地變化篩查"
    # Translated widgets are per-language (ui/state.py); the canonical values must carry over.
    assert app.selectbox(key="w_selected_id_zh_hant").value == "DB-0005"
    assert app.multiselect(key="w_f_sites_zh_hant").value == ["SITE_B"]
    text = _all_markdown(app)
    assert "需人工覆核" in text
    assert "本結果為衛星遙感篩查指標" in text
    # ...and back again (this round trip used to wipe the filters in the browser)
    app.radio(key="w_lang").set_value("en").run()
    assert app.multiselect(key="w_f_sites_en").value == ["SITE_B"]
    assert app.selectbox(key="w_selected_id_en").value == "DB-0005"


def test_empty_filter_result_draws_map_without_error(app):
    app.multiselect(key="w_f_sites_en").set_value([]).run()
    assert not app.exception
    assert app.metric[0].value == "0"
    assert not any("Map could not be drawn" in w.value for w in app.warning)
    assert "No anomalies match" in "\n".join(i.value for i in app.info)


def test_show_low_and_reset(app):
    app.toggle(key="w_f_show_low").set_value(True).run()
    assert app.metric[0].value == "10"
    app.button[0].click().run()  # first button in the sidebar is Reset
    assert app.metric[0].value == "8"


def test_export_buttons_render_and_produce_bytes(app, fixture_dir):
    assert len(app.get("download_button")) == 2    # PDF + DOCX for the selected anomaly
    source = config.resolve_data_dir([], env={config.ENV_DATA_DIR: str(fixture_dir)})
    col = loader.load_anomalies(fixture_dir)
    for aid in ("DB-0001", "DB-0005"):
        pdf, docx = make_exporters(col.by_id(aid), loader.load_brief_safe(fixture_dir, aid), source, "zh_hant")
        assert pdf().startswith(b"%PDF")
        assert docx()[:2] == b"PK"


def test_demo_mode_preloads_strongest(monkeypatch, fixture_dir):
    monkeypatch.setenv(config.ENV_DATA_DIR, str(fixture_dir))
    monkeypatch.setenv(config.ENV_DEMO, "1")
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    assert at.selectbox(key="w_selected_id_en").value == "DB-0001"
    assert "Demo path" in _all_markdown(at)
    next_button = next(b for b in at.button if b.key == "demo_next")
    next_button.click().run()
    assert at.selectbox(key="w_selected_id_en").value != "DB-0001"
