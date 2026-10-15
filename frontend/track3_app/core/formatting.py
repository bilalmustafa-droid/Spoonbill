"""Number and date formatting. Every function renders None as the localised "not available" text."""

from __future__ import annotations

from datetime import datetime, timezone

from .i18n import t


def _na(lang: str) -> str:
    return t("na", lang)


def fmt_area(value: float | None, lang: str = "en") -> str:
    """1.4234 -> '1.42 ha' / '1.42 公頃'."""
    return _na(lang) if value is None else f"{value:.2f} {t('ha', lang)}"


def fmt_db(value: float | None, lang: str = "en") -> str:
    """dB to 1 decimal with an explicit sign: 5.9 -> '+5.9 dB', -19.8 -> '-19.8 dB'."""
    return _na(lang) if value is None else f"{value:+.1f} dB"


def fmt_ndwi(value: float | None, lang: str = "en", signed: bool = False) -> str:
    """NDWI to 2 decimals. signed=True for deltas: -0.35 -> '-0.35', 0.2 -> '+0.20'."""
    if value is None:
        return _na(lang)
    return f"{value:+.2f}" if signed else f"{value:.2f}"


def fmt_date(value: str | None, lang: str = "en") -> str:
    """Validates and returns YYYY-MM-DD; raises ValueError on a malformed date (fail loudly)."""
    if not value:
        return _na(lang)
    return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%Y-%m-%d")


def fmt_timestamp(value: str | None, lang: str = "en") -> str:
    """'2026-10-12T04:00:00Z' -> '2026-10-12 04:00 UTC'."""
    if not value:
        return _na(lang)
    dt = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def fmt_coords(lon: float | None, lat: float | None, lang: str = "en") -> str:
    if lon is None or lat is None:
        return _na(lang)
    return f"{lon:.5f}, {lat:.5f}"


def delta_label(value: float | None, kind: str, lang: str = "en") -> str:
    """kind 'db' or 'ndwi'. 5.9, 'db' -> '+5.9 dB vs baseline' / '較基線 +5.9 dB'."""
    if value is None:
        return _na(lang)
    number = fmt_db(value, lang) if kind == "db" else fmt_ndwi(value, lang, signed=True)
    return t("vs_baseline", lang, value=number)


def persistence_label(count: int | None, total: int | None, lang: str = "en") -> str:
    if count is None or total is None:
        return _na(lang)
    return t("persistence_value", lang, count=count, total=total)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
