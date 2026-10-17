"""Small CSS layer for badges and status panels. Contrast checked for readability on light backgrounds."""

from __future__ import annotations

import html

import streamlit as st

from core.config import TIER_STYLE
from core.i18n import t

_CSS = """
<style>
.sb-banner {background:#7A1F1F;color:#fff;padding:.55rem .9rem;border-radius:.4rem;font-weight:700;
            letter-spacing:.02em;margin-bottom:.6rem;border-left:6px solid #FFB000;}
.sb-badge {display:inline-block;padding:.15rem .6rem;border-radius:1rem;font-weight:600;font-size:.9rem;
           margin-right:.35rem;border:2px solid transparent;}
.sb-chip {display:inline-block;padding:.1rem .55rem;border-radius:.3rem;font-size:.85rem;font-weight:600;
          background:#E7F0FF;color:#123B7A;border:1px solid #9DB8E8;margin-right:.35rem;}
.sb-meter {font-family:monospace;font-size:1.05rem;letter-spacing:.12em;}
.sb-panel-amber {background:#FFF4D6;border:1px solid #E0A800;border-left:6px solid #E0A800;
                 padding:.8rem 1rem;border-radius:.4rem;color:#3D2E00;margin:.4rem 0 .8rem 0;}
.sb-panel-amber h4 {margin:0 0 .3rem 0;color:#3D2E00;}
.sb-panel-grey {background:#F1F3F5;border:1px solid #CED4DA;border-left:6px solid #868E96;
                padding:.8rem 1rem;border-radius:.4rem;color:#343A40;margin:.4rem 0 .8rem 0;}
.sb-missing-cite {display:inline-block;background:#FFE3E3;color:#7A1F1F;border:1px dashed #C92A2A;
                  border-radius:.3rem;padding:.05rem .45rem;font-size:.85rem;font-weight:600;}
.sb-chip-placeholder {aspect-ratio:1/1;width:100%;display:flex;align-items:center;justify-content:center;
                      background:repeating-linear-gradient(45deg,#E9ECEF,#E9ECEF 10px,#F8F9FA 10px,#F8F9FA 20px);
                      border:1px dashed #ADB5BD;border-radius:.3rem;color:#495057;font-weight:600;text-align:center;}
.sb-legend span.sw {display:inline-block;width:34px;height:14px;vertical-align:middle;margin-right:.3rem;}
.sb-legend div {margin:.15rem 0;font-size:.9rem;}
/* Keep the map in view while the detail column scrolls (wide layouts only; columns stack on mobile). */
/* The keyed container sits in a same-height layout wrapper, so the wrapper is what must stick. */
div[data-testid="stColumn"]:has(.st-key-map_col) {align-self: stretch;}
div[data-testid="stLayoutWrapper"]:has(> .st-key-map_col) {position: sticky; top: 3.75rem; z-index: 1;}
.sb-footer {font-size:.88rem;color:#495057;border-top:1px solid #DEE2E6;padding-top:.6rem;margin-top:1.2rem;}
.sb-disclaimer {font-weight:600;color:#212529;background:#F8F9FA;border:1px solid #DEE2E6;padding:.6rem .8rem;
                border-radius:.3rem;margin-top:.4rem;}
/* st.metric() clips its value to one line by default; dates like 2025-06-10 get cut off in a
   narrow column. Let it wrap instead of clipping, and drop the size slightly so it still fits. */
div[data-testid="stMetricValue"] {white-space: normal; overflow-wrap: break-word; font-size: 1.3rem;}
</style>
"""


def inject() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def tier_badge_html(tier: str, lang: str) -> str:
    style = TIER_STYLE[tier]
    label = t("tier_badge", lang, tier=t(f"tier_{tier}", lang))
    # Dark text on every tier colour keeps contrast above 4.5:1.
    return (f'<span class="sb-badge" style="background:{style["color"]};color:#141414;">'
            f'{style["glyph"]} {esc(label)}</span>')


def persistence_meter_html(count: int, total: int) -> str:
    return f'<span class="sb-meter">{"■" * count}{"□" * max(total - count, 0)}</span>'
