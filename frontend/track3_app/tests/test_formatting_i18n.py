import re

import pytest

from core import formatting as f
from core.i18n import DISCLAIMER, STRINGS, disclaimer, t

PROJECT_DISCLAIMER_EN = ("Satellite-derived indicator for screening purposes only. This is not a legal determination "
                         "of unauthorised development. Findings require site verification by the relevant authority.")
PROJECT_DISCLAIMER_ZH = "本結果為衛星遙感篩查指標，僅供參考，並非對違例發展的法律認定。相關發現須由主管部門進行實地核實。"


def test_area_db_ndwi():
    assert f.fmt_area(1.4234) == "1.42 ha"
    assert f.fmt_area(1.4234, "zh_hant") == "1.42 公頃"
    assert f.fmt_db(5.94) == "+5.9 dB"
    assert f.fmt_db(-19.8) == "-19.8 dB"
    assert f.fmt_ndwi(0.314) == "0.31"
    assert f.fmt_ndwi(-0.35, signed=True) == "-0.35"
    assert f.fmt_ndwi(0.2, signed=True) == "+0.20"


def test_delta_label_and_persistence():
    assert f.delta_label(5.9, "db") == "+5.9 dB vs baseline"
    assert f.delta_label(-0.35, "ndwi") == "-0.35 vs baseline"
    assert f.delta_label(5.9, "db", "zh_hant") == "較基線 +5.9 dB"
    assert f.persistence_label(5, 6) == "5 of 6 months"
    assert f.persistence_label(5, 6, "zh_hant") == "6 個月中有 5 個月"


def test_dates_and_timestamps():
    assert f.fmt_date("2025-04-01") == "2025-04-01"
    assert f.fmt_timestamp("2026-10-12T04:00:00Z") == "2026-10-12 04:00 UTC"
    with pytest.raises(ValueError):
        f.fmt_date("2025/04/01")


def test_none_renders_not_available():
    for fn in (f.fmt_area, f.fmt_db, f.fmt_ndwi, f.fmt_date, f.fmt_timestamp):
        assert fn(None) == "not available"
        assert fn(None, "zh_hant") == "不適用"
    assert f.delta_label(None, "db") == "not available"


def test_disclaimer_is_exact_project_text():
    assert disclaimer("en") == PROJECT_DISCLAIMER_EN
    assert disclaimer("zh_hant") == PROJECT_DISCLAIMER_ZH


def test_every_string_has_both_languages():
    for key, entry in STRINGS.items():
        assert entry.get("en") and entry.get("zh_hant"), key


BANNED_EN = re.compile(r"illegal|unauthori[sz]ed|violation|breach", re.IGNORECASE)
BANNED_ZH = re.compile(r"違法|非法|違例|違規|違反|未經授權|未經許可")
# Characters that exist only in Simplified Chinese; their presence would mean mainland forms slipped in.
SIMPLIFIED_ONLY = set("区湿缓冲观数据报这为发现应时间态级识图选择显维础卫遥测筛认门实档简资")


def test_ui_copy_has_no_legal_conclusion_wording():
    for key, entry in STRINGS.items():
        assert not BANNED_EN.search(entry["en"]), key
        assert not BANNED_ZH.search(entry["zh_hant"]), key


def test_ui_copy_is_traditional_chinese():
    for key, entry in list(STRINGS.items()) + [("disclaimer", DISCLAIMER)]:
        assert not (set(entry["zh_hant"]) & SIMPLIFIED_ONLY), key


def test_format_placeholders_resolve():
    assert t("persistence_value", "en", count=1, total=2) == "1 of 2 months"
    assert "DB-0001" in t("demo_open", "zh_hant", id="DB-0001")
