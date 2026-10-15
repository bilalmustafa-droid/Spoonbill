"""Pydantic v2 models mirroring contract v1.0 exactly. Optional fields are genuinely optional.

Unknown extra fields are ignored (the contract allows new optional fields); the UI only ever renders
fields declared here, so unexpected upstream free text is never shown.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Tier = Literal["high", "medium", "low"]
Zone = Literal["WCA", "WBA", "OTHER", "UNKNOWN"]
SiteId = Literal["SITE_A", "SITE_B", "SITE_C"]
Status = Literal["cited", "abstained_human_review", "error"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class Timeseries(_Frozen):
    months: list[str]
    vv_db: list[float]
    ndwi: list[float]

    @model_validator(mode="after")
    def _equal_lengths(self) -> "Timeseries":
        if not (len(self.months) == len(self.vv_db) == len(self.ndwi)):
            raise ValueError(
                f"timeseries arrays differ in length: months={len(self.months)}, "
                f"vv_db={len(self.vv_db)}, ndwi={len(self.ndwi)}"
            )
        return self


class Thresholds(_Frozen):
    delta_vv_db: float
    delta_ndwi: float
    despeckle: str
    persistence_rule: str
    min_area_ha: float


class Metadata(_Frozen):
    schema_version: str
    generated_at: str
    aoi_name: str
    baseline_window: tuple[str, str]
    current_window: tuple[str, str]
    sensors: list[str]
    thresholds: Thresholds
    anomaly_count: int


class AnomalyProperties(_Frozen):
    anomaly_id: str
    site_id: SiteId
    centroid_lon: float
    centroid_lat: float
    area_ha: float
    baseline_vv_db: float
    current_vv_db: float
    delta_vv_db: float
    baseline_ndwi: float
    current_ndwi: float
    delta_ndwi: float
    first_detection_date: str
    persistence_count: int
    persistence_total: int
    confidence_tier: Tier
    zone_hint: Zone
    optical_available: bool
    chip_before_png: str | None
    chip_after_png: str | None
    timeseries: Timeseries | None = None
    optical_brightness_flag: bool | None = None


class Anomaly(_Frozen):
    geometry: dict[str, Any]     # GeoJSON Polygon or MultiPolygon, EPSG:4326 (validated in loader)
    properties: AnomalyProperties

    @property
    def id(self) -> str:
        return self.properties.anomaly_id


class AnomalyCollection(_Frozen):
    metadata: Metadata
    anomalies: list[Anomaly]
    # Non-fatal consistency findings (for example a delta that does not equal current - baseline).
    warnings: list[str] = Field(default_factory=list)

    def by_id(self, anomaly_id: str) -> Anomaly | None:
        return next((a for a in self.anomalies if a.id == anomaly_id), None)


class Claim(_Frozen):
    claim: str
    citation_ids: list[str]


class LanguageBlock(_Frozen):
    title: str
    summary: str
    evidence: list[str]
    statutory_basis: list[Claim]
    recommended_action: str
    limitations: str


class Citation(_Frozen):
    id: str
    doc: str
    doc_title_zh: str
    page: int
    section: str
    quote: str
    source_url: str | None


class RedactionLog(_Frozen):
    items_removed: int
    types: list[str]


class BriefMetrics(_Frozen):
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class Brief(_Frozen):
    schema_version: str
    anomaly_id: str
    status: Status
    model: str
    generated_at: str
    en: LanguageBlock
    zh_hant: LanguageBlock
    citations: list[Citation]
    human_review_required: bool
    abstain_reason: str | None
    redaction_log: RedactionLog
    metrics: BriefMetrics | None = None

    def block(self, lang: str) -> LanguageBlock:
        return self.zh_hant if lang == "zh_hant" else self.en
