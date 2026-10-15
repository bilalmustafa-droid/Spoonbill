from pathlib import Path

import pytest

from conftest import read_json, write_json
from core import config, loader
from core.filters import sort_anomalies
from core.loader import ContractError


def test_load_anomalies_parses_all(fixture_dir):
    col = loader.load_anomalies(fixture_dir)
    assert len(col.anomalies) == 10
    assert col.metadata.schema_version == "1.0"
    assert col.warnings == []


def test_multipolygon_parsed(fixture_dir):
    col = loader.load_anomalies(fixture_dir)
    assert {a.geometry["type"] for a in col.anomalies} == {"Polygon", "MultiPolygon"}


def test_missing_timeseries_is_none(fixture_dir):
    col = loader.load_anomalies(fixture_dir)
    with_ts = [a for a in col.anomalies if a.properties.timeseries is not None]
    without = [a for a in col.anomalies if a.properties.timeseries is None]
    assert with_ts and without
    ts = with_ts[0].properties.timeseries
    assert len(ts.months) == len(ts.vv_db) == len(ts.ndwi)


def test_sorting_does_not_rely_on_file_order(fixture_dir):
    col = loader.load_anomalies(fixture_dir)
    shuffled = list(reversed(col.anomalies))
    ordered = sort_anomalies(shuffled)
    tiers = [a.properties.confidence_tier for a in ordered]
    assert tiers == sorted(tiers, key=config.TIER_RANK.get)
    highs = [a.properties.area_ha for a in ordered if a.properties.confidence_tier == "high"]
    assert highs == sorted(highs, reverse=True)


def test_missing_brief_returns_none(fixture_dir):
    assert loader.load_brief(fixture_dir, "DB-0008") is None
    assert loader.load_brief_safe(fixture_dir, "DB-0008").state == "missing"


def test_brief_states(fixture_dir):
    assert loader.load_brief(fixture_dir, "DB-0001").status == "cited"
    assert loader.load_brief(fixture_dir, "DB-0005").status == "abstained_human_review"
    assert loader.load_brief(fixture_dir, "DB-0007").status == "error"


def test_null_chip_returns_none(fixture_dir):
    col = loader.load_anomalies(fixture_dir)
    a = next(a for a in col.anomalies if a.properties.chip_before_png is None)
    assert loader.chip_path(fixture_dir, a.properties.chip_before_png) is None
    assert loader.chip_path(fixture_dir, a.properties.chip_after_png).is_file()


def test_chip_missing_file_and_traversal_return_none(fixture_dir):
    assert loader.chip_path(fixture_dir, "chips/does-not-exist.png") is None
    assert loader.chip_path(fixture_dir, "../fixtures/data/chips/DB-0001_after.png") is None


def test_malformed_json_raises_contract_error(data_copy):
    (data_copy / config.ANOMALIES_FILENAME).write_text("{ not json", encoding="utf-8")
    with pytest.raises(ContractError) as exc:
        loader.load_anomalies(data_copy)
    assert "invalid JSON" in str(exc.value)


def test_missing_anomaly_file_raises(tmp_path):
    with pytest.raises(ContractError):
        loader.load_anomalies(tmp_path)


def test_nan_rejected(data_copy):
    path = data_copy / config.ANOMALIES_FILENAME
    text = path.read_text(encoding="utf-8").replace('"area_ha": 2.36', '"area_ha": NaN', 1)
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ContractError, match="NaN"):
        loader.load_anomalies(data_copy)


def test_schema_violation_raises_readable_error(data_copy):
    path = data_copy / config.ANOMALIES_FILENAME
    doc = read_json(path)
    doc["features"][0]["properties"]["site_id"] = "SITE_Z"
    write_json(path, doc)
    with pytest.raises(ContractError) as exc:
        loader.load_anomalies(data_copy)
    assert "features/0/properties/site_id" in str(exc.value)


def test_duplicate_ids_raise(data_copy):
    path = data_copy / config.ANOMALIES_FILENAME
    doc = read_json(path)
    doc["features"][1]["properties"]["anomaly_id"] = doc["features"][0]["properties"]["anomaly_id"]
    write_json(path, doc)
    with pytest.raises(ContractError, match="duplicate"):
        loader.load_anomalies(data_copy)


def test_unclosed_ring_raises(data_copy):
    path = data_copy / config.ANOMALIES_FILENAME
    doc = read_json(path)
    ring = next(f for f in doc["features"] if f["geometry"]["type"] == "Polygon")["geometry"]["coordinates"][0]
    ring[-1] = [ring[-1][0] + 0.001, ring[-1][1]]
    write_json(path, doc)
    with pytest.raises(ContractError, match="not closed"):
        loader.load_anomalies(data_copy)


def test_unequal_timeseries_raises(data_copy):
    path = data_copy / config.ANOMALIES_FILENAME
    doc = read_json(path)
    feat = next(f for f in doc["features"] if "timeseries" in f["properties"])
    feat["properties"]["timeseries"]["ndwi"].pop()
    write_json(path, doc)
    with pytest.raises(ContractError, match="differ in length"):
        loader.load_anomalies(data_copy)


def test_delta_mismatch_is_a_visible_warning(data_copy):
    path = data_copy / config.ANOMALIES_FILENAME
    doc = read_json(path)
    doc["features"][0]["properties"]["delta_vv_db"] = 1.0
    write_json(path, doc)
    col = loader.load_anomalies(data_copy)
    assert any("delta_vv_db" in w for w in col.warnings)


def test_malformed_brief_is_invalid_not_crash(data_copy):
    path = data_copy / config.BRIEFS_DIRNAME / "DB-0001.json"
    doc = read_json(path)
    del doc["citations"]
    write_json(path, doc)
    result = loader.load_brief_safe(data_copy, "DB-0001")
    assert result.state == "invalid"
    assert "citations" in result.error


def test_brief_with_wrong_id_rejected(data_copy):
    path = data_copy / config.BRIEFS_DIRNAME / "DB-0001.json"
    doc = read_json(path)
    doc["anomaly_id"] = "DB-0002"
    write_json(path, doc)
    with pytest.raises(ContractError):
        loader.load_brief(data_copy, "DB-0001")


def test_overview_absent_returns_none(fixture_dir):
    assert loader.load_overview(fixture_dir) is None


def test_data_dir_resolution_order(tmp_path, monkeypatch, fixture_dir):
    repo_data = tmp_path / "repo_data"
    monkeypatch.setattr(config, "REPO_DATA_DIR", repo_data)
    # nothing at repo data/ -> fixtures
    src = config.resolve_data_dir([], env={})
    assert src.origin == "fixtures" and src.is_fixture
    # repo data/ with the anomalies file -> repo
    repo_data.mkdir()
    (repo_data / config.ANOMALIES_FILENAME).write_text("{}", encoding="utf-8")
    src = config.resolve_data_dir([], env={})
    assert src.origin == "repo" and not src.is_fixture
    # env beats repo
    src = config.resolve_data_dir([], env={config.ENV_DATA_DIR: str(fixture_dir)})
    assert src.origin == "env" and src.is_fixture  # marker file travels with the folder
    # cli beats env
    other = tmp_path / "cli"
    other.mkdir()
    src = config.resolve_data_dir(["--data-dir", str(other)], env={config.ENV_DATA_DIR: str(fixture_dir)})
    assert src.origin == "cli" and src.path == Path(other).resolve() and not src.is_fixture
