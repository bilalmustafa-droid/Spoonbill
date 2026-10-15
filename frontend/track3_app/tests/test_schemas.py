import copy

import pytest
from jsonschema import Draft202012Validator

from conftest import read_json
from core import config


@pytest.fixture(scope="module")
def anomaly_validator():
    schema = read_json(config.ANOMALY_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.fixture(scope="module")
def brief_validator():
    schema = read_json(config.BRIEF_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_fixture_anomalies_validate(anomaly_validator, fixture_dir):
    doc = read_json(fixture_dir / config.ANOMALIES_FILENAME)
    assert list(anomaly_validator.iter_errors(doc)) == []


def test_fixture_counts_match_brief(fixture_dir):
    doc = read_json(fixture_dir / config.ANOMALIES_FILENAME)
    props = [f["properties"] for f in doc["features"]]
    tiers = [p["confidence_tier"] for p in props]
    assert (tiers.count("high"), tiers.count("medium"), tiers.count("low")) == (4, 4, 2)
    assert any(f["geometry"]["type"] == "MultiPolygon" for f in doc["features"])
    assert any(p["optical_available"] is False for p in props)
    assert any(p["chip_before_png"] is None for p in props)
    assert any("timeseries" in p for p in props)


def test_fixture_briefs_validate_and_cover_all_states(brief_validator, fixture_dir):
    statuses = []
    for path in sorted((fixture_dir / config.BRIEFS_DIRNAME).glob("DB-*.json")):
        doc = read_json(path)
        assert list(brief_validator.iter_errors(doc)) == [], path.name
        statuses.append(doc["status"])
    assert statuses.count("cited") == 6
    assert statuses.count("abstained_human_review") == 2
    assert statuses.count("error") == 1
    assert len(statuses) == 9  # one anomaly intentionally has no brief


def test_zh_blocks_are_real_traditional_chinese(fixture_dir):
    for path in (fixture_dir / config.BRIEFS_DIRNAME).glob("DB-*.json"):
        title = read_json(path)["zh_hant"]["title"]
        assert any("一" <= ch <= "鿿" for ch in title), path.name


def _cited_brief(fixture_dir):
    return read_json(fixture_dir / config.BRIEFS_DIRNAME / "DB-0001.json")


def test_schema_rejects_statutory_basis_when_abstained(brief_validator, fixture_dir):
    doc = copy.deepcopy(_cited_brief(fixture_dir))
    doc["status"] = "abstained_human_review"
    doc["human_review_required"] = True
    doc["abstain_reason"] = "reason"
    assert list(brief_validator.iter_errors(doc))  # statutory_basis must be empty


def test_schema_rejects_abstain_reason_on_cited(brief_validator, fixture_dir):
    doc = copy.deepcopy(_cited_brief(fixture_dir))
    doc["abstain_reason"] = "should be null"
    assert list(brief_validator.iter_errors(doc))


def test_schema_rejects_bad_enum_and_missing_field(anomaly_validator, fixture_dir):
    doc = read_json(fixture_dir / config.ANOMALIES_FILENAME)
    bad = copy.deepcopy(doc)
    bad["features"][0]["properties"]["confidence_tier"] = "very high"
    assert list(anomaly_validator.iter_errors(bad))
    bad = copy.deepcopy(doc)
    del bad["features"][0]["properties"]["zone_hint"]
    assert list(anomaly_validator.iter_errors(bad))


def test_schema_rejects_string_numbers(anomaly_validator, fixture_dir):
    doc = read_json(fixture_dir / config.ANOMALIES_FILENAME)
    doc["features"][0]["properties"]["area_ha"] = "1.42"
    assert list(anomaly_validator.iter_errors(doc))
