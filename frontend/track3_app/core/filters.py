"""Sorting, filtering and summary maths on anomalies. Pure functions, no Streamlit."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .config import TIER_RANK
from .loader import BriefLoad
from .models import Anomaly


@dataclass(frozen=True)
class FilterState:
    sites: tuple[str, ...]
    tiers: tuple[str, ...]
    date_from: date | None
    date_to: date | None


def sort_anomalies(anomalies: list[Anomaly]) -> list[Anomaly]:
    """Tier (high, medium, low) then area descending. The file is meant to be sorted, but we never rely on it."""
    return sorted(anomalies, key=lambda a: (TIER_RANK[a.properties.confidence_tier], -a.properties.area_ha, a.id))


def detection_date(a: Anomaly) -> date:
    return date.fromisoformat(a.properties.first_detection_date)


def date_bounds(anomalies: list[Anomaly]) -> tuple[date, date] | None:
    if not anomalies:
        return None
    dates = [detection_date(a) for a in anomalies]
    return min(dates), max(dates)


def filter_anomalies(anomalies: list[Anomaly], f: FilterState) -> list[Anomaly]:
    out = []
    for a in anomalies:
        p = a.properties
        if p.site_id not in f.sites or p.confidence_tier not in f.tiers:
            continue
        d = detection_date(a)
        if f.date_from and d < f.date_from:
            continue
        if f.date_to and d > f.date_to:
            continue
        out.append(a)
    return sort_anomalies(out)


def total_area(anomalies: list[Anomaly]) -> float:
    return sum(a.properties.area_ha for a in anomalies)


def review_count(anomalies: list[Anomaly], briefs: dict[str, BriefLoad]) -> int:
    """Anomalies whose brief exists and sets human_review_required. Pending/invalid briefs are not counted."""
    return sum(
        1 for a in anomalies
        if (b := briefs.get(a.id)) and b.state == "ok" and b.brief.human_review_required
    )


def strongest(anomalies: list[Anomaly], n: int = 3) -> list[Anomaly]:
    """Strongest detections for the demo path: tier, then persistence ratio, then area, then radar change."""
    def key(a: Anomaly):
        p = a.properties
        return (TIER_RANK[p.confidence_tier], -(p.persistence_count / p.persistence_total), -p.area_ha,
                -p.delta_vv_db, a.id)
    return sorted(anomalies, key=key)[:n]
