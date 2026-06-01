"""
Flask application for the Event Analytics Dashboard.
Replaces the Streamlit app with full HTML/CSS/JS control.
"""

import json
import logging
import os
import sys

from dotenv import load_dotenv
load_dotenv()

from flask import (
    Flask,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.middleware.proxy_fix import ProxyFix

from h2s_cdi_auth import (
    get_module_event_allowlist,
    get_portal_dashboard_url,
    get_portal_url,
    register_h2s_cdi_auth,
    register_with_portal,
)
from config_helpers import (
    DEFAULT_CREDENTIALS_PATH,
    DEFAULT_SHEET_URL,
    load_event_dashboard_config,
    save_event_dashboard_config,
    get_event_config,
)
from data_service import cached_load_sheet, get_event_list, get_event_analytics
from utils import extract_sheet_id

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,
    force=True,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "event-dashboard-secret-key-change-in-prod")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

APPLICATION_ROOT = (os.environ.get("APPLICATION_ROOT") or "").strip().rstrip("/")

PINNED_FILE = "pinned_initiatives.json"

MODULE_PAGES = [
    {"pageId": "dashboard", "label": "Dashboard",       "path": "/dashboard"},
    {"pageId": "settings",  "label": "Settings",        "path": "/settings"},
]


# ---------------------------------------------------------------------------
# Middleware: inject SCRIPT_NAME so url_for() generates correct prefixed URLs
# ---------------------------------------------------------------------------
@app.before_request
def _set_script_name():
    prefix = request.environ.get("HTTP_X_FORWARDED_PREFIX", "").strip().rstrip("/")
    if prefix and not prefix.startswith("/"):
        prefix = "/" + prefix
    if not prefix and APPLICATION_ROOT:
        prefix = APPLICATION_ROOT
    if prefix:
        request.environ["SCRIPT_NAME"] = prefix


@app.route("/favicon.ico")
def favicon():
    """Serve PNG favicon at /favicon.ico for browsers that request the legacy path."""
    return send_from_directory(app.static_folder, "favicon.png", mimetype="image/png")


register_h2s_cdi_auth(
    app,
    public_paths=("/static", "/favicon.ico", "/login", "/logout", "/api/internal/live-events"),
    path_page_rules=[
        ("/dashboard", "dashboard"),
        ("/settings", "settings"),
        ("/", "dashboard"),
    ],
    default_page=None,
)


@app.context_processor
def _inject_globals():
    """Expose script_root, portal URLs, and CDI dashboard link to every template."""
    script_root = (request.environ.get("SCRIPT_NAME") or "").rstrip("/")
    return {
        "script_root": script_root,
        "portal_url": get_portal_url(),
        "cdi_dashboard_url": get_portal_dashboard_url(),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _user_info():
    """Return (display_name, role_str, is_admin) from the portal JWT payload."""
    user = getattr(g, "user", None) or {}
    name = user.get("name") or user.get("email", "")
    is_admin = user.get("isAdmin", False)
    role = "admin" if is_admin else "viewer"
    return name, role, is_admin


def _load_pinned():
    try:
        if os.path.isfile(PINNED_FILE):
            with open(PINNED_FILE, encoding="utf-8") as fh:
                data = json.load(fh)
                return data.get("pinned", []) if isinstance(data, dict) else []
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _save_pinned(pinned_list):
    try:
        with open(PINNED_FILE, "w", encoding="utf-8") as fh:
            json.dump({"pinned": list(pinned_list)}, fh, indent=2)
    except OSError as e:
        logger.warning("Could not save pinned initiatives: %s", e)


def _get_df():
    """Load the dataframe using current session sheet settings or defaults."""
    sheet_url = session.get("sheet_url", DEFAULT_SHEET_URL)
    creds_path = session.get("credentials_path", DEFAULT_CREDENTIALS_PATH)
    sheet_id = extract_sheet_id(sheet_url)
    if not sheet_id:
        return None
    return cached_load_sheet(sheet_id, creds_path)


def _get_df_catalog():
    """
    Load the sheet used for initiative names (portal RBAC picker). No browser session.
    Override with EVENT_DASHBOARD_CATALOG_SHEET_URL / EVENT_DASHBOARD_CREDENTIALS_PATH if set.
    """
    sheet_url = (
        (os.environ.get("EVENT_DASHBOARD_CATALOG_SHEET_URL") or "").strip()
        or (os.environ.get("DEFAULT_SHEET_URL") or "").strip()
        or DEFAULT_SHEET_URL
    )
    creds_path = (
        (os.environ.get("EVENT_DASHBOARD_CREDENTIALS_PATH") or "").strip()
        or (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
        or DEFAULT_CREDENTIALS_PATH
    )
    sheet_id = extract_sheet_id(sheet_url)
    if not sheet_id:
        return None
    return cached_load_sheet(sheet_id, creds_path)


def _registration_secret_ok() -> bool:
    want = (
        (os.environ.get("H2S_CDI_REGISTRATION_SECRET") or "").strip()
        or (os.environ.get("JARVIS_REGISTRATION_SECRET") or "").strip()
    )
    got = (request.headers.get("x-module-secret") or request.headers.get("X-Module-Secret") or "").strip()
    return bool(want) and got == want


def _filter_events_for_user(events, user_payload: dict):
    """Filter initiatives using CDI JWT moduleEventAccess (configured in portal module permissions)."""
    allowed = get_module_event_allowlist(user_payload)
    if allowed is None:
        return events
    if not allowed:
        return []
    allow_set = set(allowed)
    return [e for e in events if e in allow_set]


# ---------------------------------------------------------------------------
# Routes: Auth (redirects only — portal owns the login page)
# ---------------------------------------------------------------------------
@app.route("/login")
def login():
    """Redirect stale /login bookmarks to the portal."""
    return redirect(f"{get_portal_url()}/login")


@app.route("/logout")
def logout():
    """Clear local session state and send the user back to the portal."""
    session.clear()
    return redirect(get_portal_dashboard_url())


# ---------------------------------------------------------------------------
# Routes: Dashboard
# ---------------------------------------------------------------------------
@app.route("/")
@app.route("/dashboard")
def dashboard():
    user, role, is_admin = _user_info()
    df = _get_df()
    all_events = get_event_list(df)
    events = _filter_events_for_user(all_events, g.user)
    pinned = _load_pinned()
    pinned = [p for p in pinned if p in events]

    selected = session.get("selected_event", "")
    if selected and selected not in events:
        selected = ""
        session["selected_event"] = ""

    sheet_url = session.get("sheet_url", DEFAULT_SHEET_URL)
    creds_path = session.get("credentials_path", DEFAULT_CREDENTIALS_PATH)

    return render_template(
        "dashboard.html",
        user=user,
        role=role,
        is_admin=is_admin,
        events=events,
        pinned=pinned,
        selected=selected,
        sheet_url=sheet_url,
        credentials_path=creds_path,
    )


# ---------------------------------------------------------------------------
# Routes: Settings
# ---------------------------------------------------------------------------
@app.route("/settings")
def settings():
    user, role, is_admin = _user_info()
    df = _get_df()
    all_events = get_event_list(df)
    events = _filter_events_for_user(all_events, g.user)
    config = load_event_dashboard_config()
    pinned = _load_pinned()
    pinned = [p for p in pinned if p in events]

    event_configs = []
    for name in events:
        entry = get_event_config(config, name)
        entry["name"] = name
        event_configs.append(entry)

    return render_template(
        "settings.html",
        user=user,
        role=role,
        is_admin=is_admin,
        events=events,
        pinned=pinned,
        event_configs=event_configs,
    )


@app.route("/settings/save", methods=["POST"])
def settings_save():
    if not g.user.get("isAdmin"):
        flash("Permission denied.", "error")
        return redirect(url_for("settings"))

    name = request.form.get("event_name", "").strip()
    if not name:
        flash("Invalid event name.", "error")
        return redirect(url_for("settings"))

    config = load_event_dashboard_config()
    config[name] = {
        "dashboard_link": request.form.get("dashboard_link", "").strip(),
        "admin_username": request.form.get("admin_username", "").strip(),
        "admin_password": request.form.get("admin_password", ""),
        "registration_target": int(request.form.get("registration_target", 0) or 0),
    }
    save_event_dashboard_config(config)
    flash(f"Settings saved for {name}.", "success")
    return redirect(url_for("settings"))


# ---------------------------------------------------------------------------
# API: Data
# ---------------------------------------------------------------------------
@app.route("/api/internal/live-events", methods=["GET"])
def api_internal_live_events():
    """
    Server-to-server: full initiative list for CDI Users → Configure access pickers.
    Secured with the same secret as module registration (x-module-secret header).
    """
    if not _registration_secret_ok():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    df = _get_df_catalog()
    if df is None:
        return jsonify(
            {
                "ok": False,
                "error": "no_sheet",
                "message": "Could not load the analytics sheet; set EVENT_DASHBOARD_CATALOG_SHEET_URL or DEFAULT_SHEET_URL and credentials.",
            }
        ), 200
    if df.empty:
        return jsonify({"ok": True, "events": []}), 200
    events = get_event_list(df)
    return jsonify({"ok": True, "events": events})


@app.route("/api/data")
def api_data():
    event = request.args.get("event", "").strip()
    if not event:
        return jsonify({"error": "No event specified"}), 400

    df = _get_df()
    if df is None or df.empty:
        return jsonify({"error": "No data available"}), 404

    all_events = get_event_list(df)
    events = _filter_events_for_user(all_events, g.user)
    if event not in events:
        return jsonify({"error": "Event not found"}), 404

    analytics = get_event_analytics(df, event)
    return jsonify(analytics)


@app.route("/api/select", methods=["POST"])
def api_select():
    data = request.get_json(silent=True) or {}
    event = data.get("event", "").strip()
    session["selected_event"] = event
    return jsonify({"ok": True, "selected": event})


@app.route("/api/pin", methods=["POST"])
def api_pin():
    data = request.get_json(silent=True) or {}
    event = data.get("event", "").strip()
    action = data.get("action", "pin")

    pinned = _load_pinned()
    if action == "pin" and event not in pinned:
        pinned.append(event)
    elif action == "unpin" and event in pinned:
        pinned.remove(event)
    _save_pinned(pinned)
    return jsonify({"ok": True, "pinned": pinned})


@app.route("/api/connect", methods=["POST"])
def api_connect():
    if not g.user.get("isAdmin"):
        return jsonify({"error": "Permission denied"}), 403

    data = request.get_json(silent=True) or {}
    sheet_url = data.get("sheet_url", "").strip()
    creds_path = data.get("credentials_path", "").strip() or DEFAULT_CREDENTIALS_PATH

    sheet_id = extract_sheet_id(sheet_url)
    if not sheet_id:
        return jsonify({"error": "Invalid Sheet ID or URL"}), 400

    df = cached_load_sheet(sheet_id, creds_path)
    if df is None:
        return jsonify({"error": "Failed to connect to sheet"}), 500

    session["sheet_url"] = sheet_url
    session["credentials_path"] = creds_path
    events = get_event_list(df)
    return jsonify({"ok": True, "event_count": len(events), "events": events})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3005))
    module_name = os.environ.get("MODULE_NAME", "Consolidated Event Dashboard")
    base_url = os.environ.get("BASE_URL", f"http://localhost:{port}")
    register_with_portal(MODULE_PAGES, module_name=module_name, base_url=base_url)
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
