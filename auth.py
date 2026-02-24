"""
Simple RBAC and login for the Event Analytics Dashboard.
Users and roles are defined in USER_STORE. Passwords are hashed with SHA-256 + salt.
"""

import hashlib
from typing import Optional, Tuple

# Salt for password hashing (change in production and use env var)
AUTH_SALT = "event-dashboard-rbac-2024"

# Role permissions: admin = full access, viewer = read-only dashboard
ROLE_PERMISSIONS = {
    "admin": {"view_dashboard", "edit_sheet", "connect"},
    "viewer": {"view_dashboard"},
}

# User store: username -> {"password_hash": str, "role": str}
# Passwords below are hashed for: admin/admin123, viewer/viewer123
# Generate new hash: hashlib.sha256((AUTH_SALT + "your_password").encode()).hexdigest()
USER_STORE = {
    "admin": {
        "password_hash": hashlib.sha256((AUTH_SALT + "h2s@2026").encode()).hexdigest(),
        "role": "admin",
    },
    "viewer": {
        "password_hash": hashlib.sha256((AUTH_SALT + "viewer123").encode()).hexdigest(),
        "role": "viewer",
    },
}


def _hash_password(password: str) -> str:
    return hashlib.sha256((AUTH_SALT + password).encode()).hexdigest()


def get_password_hash(password: str) -> str:
    """
    Return the stored hash for a password (uses AUTH_SALT).
    Use this to generate a hash when changing passwords:
        python -c "from auth import get_password_hash; print(get_password_hash('YourNewPassword'))"
    Then paste the output into USER_STORE[username]["password_hash"] in this file.
    """
    return _hash_password(password)


def verify_login(username: str, password: str) -> Tuple[bool, Optional[str]]:
    """
    Verify username and password. Returns (success, role).
    Role is None if login failed.
    """
    if not username or not password:
        return False, None
    username = username.strip().lower()
    if username not in USER_STORE:
        return False, None
    entry = USER_STORE[username]
    if entry["password_hash"] != _hash_password(password):
        return False, None
    return True, entry["role"]


def get_role(username: str) -> Optional[str]:
    """Return role for username, or None if user does not exist."""
    username = username.strip().lower()
    if username not in USER_STORE:
        return None
    return USER_STORE[username]["role"]


def has_permission(role: str, permission: str) -> bool:
    """Check if role has the given permission."""
    perms = ROLE_PERMISSIONS.get(role, set())
    return permission in perms


def can_edit_sheet(role: str) -> bool:
    """True if role can change sheet URL, credentials, and use Connect."""
    return has_permission(role, "edit_sheet") or has_permission(role, "connect")


if __name__ == "__main__":
    # Run: python auth.py <new_password>   to print the hash for that password.
    # Then copy the hash into USER_STORE["admin"] or USER_STORE["viewer"] in this file.
    import sys
    if len(sys.argv) >= 2:
        new_pass = sys.argv[1]
        print("Hash for your new password (copy into auth.py USER_STORE):")
        print(get_password_hash(new_pass))
    else:
        print("Usage: python auth.py <new_password>")
        print("Example: python auth.py MySecurePass123")
