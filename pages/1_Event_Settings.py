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

st.set_page_config(page_title="Event Settings", page_icon="⚙️", layout="wide")

if not st.session_state.get("authenticated", False):
    st.switch_page("app.py")

if "editing_event" not in st.session_state:
    st.session_state.editing_event = None

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif !important; }
    #MainMenu, footer, header { visibility: hidden; }
    .settings-card {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 14px;
        padding: 1.5rem;
        margin-bottom: 1rem;
        transition: border-color 0.2s;
    }
    .settings-card:hover { border-color: #475569; }
    .settings-card h3 { margin: 0 0 0.75rem 0; font-size: 1.05rem; font-weight: 600; color: #e2e8f0; }
    .settings-field {
        display: flex; align-items: center; gap: 0.5rem;
        padding: 0.35rem 0; font-size: 0.82rem; color: #94a3b8;
    }
    .settings-field .field-label { font-weight: 500; color: #cbd5e1; min-width: 90px; }
    .section-header {
        display: flex; align-items: center; gap: 0.6rem;
        margin: 1rem 0 1rem 0; padding-bottom: 0.5rem; border-bottom: 2px solid #334155;
    }
    .section-header h2 { margin: 0; font-size: 1.3rem; font-weight: 700; color: #e2e8f0; }
</style>
""", unsafe_allow_html=True)

if st.sidebar.button("Back to Dashboard", use_container_width=True, icon=":material/arrow_back:"):
    st.switch_page("app.py")

st.markdown(
    '<div class="section-header"><span>⚙️</span><h2>Event Settings</h2></div>',
    unsafe_allow_html=True,
)
st.caption("Configure dedicated dashboard links, admin credentials, and registration targets for each event.")

df = st.session_state.get("df_raw")
if df is None or df.empty:
    st.info("Load events from the sheet first.")
    if st.button("Load events", type="primary"):
        sheet_id = extract_sheet_id(DEFAULT_SHEET_URL)
        if sheet_id:
            with st.spinner("Loading..."):
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

    st.markdown(f'<div class="settings-card"><h3>{initiative_name}</h3>', unsafe_allow_html=True)

    if is_editing:
        link = st.text_input("Dashboard link", value=entry["dashboard_link"], key=f"link_{safe_key}", placeholder="https://...")
        username = st.text_input("Admin username", value=entry["admin_username"], key=f"user_{safe_key}")
        password = st.text_input("Admin password", value=entry["admin_password"], type="password", key=f"pass_{safe_key}")
        reg_target = entry.get("registration_target") or 0
        registration_target = st.number_input("Registration target", min_value=0, value=int(reg_target) if reg_target else 0, key=f"regtarget_{safe_key}")
        c1, c2, _ = st.columns([1, 1, 3])
        with c1:
            if st.button("Save", key=f"save_{safe_key}", type="primary", use_container_width=True):
                config[initiative_name] = {
                    "dashboard_link": (link or "").strip(),
                    "admin_username": (username or "").strip(),
                    "admin_password": password or "",
                    "registration_target": registration_target,
                }
                save_event_dashboard_config(config)
                st.session_state.editing_event = None
                st.rerun()
        with c2:
            if st.button("Cancel", key=f"cancel_{safe_key}", use_container_width=True):
                st.session_state.editing_event = None
                st.rerun()
    else:
        has_link = bool(entry["dashboard_link"])
        has_user = bool(entry["admin_username"])
        has_pass = bool(entry["admin_password"])
        rt = entry.get("registration_target") or 0
        link_url = entry["dashboard_link"]
        link_display = link_url[:55] + "..." if has_link and len(link_url) > 55 else link_url
        link_html = f'<a href="{link_url}" target="_blank" style="color:#818cf8">{link_display}</a>' if has_link else "Not set"
        user_html = entry["admin_username"] if has_user else "—"
        pass_html = "••••••••" if has_pass else "—"
        target_html = f"{rt:,}" if rt else "Not set"

        st.markdown(
            f'<div class="settings-field"><span class="field-label">Link</span><span>{link_html}</span></div>'
            f'<div class="settings-field"><span class="field-label">Username</span><span>{user_html}</span></div>'
            f'<div class="settings-field"><span class="field-label">Password</span><span>{pass_html}</span></div>'
            f'<div class="settings-field"><span class="field-label">Reg. target</span><span>{target_html}</span></div>',
            unsafe_allow_html=True,
        )
        if st.button("Edit", key=f"edit_{safe_key}"):
            st.session_state.editing_event = initiative_name
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)
