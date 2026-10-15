"""Paths, data-directory resolution and shared constants. No Streamlit imports in core/."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]          # track3_app/ (folder name is not hardcoded)
REPO_ROOT = APP_DIR.parent
CONTRACT_DIR = REPO_ROOT / "contract"
REPO_DATA_DIR = REPO_ROOT / "data"
FIXTURE_DATA_DIR = APP_DIR / "fixtures" / "data"
ASSETS_DIR = APP_DIR / "assets"
FONT_DIR = ASSETS_DIR / "fonts"
CJK_FONT_PATH = FONT_DIR / "NotoSansTC-Regular.ttf"
INTEGRATION_ISSUES_PATH = Path(os.environ.get("SPOONBILL_ISSUES_FILE", REPO_ROOT / "INTEGRATION_ISSUES.md"))

ANOMALIES_FILENAME = "anomalies_v1.geojson"
BRIEFS_DIRNAME = "briefs"
OVERVIEW_FILENAME = "_overview.json"
FIXTURE_MARKER = "FIXTURE_DATA.txt"
ANOMALY_SCHEMA_PATH = CONTRACT_DIR / "anomaly.schema.json"
BRIEF_SCHEMA_PATH = CONTRACT_DIR / "brief.schema.json"

ENV_DATA_DIR = "SPOONBILL_DATA_DIR"
ENV_DEMO = "SPOONBILL_DEMO"

LANGS = ("en", "zh_hant")
DEFAULT_LANG = "en"

TIERS = ("high", "medium", "low")
TIER_RANK = {"high": 0, "medium": 1, "low": 2}
# Colour plus a second visual channel (marker glyph and outline dash) so tiers are distinguishable
# without colour vision.
TIER_STYLE = {
    "high":   {"color": "#D9480F", "glyph": "▲", "dash": None,    "weight": 3},
    "medium": {"color": "#F2A100", "glyph": "◆", "dash": "8 5",   "weight": 2.5},
    "low":    {"color": "#868E96", "glyph": "●", "dash": "2 5",   "weight": 2},
}
SELECTED_OUTLINE = "#00E5FF"

ZONE_HINTS = ("WCA", "WBA", "OTHER", "UNKNOWN")
SITE_IDS = ("SITE_A", "SITE_B", "SITE_C")
BRIEF_STATUSES = ("cited", "abstained_human_review", "error")

# Geometry simplification tolerance in degrees (~1 m at Deep Bay latitude). Only affects the map
# drawing, never the numbers shown.
SIMPLIFY_TOLERANCE_DEG = 0.00001


@dataclass(frozen=True)
class DataSource:
    path: Path
    origin: str          # "cli" | "env" | "repo" | "fixtures"
    is_fixture: bool     # True when the folder carries the fixture marker file


def _parse_cli_data_dir(argv: list[str] | None) -> str | None:
    """Reads `--data-dir` from `streamlit run app.py -- --data-dir X`. Unknown args are ignored."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--demo", action="store_true")
    known, _ = parser.parse_known_args(argv if argv is not None else [])
    return known.data_dir


def demo_mode_requested(argv: list[str] | None = None) -> bool:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--demo", action="store_true")
    known, _ = parser.parse_known_args(argv if argv is not None else [])
    return known.demo or os.environ.get(ENV_DEMO, "").strip().lower() in {"1", "true", "yes"}


def resolve_data_dir(argv: list[str] | None = None, env: dict | None = None) -> DataSource:
    """Resolution order: --data-dir, SPOONBILL_DATA_DIR, repo data/ (if anomalies file exists), fixtures."""
    env = os.environ if env is None else env
    cli = _parse_cli_data_dir(argv)
    if cli:
        path, origin = Path(cli).expanduser().resolve(), "cli"
    elif env.get(ENV_DATA_DIR):
        path, origin = Path(env[ENV_DATA_DIR]).expanduser().resolve(), "env"
    elif (REPO_DATA_DIR / ANOMALIES_FILENAME).is_file():
        path, origin = REPO_DATA_DIR, "repo"
    else:
        path, origin = FIXTURE_DATA_DIR, "fixtures"
    # Assumption: a data folder counts as fixture data when it is the bundled fixtures folder or
    # carries the marker file (so a copied fixture folder still shows the banner).
    is_fixture = origin == "fixtures" or (path / FIXTURE_MARKER).is_file()
    return DataSource(path=path, origin=origin, is_fixture=is_fixture)
