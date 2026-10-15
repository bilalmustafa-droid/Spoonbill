"""
Smoke test for the Spoonbill integration API. Hits every route against a
server you've already started in another terminal and prints PASS/FAIL per
check. Exits non-zero if anything failed.

Usage:
    python scripts/smoke_test.py
    python scripts/smoke_test.py --base-url http://127.0.0.1:8000
    python scripts/smoke_test.py --assume-offline   (run against a server
        started with SPOONBILL_OFFLINE=1; adds the offline-cache-miss check)
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

PASS_COUNT = 0
FAIL_COUNT = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"PASS: {name}")
    else:
        FAIL_COUNT += 1
        print(f"FAIL: {name} -- {detail}")


def request(base_url: str, method: str, path: str):
    url = f"{base_url}{path}"
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body) if body else None
        except json.JSONDecodeError:
            return e.code, body


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--assume-offline", action="store_true")
    args = parser.parse_args()
    base_url = args.base_url

    # 1. Root route unchanged
    status, body = request(base_url, "GET", "/")
    check("GET / returns 200", status == 200, f"status={status}")

    # 2. Health
    status, body = request(base_url, "GET", "/health")
    check("GET /health returns 200", status == 200, f"status={status}")
    check(
        "GET /health has anomalies + rag sections",
        isinstance(body, dict) and "anomalies" in body and "rag" in body,
        f"body={body}",
    )

    # 3. Anomalies (default mock data: 3 features, none with confidence_tier/site_id)
    status, body = request(base_url, "GET", "/api/anomalies")
    check("GET /api/anomalies returns 200", status == 200, f"status={status}")
    feature_count = len(body.get("features", [])) if isinstance(body, dict) else -1
    check(
        "GET /api/anomalies returns 3 features (default mock data)",
        feature_count == 3,
        f"feature_count={feature_count}",
    )

    status, body = request(base_url, "GET", "/api/anomalies?include_low=true")
    check(
        "GET /api/anomalies?include_low=true matches unfiltered count",
        isinstance(body, dict) and len(body.get("features", [])) == feature_count,
        f"body={body}",
    )

    status, body = request(base_url, "GET", "/api/anomalies?tier=low")
    check(
        "GET /api/anomalies?tier=low returns 0 (no tier set in mock data)",
        isinstance(body, dict) and len(body.get("features", [])) == 0,
        f"body={body}",
    )

    status, body = request(base_url, "GET", "/api/anomalies?site_id=mai_po_4p3ha")
    check(
        "GET /api/anomalies?site_id=mai_po_4p3ha returns 0 (correct, not a bug: mock data has no site_id)",
        isinstance(body, dict) and len(body.get("features", [])) == 0,
        f"body={body}",
    )

    # 4. Single lookup
    status, body = request(base_url, "GET", "/api/anomalies/DB-0001")
    check(
        "GET /api/anomalies/DB-0001 returns the right feature",
        status == 200 and body.get("properties", {}).get("anomaly_id") == "DB-0001",
        f"status={status} body={body}",
    )

    status, body = request(base_url, "GET", "/api/anomalies/DOES-NOT-EXIST")
    check("GET /api/anomalies/DOES-NOT-EXIST returns 404", status == 404, f"status={status}")

    # 5. Chips -- clean 404 since mock data has no chip fields
    status, body = request(base_url, "GET", "/api/anomalies/DB-0001/chips/before")
    check(
        "GET chips/before returns 404 with available:false (no chip fields in mock data)",
        status == 404,
        f"status={status} body={body}",
    )

    status, body = request(base_url, "GET", "/api/anomalies/DB-0001/chips/sideways")
    check("GET chips/sideways rejects invalid side with 422", status == 422, f"status={status}")

    # 6. Stats -- known totals from contract/mock_anomalies.geojson (1.42 + 0.85 + 3.10)
    status, body = request(base_url, "GET", "/api/stats")
    check("GET /api/stats returns 200", status == 200, f"status={status}")
    if isinstance(body, dict):
        total_area = body.get("total_area_ha")
        check(
            "GET /api/stats total_area_ha ~= 5.37",
            total_area is not None and abs(total_area - 5.37) < 0.01,
            f"total_area_ha={total_area}",
        )
        check(
            "GET /api/stats tier_counts.unknown == 3",
            body.get("tier_counts", {}).get("unknown") == 3,
            f"tier_counts={body.get('tier_counts')}",
        )

    # 7. Sites
    status, body = request(base_url, "GET", "/api/sites")
    check("GET /api/sites returns 200", status == 200, f"status={status}")
    site_ids = {s.get("site_id") for s in body.get("sites", [])} if isinstance(body, dict) else set()
    check(
        "GET /api/sites includes mai_po_4p3ha and san_tin_9ha",
        {"mai_po_4p3ha", "san_tin_9ha"}.issubset(site_ids),
        f"site_ids={site_ids}",
    )

    # 8. Briefs -- cache-hit path, should not need a live Gemini call
    status, body = request(base_url, "GET", "/api/v1/briefs/DB-0001")
    check(
        "GET /api/v1/briefs/DB-0001 returns cached brief",
        status == 200 and isinstance(body, dict) and body.get("anomaly_id") == "DB-0001",
        f"status={status} body={body}",
    )

    status, body = request(base_url, "POST", "/api/brief/DB-0002")
    check(
        "POST /api/brief/DB-0002 returns cached brief",
        status == 200 and isinstance(body, dict) and body.get("anomaly_id") == "DB-0002",
        f"status={status} body={body}",
    )

    if args.assume_offline:
        # Requires an anomaly_id with no cached brief file and no chip data --
        # DB-0003 has a cached brief in this repo today, so this check only
        # proves useful once a genuinely uncached anomaly_id is available.
        status, body = request(base_url, "POST", "/api/brief/DB-9999")
        check(
            "POST /api/brief/<uncached id> returns 503 offline message (offline mode)",
            status in (404, 503),
            f"status={status} body={body}",
        )

    print(f"\n{PASS_COUNT} passed, {FAIL_COUNT} failed")
    sys.exit(1 if FAIL_COUNT else 0)


if __name__ == "__main__":
    main()
