"""
Hackathon / Event Analytics Dashboard
Connects to Google Sheets and visualizes event statistics with Plotly.
"""

import json
import logging
import os
import sys
from datetime import date, timedelta
import streamlit as st
import pandas as pd

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

# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------
C = {
    "bg": "#0f172a",
    "card": "#1e293b",
    "surface": "#334155",
    "accent": "#6366f1",
    "accent2": "#818cf8",
    "green": "#10b981",
    "amber": "#f59e0b",
    "red": "#ef4444",
    "sky": "#38bdf8",
    "text": "#e2e8f0",
    "text2": "#94a3b8",
    "muted": "#64748b",
    "border": "#334155",
}

_PLOTLY_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, -apple-system, sans-serif", size=13, color=C["text"]),
    margin=dict(l=50, r=30, t=30, b=50),
    xaxis=dict(gridcolor="rgba(148,163,184,0.08)", zerolinecolor="rgba(148,163,184,0.1)",
               title_font=dict(size=12, color=C["text2"]), tickfont=dict(size=11, color=C["muted"])),
    yaxis=dict(gridcolor="rgba(148,163,184,0.08)", zerolinecolor="rgba(148,163,184,0.1)",
               title_font=dict(size=12, color=C["text2"]), tickfont=dict(size=11, color=C["muted"])),
    hoverlabel=dict(bgcolor=C["card"], font_color=C["text"], bordercolor=C["border"]),
)


def plotly_layout(**overrides):
    """Return a merged copy of the base Plotly layout with overrides (deep-merges dict keys like yaxis)."""
    import copy
    out = copy.deepcopy(_PLOTLY_BASE)
    for k, v in overrides.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def _find_column(df: pd.DataFrame, *keywords: str):
    if df is None or df.columns is None:
        return None
    lower_kw = [k.lower() for k in keywords]
    for c in df.columns:
        if all(k in str(c).strip().lower() for k in lower_kw):
            return c
    return None


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Event Analytics", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

# ---------------------------------------------------------------------------
# Global CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

/* Layout */
.main .block-container { padding: 1rem 2rem 3rem; max-width: 1320px; }
section[data-testid="stSidebar"] { background: #0c1222; border-right: 1px solid #1e293b; }
section[data-testid="stSidebar"] .block-container { padding-top: 1rem; }

/* Hide chrome */
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stSidebarNav"] { display: none !important; }

/* Scrollbar */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }

/* --- Top bar --- */
.topbar {
    display: flex; align-items: center; justify-content: space-between;
    padding: 0.7rem 0; margin-bottom: 1.25rem;
    border-bottom: 1px solid #1e293b;
}
.topbar-left { display: flex; align-items: center; gap: 0.75rem; }
.topbar-logo {
    width: 32px; height: 32px; border-radius: 8px;
    background: linear-gradient(135deg, #6366f1, #818cf8);
    display: flex; align-items: center; justify-content: center;
    font-size: 1rem; color: #fff; flex-shrink: 0;
}
.topbar-title { font-size: 1rem; font-weight: 700; color: #e2e8f0; }
.topbar-right { display: flex; align-items: center; gap: 1rem; }
.topbar-user {
    display: flex; align-items: center; gap: 0.5rem;
    font-size: 0.78rem; color: #94a3b8;
}
.topbar-avatar {
    width: 28px; height: 28px; border-radius: 7px;
    background: linear-gradient(135deg, #6366f1, #818cf8);
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 0.7rem; color: #fff;
}
.topbar-badge {
    display: inline-block; padding: 0.15rem 0.5rem;
    border-radius: 6px; font-size: 0.65rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.04em;
    background: rgba(99,102,241,0.15); color: #818cf8;
}

/* --- KPI cards --- */
.kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.85rem; margin-bottom: 1.5rem; }
@media (max-width: 768px) { .kpi-grid { grid-template-columns: repeat(2, 1fr); } }
.kpi {
    padding: 1.1rem 1.25rem; border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.05);
    position: relative; overflow: hidden;
    transition: transform 0.15s, box-shadow 0.15s;
}
.kpi:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.25); }
.kpi-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.6rem; }
.kpi-label { font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: rgba(255,255,255,0.65); }
.kpi-icon-circle {
    width: 30px; height: 30px; border-radius: 8px;
    background: rgba(255,255,255,0.12); display: flex;
    align-items: center; justify-content: center; font-size: 0.85rem;
}
.kpi-value { font-size: 1.7rem; font-weight: 800; color: #fff; line-height: 1; }
.kpi-1 { background: linear-gradient(135deg, #4f46e5, #6366f1); }
.kpi-2 { background: linear-gradient(135deg, #059669, #10b981); }
.kpi-3 { background: linear-gradient(135deg, #d97706, #f59e0b); }
.kpi-4 { background: linear-gradient(135deg, #0284c7, #38bdf8); }

/* --- Progress bar --- */
.progress-wrap { margin-bottom: 1.5rem; }
.progress-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 0.4rem; }
.progress-title { font-size: 0.82rem; font-weight: 600; color: #e2e8f0; }
.progress-stats { font-size: 0.75rem; color: #94a3b8; }
.progress-track {
    width: 100%; height: 10px; background: #1e293b;
    border-radius: 5px; overflow: hidden; border: 1px solid #334155;
}
.progress-fill {
    height: 100%; border-radius: 5px;
    background: linear-gradient(90deg, #6366f1, #818cf8);
    transition: width 0.6s ease;
}
.progress-fill.over { background: linear-gradient(90deg, #10b981, #34d399); }

/* --- Section label --- */
.sec-label {
    font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.08em; color: #64748b;
    margin: 1.5rem 0 0.6rem; padding-bottom: 0.3rem;
    border-bottom: 1px solid #1e293b;
}

/* --- Container overrides --- */
div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
    background: #1e293b !important;
    border: 1px solid #334155 !important;
    border-radius: 12px !important;
}

/* --- Login --- */
.login-header {
    text-align: center;
    padding: 2.5rem 2rem 1.75rem;
}
.login-logo {
    width: 56px; height: 56px; border-radius: 16px;
    background: linear-gradient(135deg, #6366f1 0%, #818cf8 100%);
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 1.5rem; margin-bottom: 1rem;
    box-shadow: 0 8px 24px rgba(99,102,241,0.3);
}
.login-header h1 {
    font-size: 1.5rem; font-weight: 800; color: #f1f5f9;
    margin: 0 0 0.35rem 0; letter-spacing: -0.02em;
}
.login-header p {
    font-size: 0.85rem; color: #64748b; margin: 0;
    font-weight: 400;
}

/* --- Sidebar sections --- */
.sb-section {
    font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.08em; color: #475569; margin: 0.6rem 0 0.35rem;
}

/* --- Streamlit component tweaks --- */
.stExpander { border-color: #334155 !important; border-radius: 10px !important; }
div[data-testid="stExpander"] details { border-color: #334155 !important; border-radius: 10px !important; }
.stTextInput > div > div > input {
    border-radius: 8px !important; border: 1px solid #334155 !important;
    background: #0f172a !important; font-size: 0.85rem !important;
}
.stTextInput > div > div > input:focus {
    border-color: #6366f1 !important; box-shadow: 0 0 0 2px rgba(99,102,241,0.15) !important;
}
button[kind="primary"], button[data-testid="stBaseButton-primary"] {
    background: linear-gradient(135deg, #6366f1, #4f46e5) !important;
    border: none !important; border-radius: 8px !important; font-weight: 600 !important;
    transition: all 0.15s !important;
}
button[kind="primary"]:hover, button[data-testid="stBaseButton-primary"]:hover {
    box-shadow: 0 4px 16px rgba(99,102,241,0.35) !important;
}
section[data-testid="stSidebar"] button {
    border-radius: 8px !important; font-size: 0.8rem !important; font-weight: 500 !important;
}
section[data-testid="stSidebar"] hr { border-color: #1e293b; margin: 0.6rem 0; }
div[data-testid="stAlert"] { border-radius: 10px !important; border: none !important; }
.stTabs [data-baseweb="tab-list"] { gap: 0; border-bottom: 1px solid #334155; }
.stTabs [data-baseweb="tab"] {
    padding: 0.6rem 1.2rem !important; font-size: 0.82rem !important;
    font-weight: 500 !important; color: #94a3b8 !important;
    border-bottom: 2px solid transparent !important;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    color: #e2e8f0 !important; font-weight: 600 !important;
    border-bottom: 2px solid #6366f1 !important;
    background: transparent !important;
}
.stCaption, small { color: #64748b !important; }

/* --- Dashboard link --- */
.dash-link {
    display: inline-flex; align-items: center; gap: 0.4rem;
    padding: 0.45rem 1rem; background: rgba(99,102,241,0.12);
    color: #818cf8 !important; border: 1px solid rgba(99,102,241,0.25);
    border-radius: 8px; text-decoration: none;
    font-weight: 600; font-size: 0.8rem; transition: all 0.15s;
}
.dash-link:hover { background: rgba(99,102,241,0.2); color: #a5b4fc !important; }

/* --- Empty state --- */
.empty-state { text-align: center; padding: 3rem 2rem; }
.empty-icon { font-size: 2.2rem; display: block; margin-bottom: 0.6rem; opacity: 0.5; }
.empty-msg { font-size: 0.88rem; color: #94a3b8; margin: 0; }

/* --- Settings card --- */
.settings-card {
    background: #1e293b; border: 1px solid #334155; border-radius: 12px;
    padding: 1.25rem; margin-bottom: 0.75rem;
}
.settings-card h3 { margin: 0 0 0.6rem 0; font-size: 0.95rem; font-weight: 600; color: #e2e8f0; }
.sf { display: flex; gap: 0.5rem; padding: 0.25rem 0; font-size: 0.8rem; color: #94a3b8; }
.sf .sl { font-weight: 500; color: #cbd5e1; min-width: 80px; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Pinned initiatives
# ---------------------------------------------------------------------------
PINNED_FILE = "pinned_initiatives.json"


def load_pinned_from_file():
    try:
        if os.path.isfile(PINNED_FILE):
            with open(PINNED_FILE, encoding="utf-8") as f:
                data = json.load(f)
                return data.get("pinned", []) if isinstance(data, dict) else []
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save_pinned_to_file(pinned_list):
    try:
        with open(PINNED_FILE, "w", encoding="utf-8") as f:
            json.dump({"pinned": list(pinned_list)}, f, indent=2)
    except OSError as e:
        logger.warning("Could not save pinned initiatives: %s", e)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def clear_auth_session():
    st.session_state.authenticated = False
    st.session_state.user = None
    st.session_state.role = None
    st.session_state.login_date = None


if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user = None
    st.session_state.role = None
    st.session_state.login_date = None
elif st.session_state.authenticated:
    login_date_str = st.session_state.get("login_date")
    try:
        login_dt = date.fromisoformat(login_date_str) if login_date_str else None
    except (ValueError, TypeError):
        login_dt = None
    if login_dt is None or (date.today() - login_dt) >= timedelta(weeks=1):
        logger.info("Session expired (login was %s, >7 days ago) — re-login required", login_date_str)
        clear_auth_session()

if "user" not in st.session_state:
    st.session_state.user = None
if "role" not in st.session_state:
    st.session_state.role = None
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
    return load_sheet_data(sheet_id, credentials_path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def empty(icon: str, msg: str):
    st.markdown(f'<div class="empty-state"><span class="empty-icon">{icon}</span><p class="empty-msg">{msg}</p></div>', unsafe_allow_html=True)


def topbar(user: str, role: str, event_name: str = ""):
    initial = user[0].upper() if user else "?"
    event_part = f'<span style="color:#64748b;margin:0 0.4rem">·</span><span style="color:#94a3b8;font-weight:500">{event_name}</span>' if event_name else ""
    st.markdown(
        f'<div class="topbar">'
        f'<div class="topbar-left">'
        f'<div class="topbar-logo">📊</div>'
        f'<span class="topbar-title">Event Analytics</span>{event_part}'
        f'</div>'
        f'<div class="topbar-right">'
        f'<span class="topbar-badge">{role}</span>'
        f'<div class="topbar-user">'
        f'<div class="topbar-avatar">{initial}</div>'
        f'<span>{user}</span>'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )


def kpi_row(regs, subs, teams, visits):
    st.markdown(
        f'<div class="kpi-grid">'
        f'<div class="kpi kpi-1"><div class="kpi-top"><span class="kpi-label">Registrations</span><div class="kpi-icon-circle">👥</div></div><div class="kpi-value">{regs:,}</div></div>'
        f'<div class="kpi kpi-2"><div class="kpi-top"><span class="kpi-label">Submissions</span><div class="kpi-icon-circle">📝</div></div><div class="kpi-value">{subs:,}</div></div>'
        f'<div class="kpi kpi-3"><div class="kpi-top"><span class="kpi-label">Teams</span><div class="kpi-icon-circle">🏆</div></div><div class="kpi-value">{teams:,}</div></div>'
        f'<div class="kpi kpi-4"><div class="kpi-top"><span class="kpi-label">Page Visits</span><div class="kpi-icon-circle">🌐</div></div><div class="kpi-value">{visits:,}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def progress_bar(current, target, label="Registration Progress"):
    if not target:
        return
    pct = min(current / target * 100, 100) if target else 0
    cls = "over" if pct >= 100 else ""
    st.markdown(
        f'<div class="progress-wrap">'
        f'<div class="progress-header">'
        f'<span class="progress-title">{label}</span>'
        f'<span class="progress-stats">{current:,} / {target:,} ({pct:.1f}%)</span>'
        f'</div>'
        f'<div class="progress-track"><div class="progress-fill {cls}" style="width:{pct:.1f}%"></div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def sec_label(text: str):
    st.markdown(f'<div class="sec-label">{text}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Event Settings Page
# ---------------------------------------------------------------------------
def render_event_settings_page():
    if "editing_event" not in st.session_state:
        st.session_state.editing_event = None

    user = st.session_state.user or ""
    role = st.session_state.role or "viewer"

    with st.sidebar:
        st.markdown(f'<div class="sb-section">Navigation</div>', unsafe_allow_html=True)
        if st.button("Back to Dashboard", use_container_width=True, icon=":material/arrow_back:"):
            st.session_state.current_page = "dashboard"
            st.rerun()
        if st.button("Logout", use_container_width=True, icon=":material/logout:"):
            clear_auth_session()
            st.session_state.current_page = "dashboard"
            st.rerun()

    topbar(user, role)
    sec_label("Event Settings")
    st.caption("Configure dashboard links, admin credentials, and registration targets.")

    df = st.session_state.get("df_raw")
    if df is None or df.empty:
        empty("📋", "Load events from the dashboard first, then return here.")
        return
    col_name = "Initiative Name"
    if col_name not in df.columns:
        st.warning("Column 'Initiative Name' not found.")
        return

    initiative_options = sorted(df[col_name].dropna().unique().tolist())
    config = load_event_dashboard_config()

    for i, name in enumerate(initiative_options):
        entry = get_event_config(config, name)
        is_editing = st.session_state.editing_event == name
        sk = f"ev_{i}"

        st.markdown(f'<div class="settings-card"><h3>{name}</h3>', unsafe_allow_html=True)
        if is_editing:
            link = st.text_input("Dashboard link", value=entry["dashboard_link"], key=f"link_{sk}", placeholder="https://...")
            username = st.text_input("Admin username", value=entry["admin_username"], key=f"user_{sk}")
            password = st.text_input("Admin password", value=entry["admin_password"], type="password", key=f"pass_{sk}")
            reg_target = entry.get("registration_target") or 0
            registration_target = st.number_input("Registration target", min_value=0, value=int(reg_target) if reg_target else 0, key=f"rt_{sk}")
            c1, c2, _ = st.columns([1, 1, 3])
            with c1:
                if st.button("Save", key=f"save_{sk}", type="primary", use_container_width=True):
                    config[name] = {"dashboard_link": (link or "").strip(), "admin_username": (username or "").strip(),
                                    "admin_password": password or "", "registration_target": registration_target}
                    save_event_dashboard_config(config)
                    st.session_state.editing_event = None
                    st.rerun()
            with c2:
                if st.button("Cancel", key=f"cancel_{sk}", use_container_width=True):
                    st.session_state.editing_event = None
                    st.rerun()
        else:
            has_link = bool(entry["dashboard_link"])
            link_url = entry["dashboard_link"]
            link_disp = link_url[:50] + "..." if has_link and len(link_url) > 50 else link_url
            link_html = f'<a href="{link_url}" target="_blank" style="color:#818cf8">{link_disp}</a>' if has_link else "—"
            rt = entry.get("registration_target") or 0
            st.markdown(
                f'<div class="sf"><span class="sl">Link</span><span>{link_html}</span></div>'
                f'<div class="sf"><span class="sl">Username</span><span>{entry["admin_username"] or "—"}</span></div>'
                f'<div class="sf"><span class="sl">Password</span><span>{"••••••" if entry["admin_password"] else "—"}</span></div>'
                f'<div class="sf"><span class="sl">Target</span><span>{f"{rt:,}" if rt else "—"}</span></div>',
                unsafe_allow_html=True,
            )
            if st.button("Edit", key=f"edit_{sk}"):
                st.session_state.editing_event = name
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Login Page
# ---------------------------------------------------------------------------
def render_login_page():
    st.markdown(
        """<style>
        /* Hide everything except the login card */
        section[data-testid="stSidebar"] { display: none !important; }
        [data-testid="stSidebarCollapsedControl"] { display: none !important; }

        /* Center the card */
        .main .block-container {
            max-width: 420px !important;
            padding-top: 8vh !important;
            padding-bottom: 4rem !important;
            margin: 0 auto;
        }

        /* Form card */
        [data-testid="stForm"] {
            background: #162032 !important;
            border: 1px solid #233044 !important;
            border-radius: 20px !important;
            padding: 0 2rem 2rem !important;
            box-shadow: 0 20px 60px rgba(0,0,0,0.4), 0 0 0 1px rgba(99,102,241,0.06) !important;
        }

        /* Input fields inside login */
        [data-testid="stForm"] .stTextInput > div > div > input {
            background: #0f172a !important;
            border: 1px solid #2a3a52 !important;
            border-radius: 10px !important;
            padding: 0.65rem 0.85rem !important;
            font-size: 0.88rem !important;
            color: #e2e8f0 !important;
            transition: border-color 0.2s, box-shadow 0.2s !important;
        }
        [data-testid="stForm"] .stTextInput > div > div > input:focus {
            border-color: #6366f1 !important;
            box-shadow: 0 0 0 3px rgba(99,102,241,0.15) !important;
        }
        [data-testid="stForm"] .stTextInput > div > div > input::placeholder {
            color: #475569 !important;
        }

        /* Labels */
        [data-testid="stForm"] .stTextInput > label {
            font-size: 0.8rem !important;
            font-weight: 600 !important;
            color: #94a3b8 !important;
            letter-spacing: 0.01em !important;
        }

        /* Submit button */
        [data-testid="stForm"] button[kind="formSubmit"] {
            background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%) !important;
            border: none !important;
            border-radius: 10px !important;
            padding: 0.7rem 1rem !important;
            font-size: 0.9rem !important;
            font-weight: 600 !important;
            letter-spacing: 0.01em !important;
            box-shadow: 0 4px 16px rgba(99,102,241,0.35) !important;
            transition: all 0.2s !important;
        }
        [data-testid="stForm"] button[kind="formSubmit"]:hover {
            box-shadow: 0 6px 24px rgba(99,102,241,0.5) !important;
            transform: translateY(-1px) !important;
        }

        /* Error alert */
        [data-testid="stForm"] div[data-testid="stAlert"] {
            border-radius: 10px !important;
            font-size: 0.82rem !important;
        }
        </style>""",
        unsafe_allow_html=True,
    )

    with st.form("login_form"):
        st.markdown(
            '<div class="login-header">'
            '<div class="login-logo">📊</div>'
            '<h1>Event Analytics</h1>'
            '<p>Sign in to your dashboard</p>'
            '</div>',
            unsafe_allow_html=True,
        )
        username = st.text_input("Username", placeholder="Enter your username", autocomplete="username")
        password = st.text_input("Password", type="password", placeholder="Enter your password", autocomplete="current-password")
        st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
        submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
        if submitted:
            ok, role = verify_login(username, password)
            if ok:
                st.session_state.authenticated = True
                st.session_state.user = username.strip().lower()
                st.session_state.role = role
                st.session_state.login_date = str(date.today())
                st.rerun()
            else:
                st.error("Invalid username or password.")


# ---------------------------------------------------------------------------
# Main Dashboard
# ---------------------------------------------------------------------------
def main():
    if st.session_state.get("current_page") == "event_settings":
        render_event_settings_page()
        return

    role = st.session_state.role or "viewer"
    user = st.session_state.user or ""

    # ── Sidebar ──────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown('<div class="sb-section">Navigation</div>', unsafe_allow_html=True)
        nav1, nav2 = st.columns(2)
        with nav1:
            if st.button("Settings", use_container_width=True, icon=":material/settings:"):
                st.session_state.current_page = "event_settings"
                st.rerun()
        with nav2:
            if st.button("Logout", use_container_width=True, icon=":material/logout:"):
                clear_auth_session()
                st.rerun()

        st.markdown("---")

        # Sheet connection
        sheet_id = DEFAULT_SHEET_URL
        credentials_path = DEFAULT_CREDENTIALS_PATH
        connect_clicked = False

        if can_edit_sheet(role):
            with st.expander("Data source", expanded=False, icon=":material/database:"):
                sheet_id = st.text_input("Sheet ID or URL", value=st.session_state.sheet_id_input,
                                         placeholder="Paste Sheet ID or URL")
                credentials_path = st.text_input("Credentials", value=DEFAULT_CREDENTIALS_PATH)
                connect_clicked = st.button("Connect", type="primary", use_container_width=True)

                if st.session_state.df_raw is None and sheet_id.strip():
                    resolved_id = extract_sheet_id(sheet_id)
                    if resolved_id and credentials_path.strip():
                        with st.spinner("Loading..."):
                            df = cached_load_sheet(resolved_id, credentials_path.strip())
                        if df is not None:
                            st.session_state.df_raw = df
                            st.session_state.sheet_id_input = sheet_id.strip()

                if connect_clicked and sheet_id.strip():
                    resolved_id = extract_sheet_id(sheet_id)
                    if not resolved_id:
                        st.error("Invalid Sheet ID.")
                    else:
                        with st.spinner("Loading..."):
                            df = cached_load_sheet(resolved_id, credentials_path)
                        if df is not None:
                            st.session_state.df_raw = df
                            st.session_state.sheet_id_input = sheet_id.strip()
                            st.success("Connected!" if not df.empty else "Connected — no rows.")
                        else:
                            st.session_state.df_raw = None
        else:
            if st.session_state.df_raw is None:
                resolved_id = extract_sheet_id(DEFAULT_SHEET_URL)
                if resolved_id:
                    with st.spinner("Loading..."):
                        df = cached_load_sheet(resolved_id, DEFAULT_CREDENTIALS_PATH)
                    if df is not None:
                        st.session_state.df_raw = df

        st.markdown("---")
        st.markdown('<div class="sb-section">Events</div>', unsafe_allow_html=True)
        df = st.session_state.df_raw

        if df is None:
            st.caption("Connect to a data source first.")
            initiative_options = []
            selected_initiatives = []
        elif df.empty:
            st.caption("No data rows in sheet.")
            initiative_options = []
            selected_initiatives = []
        else:
            col_name = "Initiative Name"
            if col_name not in df.columns:
                st.warning("'Initiative Name' column missing.")
                initiative_options = []
                selected_initiatives = []
            else:
                initiative_options = sorted(df[col_name].dropna().unique().tolist())
                st.session_state.selected_initiatives = [x for x in st.session_state.selected_initiatives if x in initiative_options]
                st.session_state.pinned_initiatives = [x for x in st.session_state.pinned_initiatives if x in initiative_options]
                pinned = [x for x in initiative_options if x in st.session_state.pinned_initiatives]
                other = [x for x in initiative_options if x not in st.session_state.pinned_initiatives]
                selected_initiatives = st.session_state.selected_initiatives

                if pinned:
                    for i, opt in enumerate(pinned):
                        is_sel = opt in selected_initiatives
                        c1, c2 = st.columns([5, 1])
                        with c1:
                            if st.button(f"{'● ' if is_sel else ''}{opt}", key=f"p_{i}",
                                         use_container_width=True, type="primary" if is_sel else "secondary"):
                                st.session_state.selected_initiatives = [] if is_sel else [opt]
                                st.rerun()
                        with c2:
                            if st.button("✕", key=f"pu_{i}", help="Unpin"):
                                st.session_state.pinned_initiatives.remove(opt)
                                save_pinned_to_file(st.session_state.pinned_initiatives)
                                st.rerun()

                with st.expander(f"All events ({len(other)})", expanded=not pinned):
                    for i, opt in enumerate(other):
                        is_sel = opt in selected_initiatives
                        c1, c2 = st.columns([5, 1])
                        with c1:
                            if st.button(f"{'● ' if is_sel else ''}{opt}", key=f"o_{i}",
                                         use_container_width=True, type="primary" if is_sel else "secondary"):
                                st.session_state.selected_initiatives = [] if is_sel else [opt]
                                st.rerun()
                        with c2:
                            if st.button("📌", key=f"op_{i}", help="Pin"):
                                if opt not in st.session_state.pinned_initiatives:
                                    st.session_state.pinned_initiatives.append(opt)
                                    save_pinned_to_file(st.session_state.pinned_initiatives)
                                st.rerun()
                selected_initiatives = st.session_state.selected_initiatives

        if can_edit_sheet(role):
            st.markdown("---")
            st.caption("Data cached 5 min.")

    # ── Main content ─────────────────────────────────────────────────────
    selected_name = selected_initiatives[0] if selected_initiatives else ""
    topbar(user, role, selected_name)

    if df is None:
        empty("🔗", "Connect to a Google Sheet from the sidebar to get started.")
        return
    if df.empty:
        empty("📄", "Sheet connected but no data rows. Add data and reconnect.")
        return
    if not selected_initiatives:
        empty("👈", "Select an event from the sidebar to view analytics.")
        return

    filtered_df = df[df["Initiative Name"].isin(selected_initiatives)].copy()

    # Event header
    event_config = get_event_config(load_event_dashboard_config(), selected_name)
    if event_config["dashboard_link"]:
        st.markdown(f'<a href="{event_config["dashboard_link"]}" target="_blank" class="dash-link">Open dashboard ↗</a>', unsafe_allow_html=True)
        st.markdown("<div style='height:0.3rem'></div>", unsafe_allow_html=True)

    # KPIs
    kpis = aggregate_numeric_columns(filtered_df, NUMERIC_KPI_COLUMNS)
    reg_count = kpis.get("Registration Count", 0)
    sub_count = kpis.get("Submission Count", 0)
    teams_count = kpis.get("Teams Count", 0)
    page_visits = kpis.get("Page Visits", 0)
    kpi_row(reg_count, sub_count, teams_count, page_visits)

    # Registration progress
    reg_target = event_config.get("registration_target") or 0
    if reg_target:
        progress_bar(reg_count, reg_target)

    # Admin credentials
    with st.expander("Admin credentials", icon=":material/key:"):
        if event_config["admin_username"] or event_config["admin_password"]:
            cc1, cc2 = st.columns(2)
            with cc1:
                st.text_input("Username", value=event_config["admin_username"] or "—", disabled=True, key="cd_u")
            with cc2:
                st.text_input("Password", value=event_config["admin_password"] or "—", disabled=True, key="cd_p")
        else:
            st.caption("Not configured. Set up in Settings.")

    # ── Registration Trend ───────────────────────────────────────────────
    sec_label("Registration Trend")
    if COL_DAILY_REG in filtered_df.columns:
        combined_daily = parse_daily_registrations(filtered_df[COL_DAILY_REG])
        dates, counts = daily_registrations_to_line_data(combined_daily)
        if dates and counts:
            with st.container(border=True):
                REG_START_COL, REG_END_COL = "Registration Start Date", "Registration End Date"
                average_daily = None
                days_from_sheet = None
                span_days = None
                end_dt = None
                event_cfg = get_event_config(load_event_dashboard_config(), selected_name)
                rtarget = event_cfg.get("registration_target") or 0
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
                if rtarget and end_col and start_col:
                    row = filtered_df.iloc[0]
                    sv, ev = row.get(start_col), row.get(end_col)
                    if pd.notna(sv) and pd.notna(ev):
                        sdt = pd.to_datetime(sv, errors="coerce", dayfirst=True)
                        edt = pd.to_datetime(ev, errors="coerce", dayfirst=True)
                        if hasattr(sdt, "normalize"): sdt = sdt.normalize()
                        if hasattr(edt, "normalize"): edt = edt.normalize()
                        end_dt = edt
                        if pd.notna(sdt) and pd.notna(edt):
                            days_from_sheet = max(1, (edt - sdt).days + 1)
                            if days_from_sheet > 1:
                                average_daily = rtarget / days_from_sheet
                if rtarget and dates:
                    try:
                        mn, mx = pd.to_datetime(min(dates), errors="coerce"), pd.to_datetime(max(dates), errors="coerce")
                        if pd.notna(mn) and pd.notna(mx):
                            span_days = max(1, (mx - mn).days + 1)
                            if average_daily is None or (days_from_sheet and days_from_sheet <= 1):
                                average_daily = rtarget / span_days
                    except Exception:
                        pass

                req_avg = None
                tsf_used = None
                dr_used = None
                if rtarget and dates and counts and end_dt is not None:
                    ets = end_dt.normalize() if hasattr(end_dt, "normalize") else end_dt
                    mask = []
                    for d in dates:
                        dt = pd.to_datetime(d, errors="coerce")
                        if pd.notna(dt) and hasattr(dt, "normalize"): dt = dt.normalize()
                        mask.append(pd.notna(dt) and dt <= ets)
                    if any(mask):
                        tsf = sum(c for c, m in zip(counts, mask) if m)
                        dr_dates = [d for d, m in zip(dates, mask) if m]
                        ld = pd.to_datetime(max(dr_dates), errors="coerce")
                        if pd.notna(ld) and hasattr(ld, "normalize"): ld = ld.normalize()
                        dr = (ets - ld).days
                        if dr > 0:
                            req_avg = max(0, rtarget - tsf) / dr
                            tsf_used, dr_used = tsf, dr
                        elif average_daily is not None:
                            req_avg = average_daily
                            tsf_used, dr_used = tsf, 0

                bar_colors = ["#10b981" if c >= average_daily else "#ef4444" for c in counts] if average_daily else ["#818cf8"] * len(counts)
                cum = []
                r = 0
                for c in counts:
                    r += c
                    cum.append(r)

                fig = go.Figure()
                fig.add_trace(go.Bar(x=dates, y=counts, marker_color=bar_colors, marker_line_width=0,
                                     name="Daily", opacity=0.75,
                                     hovertemplate="<b>%{x}</b><br>Daily: %{y:,}<extra></extra>"))
                fig.add_trace(go.Scatter(x=dates, y=cum, mode="lines+markers",
                                         line=dict(color="#818cf8", width=2.5), marker=dict(size=4, color="#818cf8"),
                                         name="Cumulative", yaxis="y2",
                                         hovertemplate="<b>%{x}</b><br>Cumulative: %{y:,}<extra></extra>"))
                fig.update_layout(
                    **plotly_layout(), height=400, hovermode="x unified", showlegend=True, bargap=0.15,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                                font=dict(size=11, color=C["text2"]), bgcolor="rgba(0,0,0,0)"),
                    xaxis_title="Date", yaxis_title="Daily",
                    yaxis2=dict(title="Cumulative", overlaying="y", side="right", showgrid=False,
                                title_font=dict(size=12, color="#818cf8"), tickfont=dict(size=11, color="#818cf8")),
                )
                if average_daily:
                    fig.add_hline(y=average_daily, line_dash="dash", line_color="#f59e0b", line_width=1.5,
                                  annotation_text=f"Avg: {round(average_daily):,}", annotation_position="bottom left",
                                  annotation_font=dict(size=10, color="#f59e0b"),
                                  annotation_bgcolor="rgba(15,23,42,0.85)", annotation_bordercolor="#f59e0b")
                if req_avg is not None:
                    lbl = f"Req: {round(req_avg):,}" if dr_used and dr_used > 0 else f"Period avg: {round(req_avg):,}"
                    fig.add_hline(y=req_avg, line_dash="dot", line_color="#10b981", line_width=1.5,
                                  annotation_text=lbl, annotation_position="top left",
                                  annotation_font=dict(size=10, color="#10b981"),
                                  annotation_bgcolor="rgba(15,23,42,0.85)", annotation_bordercolor="#10b981")
                if rtarget:
                    fig.add_hline(y=rtarget, line_dash="dash", line_color="rgba(148,163,184,0.3)", line_width=1,
                                  annotation_text=f"Target: {rtarget:,}", annotation_position="top right",
                                  annotation_font=dict(size=10, color=C["muted"]),
                                  annotation_bgcolor="rgba(15,23,42,0.85)", yref="y2")
                st.plotly_chart(fig, use_container_width=True)

                if req_avg is not None and tsf_used is not None and dr_used is not None:
                    if dr_used > 0:
                        st.caption(f"Required: ({rtarget:,} − {tsf_used:,}) ÷ {dr_used} days = **{round(req_avg):,}**/day")
                    else:
                        st.caption(f"Period ended. Benchmark: **{round(req_avg):,}**/day")
                if average_daily and span_days and (not days_from_sheet or days_from_sheet <= 1):
                    st.caption(f"Daily avg = target ÷ {span_days} days = **{round(average_daily)}**/day")
                elif has_start and has_end and days_from_sheet and days_from_sheet > 1:
                    st.caption(f"Avg from sheet dates ({days_from_sheet} days): **{round(average_daily)}**/day")
        else:
            empty("📉", "No daily registration data for this event.")
    else:
        empty("📉", "Daily Registrations column not found.")

    # ── Demographics & Geography (tabs) ──────────────────────────────────
    sec_label("Breakdown")
    tab_demo, tab_geo = st.tabs(["Demographics", "Geography"])

    with tab_demo:
        d1, d2 = st.columns(2)
        with d1:
            with st.container(border=True):
                st.markdown("**Gender**")
                if COL_GENDER in filtered_df.columns:
                    merged = merge_json_dicts([safe_json_loads(v) for v in filtered_df[COL_GENDER]])
                    if merged:
                        fig_g = px.pie(values=list(merged.values()),
                                       names=[normalize_chart_label(k) for k in merged],
                                       hole=0.5, color_discrete_sequence=["#818cf8", "#f472b6", "#34d399", "#fbbf24", "#fb923c"])
                        fig_g.update_layout(**plotly_layout(), height=320, showlegend=True,
                                            legend=dict(font=dict(size=11, color=C["text2"])))
                        fig_g.update_traces(textfont_color="#fff", hovertemplate="<b>%{label}</b><br>%{value:,} (%{percent})<extra></extra>")
                        st.plotly_chart(fig_g, use_container_width=True)
                    else:
                        empty("⚧", "No data")
                else:
                    empty("⚧", "Column not found")
        with d2:
            with st.container(border=True):
                st.markdown("**Occupation**")
                if COL_OCCUPATION in filtered_df.columns:
                    merged = merge_json_dicts([safe_json_loads(v) for v in filtered_df[COL_OCCUPATION]])
                    if merged:
                        fig_o = px.pie(values=list(merged.values()),
                                       names=[normalize_chart_label(k) for k in merged],
                                       hole=0.5, color_discrete_sequence=["#38bdf8", "#a78bfa", "#fb923c", "#4ade80", "#f87171", "#facc15"])
                        fig_o.update_layout(**plotly_layout(), height=320, showlegend=True,
                                            legend=dict(font=dict(size=11, color=C["text2"])))
                        fig_o.update_traces(textfont_color="#fff", hovertemplate="<b>%{label}</b><br>%{value:,} (%{percent})<extra></extra>")
                        st.plotly_chart(fig_o, use_container_width=True)
                    else:
                        empty("💼", "No data")
                else:
                    empty("💼", "Column not found")

    with tab_geo:
        g1, g2 = st.columns(2)
        with g1:
            with st.container(border=True):
                st.markdown("**Country**")
                if COL_COUNTRY in filtered_df.columns:
                    merged = merge_json_dicts([safe_json_loads(v) for v in filtered_df[COL_COUNTRY]])
                    if merged:
                        items = sorted(merged.items(), key=lambda x: -x[1])[:12]
                        fig_c = go.Figure(go.Bar(x=[v for _, v in items], y=[normalize_chart_label(k) for k, _ in items],
                                                  orientation="h", marker=dict(color=[v for _, v in items],
                                                  colorscale=[[0, "#1e3a5f"], [1, "#818cf8"]], line_width=0, cornerradius=3),
                                                  hovertemplate="<b>%{y}</b><br>%{x:,}<extra></extra>"))
                        fig_c.update_layout(**plotly_layout(yaxis=dict(autorange="reversed")),
                                            height=380, showlegend=False)
                        st.plotly_chart(fig_c, use_container_width=True)
                    else:
                        empty("🏳️", "No data")
                else:
                    empty("🏳️", "Column not found")
        with g2:
            with st.container(border=True):
                st.markdown("**State**")
                if COL_STATE in filtered_df.columns:
                    merged = merge_json_dicts([safe_json_loads(v) for v in filtered_df[COL_STATE]])
                    if merged:
                        items = sorted(merged.items(), key=lambda x: -x[1])[:12]
                        fig_s = go.Figure(go.Bar(x=[v for _, v in items], y=[normalize_chart_label(k) for k, _ in items],
                                                  orientation="h", marker=dict(color=[v for _, v in items],
                                                  colorscale=[[0, "#134e4a"], [1, "#34d399"]], line_width=0, cornerradius=3),
                                                  hovertemplate="<b>%{y}</b><br>%{x:,}<extra></extra>"))
                        fig_s.update_layout(**plotly_layout(yaxis=dict(autorange="reversed")),
                                            height=380, showlegend=False)
                        st.plotly_chart(fig_s, use_container_width=True)
                    else:
                        empty("📍", "No data")
                else:
                    empty("📍", "Column not found")

        with st.container(border=True):
            st.markdown("**City**")
            if COL_CITY in filtered_df.columns:
                merged = merge_json_dicts([safe_json_loads(v) for v in filtered_df[COL_CITY]])
                if merged:
                    items = sorted(merged.items(), key=lambda x: -x[1])[:15]
                    fig_ci = go.Figure(go.Bar(x=[v for _, v in items], y=[normalize_chart_label(k) for k, _ in items],
                                              orientation="h", marker=dict(color=[v for _, v in items],
                                              colorscale=[[0, "#312e81"], [1, "#a78bfa"]], line_width=0, cornerradius=3),
                                              hovertemplate="<b>%{y}</b><br>%{x:,}<extra></extra>"))
                    fig_ci.update_layout(**plotly_layout(yaxis=dict(autorange="reversed")),
                                         height=420, showlegend=False)
                    st.plotly_chart(fig_ci, use_container_width=True)
                else:
                    empty("🏙️", "No data")
            else:
                empty("🏙️", "Column not found")


if __name__ == "__main__":
    if not st.session_state.authenticated:
        render_login_page()
    else:
        main()
