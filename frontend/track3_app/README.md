# Project Spoonbill: Track 3 (Streamlit UI and reporting)

Dashboard for screening persistent wetland-to-land change in the Deep Bay area. It reads Track 1's anomaly
GeoJSON and chips and Track 2's brief JSON from disk, then renders a map, the satellite evidence and a
bilingual (English / 繁體中文) preliminary brief, with PDF and DOCX export.

**The app never calls Earth Engine or an LLM.** It only reads files, so the live demo does not depend on any
external service. The only network use is the base-map tiles (Esri World Imagery / OpenStreetMap); without
internet the anomaly outlines still draw on a blank background.

## Run

Windows (Command Prompt), from a fresh clone:

```bat
track3_app\run.bat
```

macOS / Linux:

```bash
./track3_app/run.sh
```

The first run creates `track3_app/.venv`, installs the pinned `requirements.txt` and opens the app at
http://localhost:8501. Later runs start immediately. Python 3.11+ is required (developed on 3.13).

Options (work with both scripts):

| Command | Effect |
|---|---|
| `run.bat --demo` | Demo mode: preloads the three strongest anomalies and a scripted click path (also a sidebar toggle, or `SPOONBILL_DEMO=1`) |
| `run.bat --data-dir D:\some\data` | Use an explicit data folder |

## Fixtures vs real data

The data folder is resolved in this order (see `core/config.py`):

1. `--data-dir PATH`
2. the `SPOONBILL_DATA_DIR` environment variable
3. `data/` at the repo root, if `data/anomalies_v1.geojson` exists
4. `track3_app/fixtures/data/` (bundled synthetic fixtures)

When fixture data is in use, a red **FIXTURE MODE: synthetic demo data, not real satellite results** banner is
shown on the page and in the sidebar, chip captions say "synthetic test image", and exports carry a
"SYNTHETIC FIXTURE DATA" banner. Fixture detection uses the `FIXTURE_DATA.txt` marker file, so a copied fixture
folder still shows the banner.

To switch to real data, put Track 1 and Track 2 output in `data/` at the repo root and restart:

```
data/
├── anomalies_v1.geojson
├── chips/DB-0001_before.png ...
└── briefs/DB-0001.json ...        (+ optional briefs/_overview.json)
```

Regenerate fixtures (deterministic, validated against the schemas, fails loudly on error):

```bat
track3_app\.venv\Scripts\python.exe track3_app\fixtures\make_fixtures.py
```

The fixtures hold 10 anomalies (4 high, 4 medium, 2 low), including a MultiPolygon, a radar-only detection,
a null chip and two timeseries. There are 6 cited briefs, 2 abstained, 1 error and 1 anomaly with no brief.
Fixture citations point to clearly synthetic documents with `.invalid` URLs. DB-0003 deliberately cites an
ID that does not resolve, to exercise the "citation unavailable" marker.

## Tests

```bat
cd track3_app
.venv\Scripts\python.exe -m pytest
```

These cover schema validation of the fixtures, loader edge cases (missing brief, null chip, MultiPolygon,
malformed JSON, NaN, duplicate IDs, unclosed rings, unequal timeseries), citation resolution including the
unresolvable case, the content safeguard, formatting and i18n wording rules, PDF/DOCX export for every status
in both languages, and AppTest smoke tests (start, select, language toggle, filters, export, demo mode).

## Folder map

```
contract/                     JSON Schemas for contract v1.0 (shared)
INTEGRATION_ISSUES.md         upstream mismatches, appended by the app for real data only (shared)
track3_app/
├── app.py                    Streamlit entry point
├── core/                     data layer, no Streamlit imports (testable)
│   ├── config.py             paths, data-folder resolution, tier colours/glyphs
│   ├── models.py             pydantic v2 models mirroring the contract
│   ├── loader.py             schema-validated loading, ContractError, chip_path
│   ├── brief_content.py      citation resolution + screened display text (shared by UI and exports)
│   ├── content_guard.py      withholds personal data / legal-conclusion wording from upstream text
│   ├── filters.py            sort, filter, headline maths, demo ranking
│   ├── formatting.py         number/date formatting, delta_label
│   ├── i18n.py               all UI strings (en, zh_hant) and the mandated disclaimer
│   └── issues.py             deduplicated INTEGRATION_ISSUES.md logging
├── ui/                       Streamlit components (sidebar, header, map, detail, brief, export, demo, footer)
├── export/                   report_model.py (shared), pdf_export.py (reportlab), docx_export.py (python-docx)
├── assets/fonts/             NotoSansTC-Regular.ttf + OFL.txt (bundled CJK font for PDF)
├── scripts/fetch_fonts.py    regenerates the bundled font from google/fonts
├── fixtures/                 make_fixtures.py and the generated synthetic data
├── tests/                    pytest + AppTest
├── .streamlit/config.toml    theme and widget settings
└── run.bat / run.sh          one-command install + launch
```

## Product rules built into the code

- **No personal data.** The UI only renders contract fields. Upstream free text passes through
  `core/content_guard.py`, which withholds text that looks like personal data (HKID, phone, email,
  flat/room addresses, honorific plus name). Withheld text keeps its slot with a visible notice.
- **No legal conclusions.** UI copy is tested to contain no "illegal / unauthorised / violation / breach"
  (or 違法 / 非法 / 違例 / 違規 ...), except inside the mandated disclaimer. Upstream prose using such
  wording is withheld and logged. Verbatim citation quotes are checked for personal data only.
- **Cite or abstain.** `abstained_human_review` renders as an intentional amber "Requires human review" panel
  with the reason and the evidence, and no statutory basis. `error` shows a neutral notice with no upstream
  text. A missing brief shows "analysis pending". An invalid brief file shows a neutral notice and is logged.
- **Every citation_id must resolve.** If one does not, the claim stays visible with a red "Citation
  unavailable" marker. It is never dropped or invented, and it is logged to `INTEGRATION_ISSUES.md`.
- **Disclaimer** in the footer, in every PDF/DOCX (page footer and closing box) and in the language shown.
- **Fail loudly.** Schema violations, NaN/Infinity, duplicate IDs, unclosed rings and unequal timeseries
  raise `ContractError`, which is shown in full with nothing rendered. Numeric inconsistencies
  (delta ≠ current − baseline, anomaly_count mismatch) are shown as warnings and are never corrected.

## Exports

- PDF uses **reportlab** with the bundled Noto Sans TC (SIL OFL 1.1, committed in `assets/fonts/`).
  WeasyPrint was tried first but needs GTK/Pango system libraries that Windows does not ship
  (`cannot load library 'libgobject-2.0-0'`).
- DOCX uses **python-docx**. Every run sets the East Asian font to Microsoft JhengHei (bundled with Windows
  and Office), because python-docx cannot embed fonts.
- Both are generated in memory only when the download button is clicked. Filenames:
  `Spoonbill_{anomaly_id}_{lang}_{YYYYMMDD}.pdf|docx`.

## Known limitations

- Base-map tiles need internet. The anomaly layer does not.
- DOCX relies on Microsoft JhengHei being installed where it is opened (true for Windows/Office). On other
  systems Word substitutes a CJK font. PDF has no such dependency.
- `abstain_reason` is a single-language string in the contract, so it is shown as provided in both languages.
- The overview tab appears only when `data/briefs/_overview.json` exists. That file has no JSON Schema in
  contract v1.0, so only its documented keys are read.
- The content safeguard is a pattern-based last line of defence. Redaction is Track 2's responsibility.
- The map highlights the selection with a cyan outline, and the colour-blind cue is the outline style
  (solid / dashed / dotted) plus the tier glyph in tooltips and badges.
