"""
Shared config: event dashboard links/credentials and default sheet/credentials paths.
Used by app.py and pages/1_Event_Settings.py.
"""

import json
import os
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Default sheet and credentials (shared with main app)
DEFAULT_CREDENTIALS_PATH = "vision-playground-423507-d803e8fdf430.json"
DEFAULT_SHEET_URL = "https://docs.google.com/spreadsheets/d/1LDJWBy2g1gtQK_u1vwwhMARnBIsijIMEgSC2wxBK72E/edit?gid=1918686024#gid=1918686024"

EVENT_DASHBOARD_CONFIG_FILE = "event_dashboard_config.json"


def load_event_dashboard_config() -> Dict[str, Dict[str, Any]]:
    """
    Load event dashboard config from JSON file.
    Returns dict: initiative_name -> {dashboard_link, admin_username, admin_password, registration_target (optional)}
    """
    try:
        if os.path.isfile(EVENT_DASHBOARD_CONFIG_FILE):
            with open(EVENT_DASHBOARD_CONFIG_FILE, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def save_event_dashboard_config(config: Dict[str, Dict[str, Any]]) -> None:
    """Write event dashboard config to JSON file."""
    try:
        with open(EVENT_DASHBOARD_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except OSError as e:
        logger.warning("Could not save event dashboard config: %s", e)


def get_event_config(config: Dict[str, Dict[str, Any]], initiative_name: str) -> Dict[str, Any]:
    """Return config for one initiative; missing keys are empty string or 0 for registration_target."""
    entry = config.get(initiative_name) or {}
    target = entry.get("registration_target")
    if target is not None and target != "":
        try:
            target = int(target)
        except (TypeError, ValueError):
            target = 0
    else:
        target = 0
    return {
        "dashboard_link": entry.get("dashboard_link") or "",
        "admin_username": entry.get("admin_username") or "",
        "admin_password": entry.get("admin_password") or "",
        "registration_target": target,
    }
