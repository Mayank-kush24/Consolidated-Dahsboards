"""
Placeholder CDI hub page — opened from the main app via st.switch_page.
Replace this file with your real CDI dashboard flow or external redirect logic.
"""

import os
from pathlib import Path

import streamlit as st

_FAVICON = Path(__file__).resolve().parent.parent / "static" / "favicon.png"
_PAGE_ICON = str(_FAVICON) if _FAVICON.is_file() else "🏠"
st.set_page_config(page_title="CDI Dashboard", page_icon=_PAGE_ICON, layout="centered")

if not st.session_state.get("authenticated", False):
    st.switch_page("app.py")

portal = (
    os.environ.get("H2S_CDI_PUBLIC_URL")
    or os.environ.get("JARVIS_PUBLIC_URL")
    or os.environ.get("H2S_CDI_URL")
    or os.environ.get("JARVIS_URL")
    or "http://h2s.tech"
).rstrip("/")

st.markdown("### CDI dashboard")
st.caption("Stub page — edit `pages/cdi_dashboard.py` or change `CDI_NAV_TARGET_PAGE` in `app.py`.")
st.link_button("Open CDI portal in browser", portal, use_container_width=True)
if st.button("Back to Event Analytics", use_container_width=True):
    st.switch_page("app.py")
