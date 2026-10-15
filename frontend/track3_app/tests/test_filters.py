from datetime import date

from core import loader
from core.filters import FilterState, date_bounds, filter_anomalies, review_count, strongest, total_area


def _col(fixture_dir):
    return loader.load_anomalies(fixture_dir)


def test_default_filter_hides_low(fixture_dir):
    col = _col(fixture_dir)
    f = FilterState(sites=("SITE_A", "SITE_B", "SITE_C"), tiers=("high", "medium"), date_from=None, date_to=None)
    out = filter_anomalies(col.anomalies, f)
    assert len(out) == 8 and all(a.properties.confidence_tier != "low" for a in out)


def test_site_and_date_filters(fixture_dir):
    col = _col(fixture_dir)
    f = FilterState(sites=("SITE_A",), tiers=("high", "medium", "low"),
                    date_from=date(2025, 1, 1), date_to=date(2025, 6, 30))
    out = filter_anomalies(col.anomalies, f)
    assert {a.id for a in out} == {"DB-0001", "DB-0003"}


def test_bounds_area_review(fixture_dir):
    col = _col(fixture_dir)
    lo, hi = date_bounds(col.anomalies)
    assert lo <= hi
    assert round(total_area(col.anomalies), 2) == round(sum(a.properties.area_ha for a in col.anomalies), 2)
    briefs = {a.id: loader.load_brief_safe(fixture_dir, a.id) for a in col.anomalies}
    assert review_count(col.anomalies, briefs) == 3   # 2 abstained + 1 error; missing brief not counted


def test_strongest_three_are_high_tier(fixture_dir):
    top = strongest(_col(fixture_dir).anomalies, 3)
    assert len(top) == 3 and all(a.properties.confidence_tier == "high" for a in top)
