"""Session-state keys and the "persistent widget" pattern.

Canonical values live under store keys (lang, f_sites, ...). Each run copies the stored value into the
widget key before the widget is drawn, and an on_change callback copies it back.

Widgets whose option labels are translated get one widget key per language (variant=lang): the browser
identifies multiselect/selectbox values by their displayed label, so reusing one widget across a language
switch would silently drop the selection. A fresh per-language widget is primed from the canonical store.
"""

from __future__ import annotations

import streamlit as st

LANG = "lang"
SITES = "f_sites"
TIERS = "f_tiers"
SHOW_LOW = "f_show_low"
DATES = "f_dates"
SELECTED = "selected_id"
MAP_CLICK_SIG = "map_click_sig"
MAP_BOUNDS = "map_bounds"
DEMO_STEP = "demo_step"
LOGGED_ISSUES = "logged_issues"

DEFAULT_TIERS = ["high", "medium"]
_MISSING = object()


def init_defaults(lang: str = "en") -> None:
    st.session_state.setdefault(LANG, lang)
    st.session_state.setdefault(TIERS, list(DEFAULT_TIERS))
    st.session_state.setdefault(SHOW_LOW, False)
    st.session_state.setdefault(SELECTED, None)
    st.session_state.setdefault(MAP_CLICK_SIG, None)
    st.session_state.setdefault(DEMO_STEP, 0)
    st.session_state.setdefault(LOGGED_ISSUES, set())


def widget_key(store_key: str, variant: str = "") -> str:
    return f"w_{store_key}_{variant}" if variant else f"w_{store_key}"


def prime_widget(store_key: str, variant: str = "") -> str:
    """Copy the stored value into the widget key; returns the widget key to pass to the widget."""
    wk = widget_key(store_key, variant)
    # Only write when the stored value changed outside the widget (reset, demo step, language switch),
    # so normal interaction never sets widget state through the Session State API.
    if store_key in st.session_state and st.session_state.get(wk, _MISSING) != st.session_state[store_key]:
        st.session_state[wk] = st.session_state[store_key]
    return wk


def sync_from_widget(store_key: str, variant: str = "") -> None:
    st.session_state[store_key] = st.session_state[widget_key(store_key, variant)]


def select_anomaly(anomaly_id: str | None) -> None:
    st.session_state[SELECTED] = anomaly_id
