"""UI strings for English and Traditional Chinese (Hong Kong). Every visible label goes through t().

Wording rule: never "illegal", "unauthorised", "violation" or "breach" (or Chinese equivalents) in UI
copy. The only exception is the mandated disclaimer text, which is reproduced verbatim.
tests/test_i18n.py enforces this.
"""

from __future__ import annotations

DISCLAIMER = {
    "en": "Satellite-derived indicator for screening purposes only. This is not a legal determination of "
          "unauthorised development. Findings require site verification by the relevant authority.",
    "zh_hant": "本結果為衛星遙感篩查指標，僅供參考，並非對違例發展的法律認定。相關發現須由主管部門進行實地核實。",
}

STRINGS: dict[str, dict[str, str]] = {
    # app chrome
    "app_title": {"en": "Project Spoonbill: Deep Bay wetland change screening",
                  "zh_hant": "黑臉琵鷺計劃：后海灣濕地變化篩查"},
    "app_subtitle": {"en": "Preliminary satellite indicators of persistent wetland-to-land change, grounded in "
                           "Hong Kong statutory documents.",
                     "zh_hant": "以衛星數據篩查持續的濕地轉為陸地變化，並以香港法定文件作依據的初步指標。"},
    "fixture_banner": {"en": "FIXTURE MODE: synthetic demo data, not real satellite results",
                       "zh_hant": "測試資料模式：合成示範數據，並非真實衛星結果"},
    "language": {"en": "Language / 語言", "zh_hant": "Language / 語言"},
    "na": {"en": "not available", "zh_hant": "不適用"},

    # sidebar
    "filters": {"en": "Filters", "zh_hant": "篩選"},
    "site_filter": {"en": "Site", "zh_hant": "地點"},
    "confidence_filter": {"en": "Confidence", "zh_hant": "可信度"},
    "show_low": {"en": "Show low confidence", "zh_hant": "顯示低可信度"},
    "date_filter": {"en": "First detected between", "zh_hant": "首次偵測日期範圍"},
    "reset_filters": {"en": "Reset filters", "zh_hant": "重設篩選"},
    "provenance": {"en": "Data provenance", "zh_hant": "數據來源"},
    "prov_generated": {"en": "Generated", "zh_hant": "生成時間"},
    "prov_baseline": {"en": "Baseline window", "zh_hant": "基線期"},
    "prov_current": {"en": "Current window", "zh_hant": "現時期"},
    "prov_sensors": {"en": "Sensors", "zh_hant": "感測器"},
    "prov_aoi": {"en": "Area of interest", "zh_hant": "研究範圍"},
    "prov_source": {"en": "Data folder", "zh_hant": "數據資料夾"},
    "source_fixtures": {"en": "bundled fixtures (synthetic)", "zh_hant": "內置測試資料（合成）"},
    "source_repo": {"en": "repository data/", "zh_hant": "儲存庫 data/"},
    "source_cli": {"en": "--data-dir argument", "zh_hant": "--data-dir 參數"},
    "source_env": {"en": "SPOONBILL_DATA_DIR", "zh_hant": "SPOONBILL_DATA_DIR"},
    "demo_mode": {"en": "Demo mode", "zh_hant": "示範模式"},

    # tiers, sites, zones
    "tier_high": {"en": "High", "zh_hant": "高"},
    "tier_medium": {"en": "Medium", "zh_hant": "中"},
    "tier_low": {"en": "Low", "zh_hant": "低"},
    "tier_badge": {"en": "{tier} confidence", "zh_hant": "{tier}可信度"},
    "SITE_A": {"en": "Site A", "zh_hant": "A 地點"},
    "SITE_B": {"en": "Site B", "zh_hant": "B 地點"},
    "SITE_C": {"en": "Site C", "zh_hant": "C 地點"},
    "zoning_label": {"en": "Zoning (indicative)", "zh_hant": "分區（指示性）"},
    "zone_WCA": {"en": "Wetland Conservation Area (WCA)", "zh_hant": "濕地保育區"},
    "zone_WBA": {"en": "Wetland Buffer Area (WBA)", "zh_hant": "濕地緩衝區"},
    "zone_OTHER": {"en": "Other zoning", "zh_hant": "其他分區"},
    "zone_UNKNOWN": {"en": "Unknown", "zh_hant": "未能確定"},
    "zone_note": {"en": "Indicative overlay only, not a zoning determination.",
                  "zh_hant": "僅屬指示性疊加資料，並非分區認定。"},

    # header metrics
    "m_count": {"en": "Anomalies shown", "zh_hant": "顯示的異常點"},
    "m_area": {"en": "Total area", "zh_hant": "總面積"},
    "m_review": {"en": "Requiring human review", "zh_hant": "需人工覆核"},
    "m_review_help": {"en": "Briefs flagged human_review_required (abstained or failed). "
                            "Anomalies whose brief is still pending are not counted.",
                      "zh_hant": "簡報標示為需人工覆核（放棄引用或生成失敗）。尚待分析的異常點不計算在內。"},
    "m_latest": {"en": "Imagery up to", "zh_hant": "影像截至"},
    "m_latest_help": {"en": "End of the current observation window in the data file.",
                      "zh_hant": "數據檔案中現時觀測期的結束日期。"},

    # map
    "map_heading": {"en": "Map", "zh_hant": "地圖"},
    "legend": {"en": "Legend", "zh_hant": "圖例"},
    "legend_line_solid": {"en": "solid outline", "zh_hant": "實線外框"},
    "legend_line_dashed": {"en": "dashed outline", "zh_hant": "虛線外框"},
    "legend_line_dotted": {"en": "dotted outline", "zh_hant": "點線外框"},
    "legend_selected": {"en": "cyan outline = selected", "zh_hant": "青色外框＝已選取"},
    "tt_id": {"en": "Anomaly", "zh_hant": "異常點"},
    "tt_area": {"en": "Area", "zh_hant": "面積"},
    "tt_zone": {"en": "Zoning (indicative)", "zh_hant": "分區（指示性）"},
    "tt_tier": {"en": "Confidence", "zh_hant": "可信度"},
    "select_anomaly": {"en": "Selected anomaly", "zh_hant": "已選取的異常點"},
    "map_hint": {"en": "Click a polygon on the map or choose from the list.",
                 "zh_hant": "點擊地圖上的範圍，或從清單中選擇。"},
    "no_matches": {"en": "No anomalies match the current filters.", "zh_hant": "沒有符合篩選條件的異常點。"},
    "selection_hidden": {"en": "The previously selected anomaly is hidden by the current filters.",
                         "zh_hant": "先前選取的異常點已被目前的篩選條件隱藏。"},
    "tiles_note": {"en": "Base map tiles need an internet connection; anomaly outlines are drawn from local files.",
                   "zh_hant": "底圖需要互聯網連線；異常範圍由本機檔案繪製。"},

    # detail panel
    "detail_heading": {"en": "Anomaly detail", "zh_hant": "異常點詳情"},
    "persistence": {"en": "Persistence", "zh_hant": "持續性"},
    "persistence_value": {"en": "{count} of {total} months", "zh_hant": "{total} 個月中有 {count} 個月"},
    "radar_only": {"en": "Radar only", "zh_hant": "僅雷達"},
    "radar_only_help": {"en": "Optical imagery was unavailable (cloud), so this detection relies on Sentinel-1 radar.",
                        "zh_hant": "因雲層遮蔽未有光學影像，此偵測只依據 Sentinel-1 雷達數據。"},
    "brightness_flag": {"en": "Optical brightness flag", "zh_hant": "光學亮度標記"},
    "metric": {"en": "Measure", "zh_hant": "指標"},
    "baseline": {"en": "Baseline", "zh_hant": "基線"},
    "current": {"en": "Current", "zh_hant": "現時"},
    "delta": {"en": "Change", "zh_hant": "變化"},
    "vv_row": {"en": "Radar backscatter VV (dB)", "zh_hant": "雷達後向散射 VV (dB)"},
    "ndwi_row": {"en": "NDWI (water index)", "zh_hant": "NDWI（水體指數）"},
    "area": {"en": "Area", "zh_hant": "面積"},
    "first_detected": {"en": "First detected", "zh_hant": "首次偵測"},
    "coordinates": {"en": "Centroid (lon, lat)", "zh_hant": "中心點（經度, 緯度）"},
    "site": {"en": "Site", "zh_hant": "地點"},
    "ha": {"en": "ha", "zh_hant": "公頃"},
    "vs_baseline": {"en": "{value} vs baseline", "zh_hant": "較基線 {value}"},
    "chip_before": {"en": "Before (baseline)", "zh_hant": "之前（基線）"},
    "chip_after": {"en": "After (current)", "zh_hant": "之後（現時）"},
    "chip_missing": {"en": "Image not available", "zh_hant": "未有影像"},
    "chip_synthetic": {"en": "synthetic test image", "zh_hant": "合成測試影像"},
    "timeseries": {"en": "Monthly time series", "zh_hant": "每月時間序列"},
    "month": {"en": "Month", "zh_hant": "月份"},
    "baseline_period": {"en": "baseline period", "zh_hant": "基線期"},

    # brief
    "brief_heading": {"en": "Preliminary brief", "zh_hant": "初步簡報"},
    "summary": {"en": "Summary", "zh_hant": "摘要"},
    "evidence": {"en": "Evidence", "zh_hant": "證據"},
    "statutory_basis": {"en": "Statutory basis", "zh_hant": "法定依據"},
    "recommended_action": {"en": "Recommended action", "zh_hant": "建議行動"},
    "limitations": {"en": "Limitations", "zh_hant": "限制"},
    "sources": {"en": "Sources", "zh_hant": "來源"},
    "citations": {"en": "Citations", "zh_hant": "引用"},
    "doc": {"en": "Document", "zh_hant": "文件"},
    "page": {"en": "Page", "zh_hant": "頁"},
    "section": {"en": "Section", "zh_hant": "章節"},
    "quote": {"en": "Quote", "zh_hant": "引文"},
    "open_source": {"en": "Open source document", "zh_hant": "開啟來源文件"},
    "no_source_url": {"en": "No public link provided", "zh_hant": "未有提供公開連結"},
    "citation_unavailable": {"en": "Citation unavailable: {ids}", "zh_hant": "引用不可用：{ids}"},
    "citation_unavailable_help": {
        "en": "This citation ID does not match any retrieved source. The claim is shown unverified and the "
              "mismatch has been logged for the analysis team.",
        "zh_hant": "此引用編號未能對應任何已檢索的來源。該陳述未經核實，相關問題已記錄並轉交分析團隊。"},
    "review_heading": {"en": "Requires human review", "zh_hant": "需人工覆核"},
    "review_body": {"en": "The analysis pipeline did not find statutory text it could cite with confidence, so it "
                          "deliberately made no statutory claim. The satellite evidence below still stands and "
                          "should be reviewed by an officer.",
                    "zh_hant": "分析流程未能找到可有把握引用的法定條文，因此刻意不作任何法定依據陳述。"
                               "以下衛星證據仍然有效，應由人員覆核。"},
    "review_reason": {"en": "Reason given by the analysis pipeline", "zh_hant": "分析流程提供的原因"},
    "error_notice": {"en": "A brief could not be generated for this anomaly. The satellite metrics above are "
                           "unaffected. The analysis team has been notified through the data file status.",
                     "zh_hant": "未能為此異常點生成簡報。上方的衛星指標不受影響。分析團隊可從數據檔案狀態得知此情況。"},
    "pending_notice": {"en": "Analysis pending: no brief has been produced for this anomaly yet.",
                       "zh_hant": "分析待定：此異常點尚未生成簡報。"},
    "invalid_notice": {"en": "The brief file for this anomaly does not match the data contract, so it is not shown.",
                       "zh_hant": "此異常點的簡報檔案不符合數據規格，因此不予顯示。"},
    "withheld": {"en": "Text withheld by content safeguard ({reason}).", "zh_hant": "內容已被保護機制隱藏（{reason}）。"},
    "reason_personal": {"en": "possible personal data", "zh_hant": "可能含個人資料"},
    "reason_legal": {"en": "wording that could read as a legal conclusion",
                     "zh_hant": "措辭可能被視為法律結論"},
    "brief_meta": {"en": "Generated {when} · model {model}", "zh_hant": "生成時間 {when} · 模型 {model}"},

    # export
    "export_heading": {"en": "Export preliminary brief", "zh_hant": "匯出初步簡報"},
    "export_pdf": {"en": "Download PDF", "zh_hant": "下載 PDF"},
    "export_docx": {"en": "Download DOCX", "zh_hant": "下載 DOCX"},
    "export_font_missing": {"en": "PDF export unavailable: the bundled CJK font is missing. Run "
                                  "scripts/fetch_fonts.py (see README).",
                            "zh_hant": "未能匯出 PDF：缺少內置中文字型。請執行 scripts/fetch_fonts.py（見 README）。"},

    # report
    "report_title": {"en": "Preliminary Observation Report", "zh_hant": "初步觀察報告"},
    "report_generated": {"en": "Report generated", "zh_hant": "報告生成時間"},
    "report_fixture": {"en": "SYNTHETIC FIXTURE DATA: not real satellite results",
                       "zh_hant": "合成測試資料：並非真實衛星結果"},
    "report_status": {"en": "Brief status", "zh_hant": "簡報狀態"},
    "status_cited": {"en": "Cited", "zh_hant": "已引用"},
    "status_abstained_human_review": {"en": "Requires human review", "zh_hant": "需人工覆核"},
    "status_error": {"en": "Generation failed", "zh_hant": "生成失敗"},
    "status_missing": {"en": "Analysis pending", "zh_hant": "分析待定"},
    "status_invalid": {"en": "Brief file invalid", "zh_hant": "簡報檔案無效"},
    "metrics_heading": {"en": "Satellite metrics", "zh_hant": "衛星指標"},
    "images_heading": {"en": "Before and after", "zh_hant": "前後對比"},
    "location_heading": {"en": "Location", "zh_hant": "位置"},

    # overview tab
    "tab_map": {"en": "Map and detail", "zh_hant": "地圖及詳情"},
    "tab_overview": {"en": "Overview", "zh_hant": "總覽"},
    "overview_totals": {"en": "Totals reported by the analysis pipeline", "zh_hant": "分析流程報告的總數"},

    # demo
    "demo_heading": {"en": "Demo path", "zh_hant": "示範路線"},
    "demo_step": {"en": "Step {n} of {total}", "zh_hant": "第 {n} 步，共 {total} 步"},
    "demo_prev": {"en": "Previous", "zh_hant": "上一步"},
    "demo_next": {"en": "Next", "zh_hant": "下一步"},
    "demo_open": {"en": "Show anomaly {id}", "zh_hant": "顯示異常點 {id}"},
    "demo_note_strongest": {"en": "Strongest detection ({rank} of 3): walk through the evidence, then the brief.",
                            "zh_hant": "最強偵測（第 {rank} 個，共 3 個）：先講解證據，再講解簡報。"},
    "demo_note_language": {"en": "Switch language to show the same brief in Traditional Chinese.",
                           "zh_hant": "切換語言，以繁體中文展示同一份簡報。"},
    "demo_note_review": {"en": "Show an abstained brief: the system declines to cite rather than guess.",
                         "zh_hant": "展示放棄引用的簡報：系統寧可不引用，也不會猜測。"},
    "demo_note_export": {"en": "Export the brief as PDF or DOCX.", "zh_hant": "將簡報匯出為 PDF 或 DOCX。"},

    # footer
    "methodology": {"en": "Methodology", "zh_hant": "方法"},
    "methodology_text": {
        "en": "Sensors: {sensors}. Each month is compared with the same calendar month of the baseline "
              "({b0} to {b1}); a pixel is flagged when radar backscatter rises by more than {dvv} dB and NDWI "
              "changes by less than {dndwi}. Despeckle: {despeckle}. Persistence rule: {persistence}. "
              "Minimum mapped area: {min_area} ha. Current window: {c0} to {c1}.",
        "zh_hant": "感測器：{sensors}。每月數據與基線期（{b0} 至 {b1}）同一曆月比較；當雷達後向散射上升超過 "
                   "{dvv} dB 而 NDWI 變化低於 {dndwi}，該像素即被標示。去斑處理：{despeckle}。持續性規則："
                   "{persistence}。最小製圖面積：{min_area} 公頃。現時期：{c0} 至 {c1}。"},
    "disclaimer_label": {"en": "Disclaimer", "zh_hant": "免責聲明"},

    # errors
    "contract_error": {"en": "The anomaly data file does not match the data contract, so nothing is shown. "
                             "Fix the upstream file and reload.",
                       "zh_hant": "異常點數據檔案不符合數據規格，因此不顯示任何內容。請修正上游檔案後重新載入。"},
    "consistency_warning": {"en": "Data consistency warnings (shown, not corrected):",
                            "zh_hant": "數據一致性警告（僅顯示，未作修正）："},
}


def t(key: str, lang: str, **kwargs) -> str:
    """Translate key into lang ("en" or "zh_hant"). Raises KeyError on unknown keys so gaps surface in tests."""
    entry = STRINGS[key]
    text = entry.get(lang) or entry["en"]
    return text.format(**kwargs) if kwargs else text


def disclaimer(lang: str) -> str:
    return DISCLAIMER["zh_hant" if lang == "zh_hant" else "en"]
