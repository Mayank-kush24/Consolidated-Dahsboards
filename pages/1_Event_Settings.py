"""
Event settings: list all events and configure dedicated dashboard link and admin credentials per event.
"""

import streamlit as st
from config_helpers import (
    DEFAULT_CREDENTIALS_PATH,
    DEFAULT_SHEET_URL,
    load_event_dashboard_config,
    save_event_dashboard_config,
    get_event_config,
)
from sheets_connector import load_sheet_data
from utils import extract_sheet_id

st.set_page_config(page_title="Event settings", page_icon="⚙️", layout="wide")

# Auth: redirect to home if not logged in (home shows login)
if not st.session_state.get("authenticated", False):
    st.switch_page("app.py")

# Session state for which event is being edited
if "editing_event" not in st.session_state:
    st.session_state.editing_event = None

if st.sidebar.button("← Back to Dashboard", use_container_width=True):
    st.switch_page("app.py")
st.title("Event settings")
st.markdown("Configure dedicated dashboard link and admin credentials for each event. After saving, use **Edit** to change.")

# Get initiative list: from session state or load sheet
df = st.session_state.get("df_raw")
if df is None or df.empty:
    st.info("Load events from the sheet first.")
    if st.button("Load events"):
        sheet_id = extract_sheet_id(DEFAULT_SHEET_URL)
        if sheet_id:
            with st.spinner("Loading sheet..."):
                df_loaded = load_sheet_data(sheet_id, DEFAULT_CREDENTIALS_PATH)
            if df_loaded is not None and not df_loaded.empty:
                st.session_state.df_raw = df_loaded
                st.rerun()
            else:
                st.error("Could not load sheet. Check credentials and sheet ID.")
        else:
            st.error("Invalid sheet URL.")
    st.stop()

col_name = "Initiative Name"
if col_name not in df.columns:
    st.warning("Column 'Initiative Name' not found in the sheet.")
    st.stop()

initiative_options = sorted(df[col_name].dropna().unique().tolist())
config = load_event_dashboard_config()

for i, initiative_name in enumerate(initiative_options):
    entry = get_event_config(config, initiative_name)
    is_editing = st.session_state.editing_event == initiative_name
    safe_key = f"ev_{i}"

    with st.container():
        st.subheader(initiative_name)
        if is_editing:
            link = st.text_input("Dashboard link", value=entry["dashboard_link"], key=f"link_{safe_key}", placeholder="https://...")
            username = st.text_input("Admin username", value=entry["admin_username"], key=f"user_{safe_key}")
            password = st.text_input("Admin password", value=entry["admin_password"], type="password", key=f"pass_{safe_key}")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Save", key=f"save_{safe_key}"):
                    config[initiative_name] = {
                        "dashboard_link": (link or "").strip(),
                        "admin_username": (username or "").strip(),
                        "admin_password": password or "",
                    }
                    save_event_dashboard_config(config)
                    st.session_state.editing_event = None
                    st.rerun()
            with c2:
                if st.button("Cancel", key=f"cancel_{safe_key}"):
                    st.session_state.editing_event = None
                    st.rerun()
        else:
            # View mode
            if entry["dashboard_link"]:
                display_text = entry["dashboard_link"] if len(entry["dashboard_link"]) <= 60 else entry["dashboard_link"][:60] + "..."
                st.markdown(f"**Link:** [{display_text}]({entry['dashboard_link']})")
            else:
                st.caption("Dashboard link: Not set")
            st.caption(f"**Username:** {entry['admin_username'] or '—'}")
            st.caption(f"**Password:** {'••••••' if entry['admin_password'] else '—'}")
            if st.button("Edit", key=f"edit_{safe_key}"):
                st.session_state.editing_event = initiative_name
                st.rerun()
        st.markdown("---")
