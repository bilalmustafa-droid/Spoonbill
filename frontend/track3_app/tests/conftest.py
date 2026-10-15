from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from core import config  # noqa: E402

FIXTURE_DIR = config.FIXTURE_DATA_DIR


@pytest.fixture
def fixture_dir() -> Path:
    if not (FIXTURE_DIR / config.ANOMALIES_FILENAME).is_file():
        pytest.fail("fixtures missing: run python track3_app/fixtures/make_fixtures.py")
    return FIXTURE_DIR


@pytest.fixture
def data_copy(tmp_path, fixture_dir) -> Path:
    """A writable copy of the fixture data folder."""
    dest = tmp_path / "data"
    shutil.copytree(fixture_dir, dest)
    return dest


def read_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, doc) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
