"""
RBAC and user management for the Event Analytics Dashboard.
Users are persisted in users.json. Passwords are hashed with SHA-256 + salt.
"""

import hashlib
import json
import logging
import os
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

AUTH_SALT = "event-dashboard-rbac-2024"
USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")

ROLE_PERMISSIONS = {
    "admin": {"view_dashboard", "edit_sheet", "connect", "manage_users"},
    "viewer": {"view_dashboard"},
}

# Seed users created on first run when users.json doesn't exist yet
_SEED_USERS = {
    "admin": {
        "password_hash": hashlib.sha256((AUTH_SALT + "h2s@2026").encode()).hexdigest(),
        "role": "admin",
        "allowed_events": [],
    },
    "viewer": {
        "password_hash": hashlib.sha256((AUTH_SALT + "viewer123").encode()).hexdigest(),
        "role": "viewer",
        "allowed_events": [],
    },
}


def _hash_password(password: str) -> str:
    return hashlib.sha256((AUTH_SALT + password).encode()).hexdigest()


def get_password_hash(password: str) -> str:
    return _hash_password(password)


# ---------------------------------------------------------------------------
# Persistent user store
# ---------------------------------------------------------------------------

def load_users() -> Dict:
    """Load the user store from users.json, seeding defaults if missing."""
    if not os.path.isfile(USERS_FILE):
        save_users(_SEED_USERS)
        return dict(_SEED_USERS)
    try:
        with open(USERS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
            if not isinstance(data, dict) or not data:
                save_users(_SEED_USERS)
                return dict(_SEED_USERS)
            for entry in data.values():
                entry.setdefault("allowed_events", [])
            return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read %s, seeding defaults: %s", USERS_FILE, exc)
        save_users(_SEED_USERS)
        return dict(_SEED_USERS)


def save_users(users: Dict) -> None:
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as fh:
            json.dump(users, fh, indent=2, ensure_ascii=False)
    except OSError as exc:
        logger.error("Could not write %s: %s", USERS_FILE, exc)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def verify_login(username: str, password: str) -> Tuple[bool, Optional[str]]:
    if not username or not password:
        return False, None
    username = username.strip().lower()
    users = load_users()
    if username not in users:
        return False, None
    entry = users[username]
    if entry["password_hash"] != _hash_password(password):
        return False, None
    return True, entry["role"]


def get_role(username: str) -> Optional[str]:
    username = username.strip().lower()
    users = load_users()
    if username not in users:
        return None
    return users[username]["role"]


def has_permission(role: str, permission: str) -> bool:
    perms = ROLE_PERMISSIONS.get(role, set())
    return permission in perms


def can_edit_sheet(role: str) -> bool:
    return has_permission(role, "edit_sheet") or has_permission(role, "connect")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def get_all_users() -> List[Dict]:
    """Return list of user dicts (without password hashes) for the management UI."""
    users = load_users()
    result = []
    for uname, entry in users.items():
        result.append({
            "username": uname,
            "role": entry["role"],
            "allowed_events": entry.get("allowed_events", []),
        })
    return result


def get_user_allowed_events(username: str) -> List[str]:
    """Return the allowed_events list for a user. Empty list means all events."""
    username = username.strip().lower()
    users = load_users()
    if username not in users:
        return []
    return users[username].get("allowed_events", [])


def create_user(
    username: str,
    password: str,
    role: str,
    allowed_events: Optional[List[str]] = None,
) -> Tuple[bool, str]:
    """Create a new user. Returns (success, message)."""
    username = username.strip().lower()
    if not username:
        return False, "Username cannot be empty."
    if not password:
        return False, "Password cannot be empty."
    if role not in ROLE_PERMISSIONS:
        return False, f"Invalid role: {role}"

    users = load_users()
    if username in users:
        return False, f"User '{username}' already exists."

    users[username] = {
        "password_hash": _hash_password(password),
        "role": role,
        "allowed_events": allowed_events or [],
    }
    save_users(users)
    return True, f"User '{username}' created."


def update_user(
    username: str,
    password: Optional[str] = None,
    role: Optional[str] = None,
    allowed_events: Optional[List[str]] = None,
) -> Tuple[bool, str]:
    """Update an existing user. Only provided fields are changed."""
    username = username.strip().lower()
    users = load_users()
    if username not in users:
        return False, f"User '{username}' not found."

    if role is not None:
        if role not in ROLE_PERMISSIONS:
            return False, f"Invalid role: {role}"
        users[username]["role"] = role

    if password is not None and password != "":
        users[username]["password_hash"] = _hash_password(password)

    if allowed_events is not None:
        users[username]["allowed_events"] = allowed_events

    save_users(users)
    return True, f"User '{username}' updated."


def remove_user_access(email: str) -> Tuple[bool, str]:
    """Remove a user's event-access restriction. They revert to seeing all events."""
    email = email.strip().lower()
    users = load_users()
    if email not in users:
        return False, f"No restriction found for '{email}'."
    del users[email]
    save_users(users)
    return True, f"Access restriction removed for '{email}'."


def delete_user(username: str, requesting_user: str) -> Tuple[bool, str]:
    """Delete a user. Cannot delete yourself or the last admin."""
    username = username.strip().lower()
    requesting_user = requesting_user.strip().lower()

    if username == requesting_user:
        return False, "You cannot delete your own account."

    users = load_users()
    if username not in users:
        return False, f"User '{username}' not found."

    if users[username]["role"] == "admin":
        admin_count = sum(1 for u in users.values() if u["role"] == "admin")
        if admin_count <= 1:
            return False, "Cannot delete the last admin user."

    del users[username]
    save_users(users)
    return True, f"User '{username}' deleted."


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2:
        print("Hash:", get_password_hash(sys.argv[1]))
    else:
        print("Usage: python auth.py <password>")
