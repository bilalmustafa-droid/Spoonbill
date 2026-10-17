r"""
Validates a data file against Project Spoonbill's frozen contract. Did not
exist in the repo before; written as a standalone check any script or person
can run, separate from the frontend's own loader validation.

Auto-detects which schema to use: a FeatureCollection validates against
contract/anomaly.schema.json, anything else with a top-level "citations" key
validates against contract/brief.schema.json.

Usage:
    python tools\validate_contract.py data\anomalies_v1.geojson
    python tools\validate_contract.py data\briefs\DB-0001.json
    python tools\validate_contract.py data\anomalies_v1.geojson --schema contract\anomaly.schema.json
"""
import argparse
import json
import sys
from pathlib import Path

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[1]
ANOMALY_SCHEMA = REPO_ROOT / "contract" / "anomaly.schema.json"
BRIEF_SCHEMA = REPO_ROOT / "contract" / "brief.schema.json"


def detect_schema(doc: dict) -> Path:
    if doc.get("type") == "FeatureCollection":
        return ANOMALY_SCHEMA
    if "citations" in doc:
        return BRIEF_SCHEMA
    raise SystemExit("Could not auto-detect schema: expected a FeatureCollection or a brief "
                      "(top-level 'citations' key). Pass --schema explicitly.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("data_file")
    parser.add_argument("--schema", default=None, help="Override auto-detected schema path")
    args = parser.parse_args()

    data_path = Path(args.data_file)
    if not data_path.is_file():
        print(f"FAIL: file not found: {data_path}")
        sys.exit(1)

    with open(data_path, encoding="utf-8") as f:
        doc = json.load(f)

    schema_path = Path(args.schema) if args.schema else detect_schema(doc)
    print(f"Validating {data_path} against {schema_path.relative_to(REPO_ROOT)} ...")

    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)

    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))

    if not errors:
        print("PASS: no schema violations.")
        sys.exit(0)

    print(f"FAIL: {len(errors)} schema violation(s):")
    for err in errors:
        where = "/".join(str(p) for p in err.absolute_path) or "(root)"
        print(f"  - {where}: {err.message}")
    sys.exit(1)


if __name__ == "__main__":
    main()
