"""Folium map with tier-styled anomaly polygons, click-to-select and a colour-independent legend.

Flicker and re-zoom avoidance: the base map (tiles + fit bounds) is identical on every run, so
streamlit-folium never remounts it. Anomaly polygons and the selection outline are passed through
`feature_group_to_add`, which updates layers in place. Bounds are computed once, from the filtered
set on first load, and stored in session state.
"""

from __future__ import annotations

import folium
import streamlit as st
from shapely.geometry import Point, shape

from core.config import SELECTED_OUTLINE, TIER_STYLE
from core.formatting import fmt_area
from core.i18n import t
from core.models import Anomaly

from . import state
from .styles import esc

MAP_KEY = "anomaly_map"
MAP_HEIGHT = 560
_CLICK_TOLERANCE_DEG = 0.00005  # about 5 m, so clicks on a polygon edge still select it

ESRI_TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
ESRI_ATTR = "Tiles &copy; Esri, Maxar, Earthstar Geographics, and the GIS User Community"


def _bounds_of(anomalies: list[Anomaly], geoms: dict[str, dict]) -> list[list[float]]:
    xs0, ys0, xs1, ys1 = zip(*(shape(geoms[a.id]).bounds for a in anomalies))
    pad = 0.002
    return [[min(ys0) - pad, min(xs0) - pad], [max(ys1) + pad, max(xs1) + pad]]


def _base_map(bounds: list[list[float]]) -> folium.Map:
    center = [(bounds[0][0] + bounds[1][0]) / 2, (bounds[0][1] + bounds[1][1]) / 2]
    # keyboard=False: Leaflet's keyboard handler focuses the map on mousedown, and the browser then scrolls
    # the page to show the whole map. When the map extends below the fold the page jumps mid-click, the
    # mouseup lands below the polygon and the selection is missed. The anomaly list stays keyboard-accessible.
    m = folium.Map(location=center, zoom_start=14, tiles=None, control_scale=True, prefer_canvas=False,
                   keyboard=False)
    # Only Leaflet itself is needed (no markers/icons); dropping jQuery, Bootstrap and Font Awesome
    # removes six CDN requests from every map load.
    m.default_js = [js for js in folium.Map.default_js if js[0] == "leaflet"]
    m.default_css = [css for css in folium.Map.default_css if css[0] == "leaflet_css"]
    folium.TileLayer(tiles=ESRI_TILES, attr=ESRI_ATTR, name="Esri World Imagery", max_zoom=19).add_to(m)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap", show=False).add_to(m)
    m.fit_bounds(bounds)
    return m


def _style(feature: dict) -> dict:
    s = TIER_STYLE[feature["properties"]["tier"]]
    return {"color": s["color"], "weight": s["weight"], "dashArray": s["dash"],
            "fillColor": s["color"], "fillOpacity": 0.28, "opacity": 1.0}


def _highlight(feature: dict) -> dict:
    return {"weight": 5, "fillOpacity": 0.45}


def _selected_style(_feature: dict) -> dict:
    return {"color": SELECTED_OUTLINE, "weight": 5, "fillOpacity": 0.0, "dashArray": None}


def _feature(a: Anomaly, geom: dict, lang: str) -> dict:
    p = a.properties
    style = TIER_STYLE[p.confidence_tier]
    return {
        "type": "Feature",
        "geometry": geom,
        "properties": {
            "anomaly_id": a.id,
            "tier": p.confidence_tier,
            "tt_id": a.id,
            "tt_tier": f"{style['glyph']} {t(f'tier_{p.confidence_tier}', lang)}",
            "tt_area": fmt_area(p.area_ha, lang),
            "tt_zone": t(f"zone_{p.zone_hint}", lang),
        },
    }


def _anomaly_layer(anomalies: list[Anomaly], geoms: dict[str, dict], selected_id: str | None,
                   lang: str) -> folium.FeatureGroup:
    fg = folium.FeatureGroup(name=t("m_count", lang))
    if not anomalies:
        return fg  # GeoJsonTooltip refuses an empty FeatureCollection
    data = {"type": "FeatureCollection", "features": [_feature(a, geoms[a.id], lang) for a in anomalies]}
    folium.GeoJson(
        data,
        style_function=_style,
        highlight_function=_highlight,
        tooltip=folium.GeoJsonTooltip(
            fields=["tt_id", "tt_tier", "tt_area", "tt_zone"],
            aliases=[t("tt_id", lang), t("tt_tier", lang), t("tt_area", lang), t("tt_zone", lang)],
            sticky=True,
        ),
    ).add_to(fg)
    if selected_id and selected_id in geoms and any(a.id == selected_id for a in anomalies):
        folium.GeoJson({"type": "Feature", "geometry": geoms[selected_id], "properties": {}},
                       style_function=_selected_style, interactive=False).add_to(fg)
    return fg


def anomaly_at(lat: float, lng: float, anomalies: list[Anomaly], geoms: dict[str, dict]) -> str | None:
    """Return the anomaly under a click; smallest polygon wins when several overlap."""
    pt = Point(lng, lat)
    hits = [(shape(geoms[a.id]).area, a.id) for a in anomalies
            if shape(geoms[a.id]).buffer(_CLICK_TOLERANCE_DEG).contains(pt)]
    return min(hits)[1] if hits else None


def _make_click_handler(anomalies: list[Anomaly], geoms: dict[str, dict]):
    def on_map_change() -> None:
        value = st.session_state.get(MAP_KEY) or {}
        # "last_clicked" (any map click) rather than "last_object_clicked": Leaflet's drag handler can
        # retarget mouseup to the map container, so the layer-level click is unreliable. The point-in-
        # polygon lookup below decides which anomaly was hit.
        click = value.get("last_clicked") or value.get("last_object_clicked")
        if not click:
            return
        sig = (round(click["lat"], 7), round(click["lng"], 7))
        if sig == st.session_state.get(state.MAP_CLICK_SIG):
            return
        st.session_state[state.MAP_CLICK_SIG] = sig
        hit = anomaly_at(click["lat"], click["lng"], anomalies, geoms)
        if hit:
            state.select_anomaly(hit)
    return on_map_change


def render(anomalies: list[Anomaly], geoms: dict[str, dict], selected_id: str | None, lang: str) -> None:
    if state.MAP_BOUNDS not in st.session_state and anomalies:
        st.session_state[state.MAP_BOUNDS] = _bounds_of(anomalies, geoms)
    bounds = st.session_state.get(state.MAP_BOUNDS) or [[22.45, 113.98], [22.54, 114.12]]

    base = _base_map(bounds)
    try:
        from streamlit_folium import st_folium
        st_folium(
            base,
            key=MAP_KEY,
            height=MAP_HEIGHT,
            use_container_width=True,
            returned_objects=["last_clicked", "last_object_clicked"],
            feature_group_to_add=_anomaly_layer(anomalies, geoms, selected_id, lang),
            layer_control=folium.LayerControl(collapsed=True),
            on_change=_make_click_handler(anomalies, geoms),
        )
    except Exception as exc:  # the detail panel and list selection keep working without the map
        st.warning(f"Map could not be drawn: {exc}")
    legend(lang)


def legend(lang: str) -> None:
    lines = {"high": "legend_line_solid", "medium": "legend_line_dashed", "low": "legend_line_dotted"}
    rows = []
    for tier, s in TIER_STYLE.items():
        dash = f'stroke-dasharray="{s["dash"]}"' if s["dash"] else ""
        swatch = (f'<svg width="34" height="14" aria-hidden="true"><rect x="2" y="2" width="30" height="10" '
                  f'fill="{s["color"]}" fill-opacity="0.35" stroke="{s["color"]}" stroke-width="2.5" {dash}/></svg>')
        rows.append(f'<div>{swatch} <b>{s["glyph"]} {esc(t(f"tier_{tier}", lang))}</b> '
                    f'· {esc(t(lines[tier], lang))}</div>')
    rows.append(f'<div><svg width="34" height="14" aria-hidden="true"><rect x="2" y="2" width="30" height="10" '
                f'fill="none" stroke="{SELECTED_OUTLINE}" stroke-width="3"/></svg> {esc(t("legend_selected", lang))}</div>')
    st.markdown(f'<div class="sb-legend"><b>{esc(t("legend", lang))}</b>{"".join(rows)}</div>',
                unsafe_allow_html=True)
    st.caption(t("tiles_note", lang))
