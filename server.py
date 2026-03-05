"""
Flask application for the Event Analytics Dashboard.
Replaces the Streamlit app with full HTML/CSS/JS control.
"""

import json
import logging
import os
import sys
from datetime import timedelta
from functools import wraps

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from auth import verify_login, can_edit_sheet
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
app.permanent_session_lifetime = timedelta(weeks=1)

PINNED_FILE = "pinned_initiatives.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


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


# ---------------------------------------------------------------------------
# Routes: Auth
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("authenticated"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        ok, role = verify_login(username, password)
        if ok:
            session.permanent = True
            session["authenticated"] = True
            session["user"] = username.lower()
            session["role"] = role
            logger.info("User '%s' logged in (role=%s)", username, role)
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    user = session.get("user", "unknown")
    session.clear()
    logger.info("User '%s' logged out", user)
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Routes: Dashboard
# ---------------------------------------------------------------------------
@app.route("/")
@login_required
def dashboard():
    user = session.get("user", "")
    role = session.get("role", "viewer")
    is_admin = can_edit_sheet(role)

    df = _get_df()
    events = get_event_list(df)
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
@login_required
def settings():
    user = session.get("user", "")
    role = session.get("role", "viewer")
    is_admin = can_edit_sheet(role)

    df = _get_df()
    events = get_event_list(df)
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
@login_required
def settings_save():
    role = session.get("role", "viewer")
    if not can_edit_sheet(role):
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
@app.route("/api/data")
@login_required
def api_data():
    event = request.args.get("event", "").strip()
    if not event:
        return jsonify({"error": "No event specified"}), 400

    df = _get_df()
    if df is None or df.empty:
        return jsonify({"error": "No data available"}), 404

    events = get_event_list(df)
    if event not in events:
        return jsonify({"error": "Event not found"}), 404

    analytics = get_event_analytics(df, event)
    return jsonify(analytics)


@app.route("/api/select", methods=["POST"])
@login_required
def api_select():
    data = request.get_json(silent=True) or {}
    event = data.get("event", "").strip()
    session["selected_event"] = event
    return jsonify({"ok": True, "selected": event})


@app.route("/api/pin", methods=["POST"])
@login_required
def api_pin():
    data = request.get_json(silent=True) or {}
    event = data.get("event", "").strip()
    action = data.get("action", "pin")  # "pin" or "unpin"

    pinned = _load_pinned()
    if action == "pin" and event not in pinned:
        pinned.append(event)
    elif action == "unpin" and event in pinned:
        pinned.remove(event)
    _save_pinned(pinned)
    return jsonify({"ok": True, "pinned": pinned})


@app.route("/api/connect", methods=["POST"])
@login_required
def api_connect():
    role = session.get("role", "viewer")
    if not can_edit_sheet(role):
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
    app.run(host="0.0.0.0", port=3005, debug=True)
