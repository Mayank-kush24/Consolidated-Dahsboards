"""
Hackathon / Event Analytics Dashboard
Connects to Google Sheets and visualizes event statistics with Plotly.
"""

import json
import logging
import os
import sys
import streamlit as st
import pandas as pd

# Configure logging to terminal (visible when running streamlit run / python run.py)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,
    force=True,
)
logger = logging.getLogger(__name__)
logger.info("Event Analytics Dashboard starting")
import plotly.express as px
import plotly.graph_objects as go
from sheets_connector import load_sheet_data
from auth import verify_login, can_edit_sheet
from config_helpers import (
    DEFAULT_CREDENTIALS_PATH,
    DEFAULT_SHEET_URL,
    load_event_dashboard_config,
    save_event_dashboard_config,
    get_event_config,
)
from utils import (
    extract_sheet_id,
    safe_json_loads,
    merge_json_dicts,
    normalize_chart_label,
    parse_daily_registrations,
    daily_registrations_to_line_data,
    aggregate_numeric_columns,
    COL_DAILY_REG,
    COL_GENDER,
    COL_COUNTRY,
    COL_STATE,
    COL_CITY,
    COL_OCCUPATION,
    NUMERIC_KPI_COLUMNS,
)


def _find_column(df: pd.DataFrame, *keywords: str):
    """Return first column whose name contains all keywords (case-insensitive)."""
    if df is None or df.columns is None:
        return None
    lower_keywords = [k.lower() for k in keywords]
    for c in df.columns:
        name = str(c).strip().lower()
        if all(k in name for k in lower_keywords):
            return c
    return None

# Page config
st.set_page_config(
    page_title="Event Analytics Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for cleaner cards and layout
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);
        padding: 1.25rem;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        text-align: center;
        color: white;
        margin-bottom: 1rem;
    }
    .metric-card h3 {
        font-size: 0.85rem;
        font-weight: 600;
        opacity: 0.9;
        margin: 0 0 0.25rem 0;
    }
    .metric-card .value {
        font-size: 1.75rem;
        font-weight: 700;
    }
    .event-tile {
        display: inline-block;
        padding: 0.5rem 1rem;
        margin: 0.25rem;
        border-radius: 8px;
        border: 2px solid #2d5a87;
        background: #1e3a5f;
        color: white;
        cursor: pointer;
        font-size: 0.9rem;
        transition: all 0.2s;
    }
    .event-tile:hover { background: #2d5a87; border-color: #4a8bc2; }
    .event-tile.selected { background: #0d7d58; border-color: #0d7d58; }
    .event-tile.selected:hover { background: #0a6b4a; border-color: #0a6b4a; }
</style>
""", unsafe_allow_html=True)

# Persisted pinned hackathons (survives refresh / re-login)
PINNED_FILE = "pinned_initiatives.json"


def load_pinned_from_file():
    """Load pinned initiative names from JSON file. Returns list (empty if missing/invalid)."""
    try:
        if os.path.isfile(PINNED_FILE):
            with open(PINNED_FILE, encoding="utf-8") as f:
                data = json.load(f)
                return data.get("pinned", []) if isinstance(data, dict) else []
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save_pinned_to_file(pinned_list):
    """Write pinned initiative names to JSON file."""
    try:
        with open(PINNED_FILE, "w", encoding="utf-8") as f:
            json.dump({"pinned": list(pinned_list)}, f, indent=2)
    except OSError as e:
        logger.warning("Could not save pinned initiatives: %s", e)

# Persisted auth session (survives refresh)
AUTH_SESSION_FILE = "auth_session.json"


def load_auth_session():
    """Load saved user/role from file. Returns (user, role) or (None, None) if missing/invalid."""
    try:
        if os.path.isfile(AUTH_SESSION_FILE):
            with open(AUTH_SESSION_FILE, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data.get("user") and data.get("role"):
                    return (str(data["user"]).strip().lower(), str(data["role"]))
    except (json.JSONDecodeError, OSError):
        pass
    return (None, None)


def save_auth_session(user: str, role: str):
    """Write user and role to session file so login persists across refresh."""
    try:
        with open(AUTH_SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump({"user": user, "role": role}, f, indent=2)
    except OSError as e:
        logger.warning("Could not save auth session: %s", e)


def clear_auth_session():
    """Remove session file so next load shows login."""
    try:
        if os.path.isfile(AUTH_SESSION_FILE):
            os.remove(AUTH_SESSION_FILE)
    except OSError:
        pass


# Session state for auth (restore from file on refresh)
if "authenticated" not in st.session_state:
    saved_user, saved_role = load_auth_session()
    if saved_user and saved_role:
        st.session_state.authenticated = True
        st.session_state.user = saved_user
        st.session_state.role = saved_role
    else:
        st.session_state.authenticated = False
        st.session_state.user = None
        st.session_state.role = None
if "user" not in st.session_state:
    st.session_state.user = None
if "role" not in st.session_state:
    st.session_state.role = None

# Session state for sheet data and selection
if "df_raw" not in st.session_state:
    st.session_state.df_raw = None
if "sheet_id_input" not in st.session_state:
    st.session_state.sheet_id_input = DEFAULT_SHEET_URL
if "selected_initiatives" not in st.session_state:
    st.session_state.selected_initiatives = []
if "pinned_initiatives" not in st.session_state:
    st.session_state.pinned_initiatives = load_pinned_from_file()
if "current_page" not in st.session_state:
    st.session_state.current_page = "dashboard"


@st.cache_data(ttl=300)
def cached_load_sheet(sheet_id: str, credentials_path: str):
    """Load Google Sheet data with caching (5 min TTL)."""
    return load_sheet_data(sheet_id, credentials_path)


def render_event_settings_page():
    """Event settings: list events, configure dashboard link and admin credentials (no switch_page)."""
    if "editing_event" not in st.session_state:
        st.session_state.editing_event = None
    with st.sidebar:
        st.title("📊 Event Dashboard")
        if st.button("← Back to Dashboard", use_container_width=True):
            st.session_state.current_page = "dashboard"
            st.rerun()
        st.markdown("---")
        if st.button("Logout", use_container_width=True):
            clear_auth_session()
            st.session_state.authenticated = False
            st.session_state.user = None
            st.session_state.role = None
            st.session_state.current_page = "dashboard"
            st.rerun()
    st.title("Event settings")
    st.markdown("Configure dedicated dashboard link and admin credentials for each event. After saving, use **Edit** to change.")
    df = st.session_state.get("df_raw")
    if df is None or df.empty:
        st.info("Load events from the sheet first. Go back to the dashboard, connect to the sheet, then return here.")
        return
    col_name = "Initiative Name"
    if col_name not in df.columns:
        st.warning("Column 'Initiative Name' not found in the sheet.")
        return
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
                reg_target = entry.get("registration_target") or 0
                registration_target = st.number_input("Registration target", min_value=0, value=int(reg_target) if reg_target else 0, key=f"regtarget_{safe_key}")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Save", key=f"save_{safe_key}"):
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
                    if st.button("Cancel", key=f"cancel_{safe_key}"):
                        st.session_state.editing_event = None
                        st.rerun()
            else:
                if entry["dashboard_link"]:
                    display_text = entry["dashboard_link"] if len(entry["dashboard_link"]) <= 60 else entry["dashboard_link"][:60] + "..."
                    st.markdown(f"**Link:** [{display_text}]({entry['dashboard_link']})")
                else:
                    st.caption("Dashboard link: Not set")
                st.caption(f"**Username:** {entry['admin_username'] or '—'}")
                st.caption(f"**Password:** {'••••••' if entry['admin_password'] else '—'}")
                rt = entry.get("registration_target") or 0
                st.caption(f"**Registration target:** {rt if rt else 'Not set'}")
                if st.button("Edit", key=f"edit_{safe_key}"):
                    st.session_state.editing_event = initiative_name
                    st.rerun()
            st.markdown("---")


def render_login_page():
    """Show login form; on success set session state and rerun."""
    st.markdown(
        """
        <style>
            .login-box {
                max-width: 360px;
                margin: 4rem auto;
                padding: 2rem;
                background: rgba(30, 58, 95, 0.4);
                border-radius: 12px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.2);
            }
            .login-title { font-size: 1.5rem; margin-bottom: 1.5rem; text-align: center; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### Event Analytics Dashboard")
        st.markdown("Sign in to continue.")
        with st.form("login_form"):
            username = st.text_input("Username", placeholder="Enter username", autocomplete="username")
            password = st.text_input("Password", type="password", placeholder="Enter password", autocomplete="current-password")
            submitted = st.form_submit_button("Login")
            if submitted:
                ok, role = verify_login(username, password)
                if ok:
                    st.session_state.authenticated = True
                    st.session_state.user = username.strip().lower()
                    st.session_state.role = role
                    save_auth_session(st.session_state.user, st.session_state.role)
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
    return


def main():
    if st.session_state.get("current_page") == "event_settings":
        render_event_settings_page()
        return
    role = st.session_state.role or "viewer"
    user = st.session_state.user or ""

    # ----- Sidebar -----
    with st.sidebar:
        st.title("📊 Event Dashboard")
        st.caption(f"Logged in as **{user}** ({role})")
        if st.button("Event settings", use_container_width=True, type="secondary"):
            st.session_state.current_page = "event_settings"
            st.rerun()
        if st.button("Logout", use_container_width=True):
            clear_auth_session()
            st.session_state.authenticated = False
            st.session_state.user = None
            st.session_state.role = None
            st.rerun()
        st.markdown("---")

        sheet_id = DEFAULT_SHEET_URL
        credentials_path = DEFAULT_CREDENTIALS_PATH
        connect_clicked = False

        if can_edit_sheet(role):
            with st.expander("Sheet connection", expanded=False):
                sheet_id = st.text_input(
                    "Google Sheet ID or URL",
                    value=st.session_state.sheet_id_input,
                    placeholder="Paste Sheet ID or full sheet URL",
                    help="Paste either the Sheet ID or the full URL (e.g. https://docs.google.com/spreadsheets/d/.../edit)",
                )
                credentials_path = st.text_input(
                    "Credentials path (optional)",
                    value=DEFAULT_CREDENTIALS_PATH,
                    help="Path to service account JSON key file.",
                )
                connect_clicked = st.button("Connect", type="primary", use_container_width=True)

                # Auto-connect on first load if we have defaults and no data yet
                if st.session_state.df_raw is None and sheet_id.strip():
                    resolved_id = extract_sheet_id(sheet_id)
                    if resolved_id and credentials_path.strip():
                        logger.info("Auto-connecting: sheet_id=%s", resolved_id)
                        with st.spinner("Loading sheet..."):
                            df = cached_load_sheet(resolved_id, credentials_path.strip())
                        if df is not None:
                            st.session_state.df_raw = df
                            st.session_state.sheet_id_input = sheet_id.strip()
                            if not df.empty:
                                logger.info("Sheet loaded: %d rows", len(df))

                if connect_clicked and sheet_id.strip():
                    resolved_id = extract_sheet_id(sheet_id)
                    if not resolved_id:
                        logger.warning("Could not extract Sheet ID from input (use ID or full URL)")
                        st.error("Could not extract Sheet ID. Paste the full sheet URL or just the ID from .../d/ID/...")
                    else:
                        logger.info("Connect clicked: resolved sheet_id=%s", resolved_id)
                        with st.spinner("Loading sheet..."):
                            df = cached_load_sheet(resolved_id, credentials_path)
                        if df is not None:
                            st.session_state.df_raw = df
                            st.session_state.sheet_id_input = sheet_id.strip()
                            logger.info("Sheet loaded: %d rows, %d columns", len(df), len(df.columns) if not df.empty else 0)
                            if df.empty:
                                st.warning("Sheet connected but no data rows found. Add data below the header row.")
                            else:
                                st.success("Data loaded successfully!")
                        else:
                            logger.warning("Sheet load returned None (check terminal for errors)")
                            st.session_state.df_raw = None
                elif connect_clicked and not sheet_id.strip():
                    logger.warning("Connect clicked but Sheet ID is empty")
                    st.warning("Please enter a Sheet ID or full sheet URL.")
        else:
            # Viewer: auto-connect using defaults only (no sheet/credentials UI)
            if st.session_state.df_raw is None:
                resolved_id = extract_sheet_id(DEFAULT_SHEET_URL)
                if resolved_id:
                    logger.info("Auto-connecting (viewer): sheet_id=%s", resolved_id)
                    with st.spinner("Loading sheet..."):
                        df = cached_load_sheet(resolved_id, DEFAULT_CREDENTIALS_PATH)
                    if df is not None:
                        st.session_state.df_raw = df
                        st.session_state.sheet_id_input = DEFAULT_SHEET_URL
                        if not df.empty:
                            logger.info("Sheet loaded: %d rows", len(df))
            st.info("Viewer: using default sheet. Contact admin to change.")

        st.markdown("---")
        st.subheader("Event selector")

        df = st.session_state.df_raw
        if df is None:
            st.info("Connect to a sheet first to select events.")
            initiative_options = []
            selected_initiatives = []
        elif df.empty:
            st.info("Sheet connected but no data rows. Add rows below the header and click **Connect** again.")
            initiative_options = []
            selected_initiatives = []
        else:
            col_name = "Initiative Name"
            if col_name not in df.columns:
                cols_preview = ", ".join(df.columns[:8]) + ("..." if len(df.columns) > 8 else "")
                st.warning("Column 'Initiative Name' not found. Columns in sheet: " + cols_preview)
                initiative_options = []
                selected_initiatives = []
            else:
                initiative_options = sorted(df[col_name].dropna().unique().tolist())
                # Keep selection in sync with available options (no default selection)
                current = st.session_state.selected_initiatives
                valid = [x for x in current if x in initiative_options]
                st.session_state.selected_initiatives = valid
                # Keep pins in sync: only names that still exist in the sheet
                pin_list = [x for x in st.session_state.pinned_initiatives if x in initiative_options]
                st.session_state.pinned_initiatives = pin_list
                # Split into pinned (always visible) and other (in accordion)
                pinned = [x for x in initiative_options if x in st.session_state.pinned_initiatives]
                other = [x for x in initiative_options if x not in st.session_state.pinned_initiatives]
                selected_initiatives = st.session_state.selected_initiatives

                st.markdown("Select one event")
                btn_col1, btn_col2, _ = st.columns([1, 1, 2])
                with btn_col1:
                    if st.button("Select first", key="evt_select_all", use_container_width=True):
                        st.session_state.selected_initiatives = [initiative_options[0]] if initiative_options else []
                        st.rerun()
                with btn_col2:
                    if st.button("Deselect all", key="evt_deselect_all", use_container_width=True):
                        st.session_state.selected_initiatives = []
                        st.rerun()

                # Pinned section (always visible)
                if pinned:
                    st.markdown("**Pinned**")
                    for i, opt in enumerate(pinned):
                        is_selected = opt in st.session_state.selected_initiatives
                        label = f"✓ {opt}" if is_selected else opt
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            if st.button(label, key=f"pinned_tile_{i}", use_container_width=True):
                                if is_selected:
                                    st.session_state.selected_initiatives = []
                                else:
                                    st.session_state.selected_initiatives = [opt]
                                st.rerun()
                        with c2:
                            if st.button("Unpin", key=f"pinned_unpin_{i}", use_container_width=True):
                                st.session_state.pinned_initiatives = [x for x in st.session_state.pinned_initiatives if x != opt]
                                save_pinned_to_file(st.session_state.pinned_initiatives)
                                st.rerun()
                    st.markdown("---")

                # Other events (accordion, collapsed by default)
                with st.expander("Other events", expanded=False):
                    if not other:
                        st.caption("No other events.")
                    for i, opt in enumerate(other):
                        is_selected = opt in st.session_state.selected_initiatives
                        label = f"✓ {opt}" if is_selected else opt
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            if st.button(label, key=f"other_tile_{i}", use_container_width=True):
                                if is_selected:
                                    st.session_state.selected_initiatives = []
                                else:
                                    st.session_state.selected_initiatives = [opt]
                                st.rerun()
                        with c2:
                            if st.button("Pin", key=f"other_pin_{i}", use_container_width=True):
                                if opt not in st.session_state.pinned_initiatives:
                                    st.session_state.pinned_initiatives = list(st.session_state.pinned_initiatives) + [opt]
                                    save_pinned_to_file(st.session_state.pinned_initiatives)
                                st.rerun()
                selected_initiatives = st.session_state.selected_initiatives

    # ----- Main content -----
    if df is None:
        st.info("👈 Enter a Google Sheet ID and click **Connect** to load data.")
        return
    if df.empty:
        st.info("Sheet connected but no data rows yet. Add data below the header in your sheet and click **Connect** again to refresh.")
        return

    if not selected_initiatives:
        st.warning("Select at least one event from the sidebar.")
        return

    # Filter dataframe by selected initiatives
    filtered_df = df[df["Initiative Name"].isin(selected_initiatives)].copy()

    # Selected project name at top of page
    selected_name = selected_initiatives[0] if selected_initiatives else ""
    if selected_name:
        st.title(selected_name)
        # Dedicated dashboard link and credentials (from Event settings)
        event_config = get_event_config(load_event_dashboard_config(), selected_name)
        if event_config["dashboard_link"]:
            st.markdown(
                f'<a href="{event_config["dashboard_link"]}" target="_blank" rel="noopener noreferrer" '
                'style="display:inline-block;padding:0.5rem 1rem;background:#2d5a87;color:white;border-radius:8px;text-decoration:none;margin-bottom:0.5rem;">'
                "Open dedicated dashboard</a>",
                unsafe_allow_html=True,
            )
        with st.expander("Admin credentials for this dashboard"):
            if event_config["admin_username"] or event_config["admin_password"]:
                st.text("Username: " + (event_config["admin_username"] or "—"))
                st.text("Password: " + (event_config["admin_password"] or "—"))
            else:
                st.caption("Not set. Configure in **Event settings**.")
        st.markdown("---")

    # ----- Row 1: KPI Cards -----
    kpis = aggregate_numeric_columns(filtered_df, NUMERIC_KPI_COLUMNS)
    reg_count = kpis.get("Registration Count", 0)
    sub_count = kpis.get("Submission Count", 0)
    teams_count = kpis.get("Teams Count", 0)
    page_visits = kpis.get("Page Visits", 0)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(
            f'<div class="metric-card"><h3>Total Registrations</h3><div class="value">{reg_count:,}</div></div>',
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f'<div class="metric-card"><h3>Total Submissions</h3><div class="value">{sub_count:,}</div></div>',
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            f'<div class="metric-card"><h3>Total Teams</h3><div class="value">{teams_count:,}</div></div>',
            unsafe_allow_html=True,
        )
    with col4:
        st.markdown(
            f'<div class="metric-card"><h3>Total Page Visits</h3><div class="value">{page_visits:,}</div></div>',
            unsafe_allow_html=True,
        )

    # ----- Row 2: Daily Registrations (bar chart + optional average line) -----
    st.subheader("Registration Target")
    if COL_DAILY_REG in filtered_df.columns:
        combined_daily = parse_daily_registrations(filtered_df[COL_DAILY_REG])
        dates, counts = daily_registrations_to_line_data(combined_daily)
        if dates and counts:
            # Daily average = total registration target / number of days in registration period
            # Use exact column names from sheet: "Registration Start Date", "Registration End Date"
            REG_START_COL = "Registration Start Date"
            REG_END_COL = "Registration End Date"
            average_daily = None
            days_from_sheet = None
            span_days = None
            end_dt = None  # registration end date (for required daily average)
            event_cfg = get_event_config(load_event_dashboard_config(), selected_name)
            reg_target = event_cfg.get("registration_target") or 0
            has_start = REG_START_COL in filtered_df.columns
            has_end = REG_END_COL in filtered_df.columns
            if has_start and has_end:
                start_col, end_col = REG_START_COL, REG_END_COL
            else:
                end_col = _find_column(filtered_df, "registration", "end") if not has_end else REG_END_COL
                start_col = _find_column(filtered_df, "registration", "start") if not has_start else REG_START_COL
                if not start_col:
                    start_col = "Created At" if "Created At" in filtered_df.columns else None
                if not end_col or end_col not in filtered_df.columns:
                    end_col = None
                if not start_col or start_col not in filtered_df.columns:
                    start_col = None
            if reg_target and end_col and start_col:
                row = filtered_df.iloc[0]
                start_val = row.get(start_col)
                end_val = row.get(end_col)
                if pd.notna(start_val) and pd.notna(end_val):
                    # dayfirst=True so DD-MM-YYYY (e.g. 08-01-2026 = 8 Jan 2026) parses correctly
                    start_dt = pd.to_datetime(start_val, errors="coerce", dayfirst=True)
                    end_dt = pd.to_datetime(end_val, errors="coerce", dayfirst=True)
                    if hasattr(start_dt, "normalize"):
                        start_dt = start_dt.normalize()
                    if hasattr(end_dt, "normalize"):
                        end_dt = end_dt.normalize()
                    if pd.notna(start_dt) and pd.notna(end_dt):
                        # Inclusive: both start and end days count (e.g. 8 Jan to 22 Feb = 46 days)
                        raw_days = (end_dt - start_dt).days + 1
                        days_from_sheet = max(1, raw_days)
                        if days_from_sheet > 1:
                            average_daily = reg_target / days_from_sheet
            # Use chart date span when: no average yet, or sheet gave only 1 day (so line was at full target)
            span_days = None
            if reg_target and dates:
                try:
                    min_d = pd.to_datetime(min(dates), errors="coerce")
                    max_d = pd.to_datetime(max(dates), errors="coerce")
                    if pd.notna(min_d) and pd.notna(max_d):
                        span_days = max(1, (max_d - min_d).days + 1)
                        if average_daily is None or (days_from_sheet is not None and days_from_sheet <= 1):
                            average_daily = reg_target / span_days
                except Exception:
                    pass
            # Required daily average to meet target before end date: (target - total_so_far) / days_remaining
            # days_remaining = number of days from day after last data date through end date (only show when > 0)
            required_daily_avg = None
            total_so_far_used = None
            days_remaining_used = None
            if reg_target and dates and counts and end_dt is not None:
                end_ts = end_dt
                if hasattr(end_ts, "normalize"):
                    end_ts = end_ts.normalize()
                # Only count data on or before registration end date
                mask = []
                for d in dates:
                    dt = pd.to_datetime(d, errors="coerce")
                    if pd.notna(dt) and hasattr(dt, "normalize"):
                        dt = dt.normalize()
                    mask.append(pd.notna(dt) and dt <= end_ts)
                if any(mask):
                    total_so_far = sum(c for c, m in zip(counts, mask) if m)
                    dates_in_range = [d for d, m in zip(dates, mask) if m]
                    last_date = pd.to_datetime(max(dates_in_range), errors="coerce")
                    if pd.notna(last_date) and hasattr(last_date, "normalize"):
                        last_date = last_date.normalize()
                    # Days from day after last_date through end date (0 when last_date >= end_ts)
                    days_remaining = (end_ts - last_date).days
                    if days_remaining > 0:
                        remaining_target = max(0, reg_target - total_so_far)
                        required_daily_avg = remaining_target / days_remaining
                        total_so_far_used = total_so_far
                        days_remaining_used = days_remaining
                    elif average_daily is not None:
                        # Period ended: show green line at full-period average so the line stays visible as benchmark
                        required_daily_avg = average_daily
                        total_so_far_used = total_so_far
                        days_remaining_used = 0
            # Bar colors: green if count >= average_daily, red otherwise; default blue if no average
            if average_daily is not None:
                bar_colors = ["#2ecc71" if c >= average_daily else "#e74c3c" for c in counts]
            else:
                bar_colors = "#3498db"
            fig_line = go.Figure(
                data=[
                    go.Scatter(
                        x=dates,
                        y=counts,
                        mode="lines+markers",
                        line=dict(color="#3498db", width=2),
                        marker=dict(size=8, color=bar_colors, line=dict(width=1, color="white")),
                        name="Daily registrations",
                    )
                ]
            )
            fig_line.update_layout(
                template="plotly_white",
                margin=dict(l=50, r=280, t=50, b=70),
                xaxis_title="Date",
                yaxis_title="Registrations",
                height=380,
                hovermode="x unified",
                showlegend=False,
                font=dict(size=14, color="#1f2937"),
                title_font=dict(size=18),
                xaxis=dict(
                    title_font=dict(size=16),
                    tickfont=dict(size=13),
                    gridcolor="rgba(0,0,0,0.08)",
                ),
                yaxis=dict(
                    title_font=dict(size=16),
                    tickfont=dict(size=13),
                    gridcolor="rgba(0,0,0,0.08)",
                ),
            )
            if average_daily is not None:
                fig_line.add_hline(
                    y=average_daily,
                    line_dash="dash",
                    line_color="#c2410c",
                    line_width=2.5,
                    annotation_text=f"Daily avg (full period): {round(average_daily):,}",
                    annotation_position="right",
                    annotation_font=dict(size=14, color="#c2410c", family="Arial Black"),
                    annotation_bgcolor="rgba(255,255,255,0.9)",
                    annotation_bordercolor="#c2410c",
                    annotation_borderwidth=1,
                )
            if required_daily_avg is not None:
                req_label = (
                    f"Required daily avg (full period): {round(required_daily_avg):,}"
                    if (days_remaining_used is not None and days_remaining_used == 0)
                    else f"Required daily avg to meet target: {round(required_daily_avg):,}"
                )
                fig_line.add_hline(
                    y=required_daily_avg,
                    line_dash="dash",
                    line_color="#047857",
                    line_width=3,
                    annotation_text=req_label,
                    annotation_position="right",
                    annotation_font=dict(size=14, color="#047857", family="Arial Black"),
                    annotation_bgcolor="rgba(255,255,255,0.95)",
                    annotation_bordercolor="#047857",
                    annotation_borderwidth=2,
                )
            st.plotly_chart(fig_line, use_container_width=True)
            # Show how required daily average was computed when the line is shown
            if required_daily_avg is not None and total_so_far_used is not None and days_remaining_used is not None:
                if days_remaining_used > 0:
                    st.caption(f"**Required daily avg:** (target − total so far) ÷ days left = ({reg_target:,} − {total_so_far_used:,}) ÷ {days_remaining_used} = **{round(required_daily_avg):,}**/day until registration end date.")
                else:
                    st.caption(f"Registration period ended. **Required daily avg** line shows the full-period benchmark (**{round(required_daily_avg):,}**/day, same as orange line).")
            # Show how daily average was computed
            if average_daily is not None and span_days is not None and (days_from_sheet is None or days_from_sheet <= 1):
                st.caption(f"Daily average = target ÷ **{span_days}** days (from chart date range). Line at **{round(average_daily)}** registrations/day.")
            elif has_start and has_end and days_from_sheet and days_from_sheet > 1:
                st.caption(f"✓ Daily average from sheet: **Registration Start Date** → **Registration End Date** ({days_from_sheet} days). Line at **{round(average_daily)}**/day.")
            elif not has_start or not has_end:
                missing = []
                if not has_start:
                    missing.append("Registration Start Date")
                if not has_end:
                    missing.append("Registration End Date")
                st.warning(f"Column(s) not found in sheet: {', '.join(missing)}. Ensure your sheet has these exact column names (first row = header).")
        else:
            st.info("No daily registration data available for selected events.")
    else:
        st.info("Daily Registrations column not found in the sheet.")

    # ----- Row 3: Gender + Occupation Pie Charts -----
    st.subheader("Demographics")
    demo_col1, demo_col2 = st.columns(2)

    with demo_col1:
        st.markdown("**Gender Distribution**")
        if COL_GENDER in filtered_df.columns:
            dicts = [safe_json_loads(v) for v in filtered_df[COL_GENDER]]
            merged = merge_json_dicts(dicts)
            if merged:
                fig_gender = px.pie(
                    values=list(merged.values()),
                    names=[normalize_chart_label(k) for k in merged.keys()],
                    hole=0.45,
                    color_discrete_sequence=px.colors.qualitative.Set2,
                )
                fig_gender.update_layout(margin=dict(l=20, r=20, t=30, b=20), height=320, showlegend=True)
                st.plotly_chart(fig_gender, use_container_width=True)
            else:
                st.info("No gender data for selected events.")
        else:
            st.info("Gender Distribution column not found.")

    with demo_col2:
        st.markdown("**Occupation Distribution**")
        if COL_OCCUPATION in filtered_df.columns:
            dicts = [safe_json_loads(v) for v in filtered_df[COL_OCCUPATION]]
            merged = merge_json_dicts(dicts)
            if merged:
                fig_occ = px.pie(
                    values=list(merged.values()),
                    names=[normalize_chart_label(k) for k in merged.keys()],
                    hole=0.45,
                    color_discrete_sequence=px.colors.qualitative.Pastel,
                )
                fig_occ.update_layout(margin=dict(l=20, r=20, t=30, b=20), height=320, showlegend=True)
                st.plotly_chart(fig_occ, use_container_width=True)
            else:
                st.info("No occupation data for selected events.")
        else:
            st.info("Occupation column not found.")

    # ----- Row 4: Country + State Bar Charts -----
    st.subheader("Geography")
    geo_col1, geo_col2 = st.columns(2)

    with geo_col1:
        st.markdown("**Country Distribution**")
        if COL_COUNTRY in filtered_df.columns:
            dicts = [safe_json_loads(v) for v in filtered_df[COL_COUNTRY]]
            merged = merge_json_dicts(dicts)
            if merged:
                # Sort by count descending, take top 15 for readability
                sorted_country = sorted(merged.items(), key=lambda x: -x[1])[:15]
                names = [normalize_chart_label(x[0]) for x in sorted_country]
                values = [x[1] for x in sorted_country]
                fig_country = px.bar(
                    x=values,
                    y=names,
                    orientation="h",
                    labels={"x": "Count", "y": "Country"},
                    color=values,
                    color_continuous_scale="Blues",
                )
                fig_country.update_layout(margin=dict(l=80, r=40, t=30, b=40), height=400, showlegend=False)
                fig_country.update_coloraxes(showscale=False)
                st.plotly_chart(fig_country, use_container_width=True)
            else:
                st.info("No country data for selected events.")
        else:
            st.info("Country column not found.")

    with geo_col2:
        st.markdown("**State Distribution**")
        if COL_STATE in filtered_df.columns:
            dicts = [safe_json_loads(v) for v in filtered_df[COL_STATE]]
            merged = merge_json_dicts(dicts)
            if merged:
                sorted_state = sorted(merged.items(), key=lambda x: -x[1])[:15]
                names = [normalize_chart_label(x[0]) for x in sorted_state]
                values = [x[1] for x in sorted_state]
                fig_state = px.bar(
                    x=values,
                    y=names,
                    orientation="h",
                    labels={"x": "Count", "y": "State"},
                    color=values,
                    color_continuous_scale="Teal",
                )
                fig_state.update_layout(margin=dict(l=80, r=40, t=30, b=40), height=400, showlegend=False)
                fig_state.update_coloraxes(showscale=False)
                st.plotly_chart(fig_state, use_container_width=True)
            else:
                st.info("No state data for selected events.")
        else:
            st.info("State column not found.")

    # ----- Row 5: City Bar Chart -----
    st.subheader("City Distribution")
    if COL_CITY in filtered_df.columns:
        dicts = [safe_json_loads(v) for v in filtered_df[COL_CITY]]
        merged = merge_json_dicts(dicts)
        if merged:
            sorted_city = sorted(merged.items(), key=lambda x: -x[1])[:15]
            names = [normalize_chart_label(x[0]) for x in sorted_city]
            values = [x[1] for x in sorted_city]
            fig_city = px.bar(
                x=values,
                y=names,
                orientation="h",
                labels={"x": "Count", "y": "City"},
                color=values,
                color_continuous_scale="Viridis",
            )
            fig_city.update_layout(margin=dict(l=80, r=40, t=30, b=40), height=400, showlegend=False)
            fig_city.update_coloraxes(showscale=False)
            st.plotly_chart(fig_city, use_container_width=True)
        else:
            st.info("No city data for selected events.")
    else:
        st.info("City column not found.")

    # Refresh hint (only for roles that can connect)
    if can_edit_sheet(st.session_state.role or "viewer"):
        st.sidebar.caption("Data is cached for 5 minutes. Re-connect to refresh.")


if __name__ == "__main__":
    if not st.session_state.authenticated:
        render_login_page()
    else:
        main()
