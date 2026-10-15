"""
Safe resolution of before/after chip PNGs referenced by an anomaly feature's
chip_before_png / chip_after_png properties.

Today's mock data has neither property, so every lookup correctly returns the
clean "not available" response below -- there is no hand-wired mapping from
anomaly IDs to the existing spatial/spoonbill_outputs_v2/ PNGs, since those
files are not actually linked to any anomaly_id and guessing a mapping would
be fabricating a detection-to-image linkage with no evidentiary basis.
"""
from pathlib import Path
from typing import Literal, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]

PROPERTY_BY_SIDE = {
    "before": "chip_before_png",
    "after": "chip_after_png",
}


class ChipNotAvailable(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def resolve_chip_path(feature: dict, side: Literal["before", "after"]) -> Path:
    """Returns an absolute Path to the chip PNG, or raises ChipNotAvailable.

    Never returns a path outside the repo root and never returns a non-.png
    path, regardless of what the GeoJSON property contains.
    """
    prop_key = PROPERTY_BY_SIDE[side]
    raw_value: Optional[str] = feature.get("properties", {}).get(prop_key)

    if not raw_value:
        raise ChipNotAvailable(f"no {prop_key} recorded for this anomaly")

    candidate = (REPO_ROOT / raw_value).resolve()

    if not candidate.is_relative_to(REPO_ROOT):
        raise ChipNotAvailable("chip path invalid")

    if candidate.suffix.lower() != ".png":
        raise ChipNotAvailable("chip path invalid")

    if not candidate.exists():
        raise ChipNotAvailable("referenced chip file missing on disk")

    return candidate
