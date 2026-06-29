"""
auth/ — Local authentication for LMU Pit Strategist.

Supports two login methods:
  1. Email + password (bcrypt-hashed, stored in local DB)
  2. Google OAuth (verified via Google ID token, user_id generated locally)

When a user logs in, they get a JWT signed with a local secret. The JWT
contains user_id and is used as a Bearer token for all API calls.

On the community cloud (Turso), users authenticate via:
  - For local-only users: their local user_id is used as the cloud
    user_id (no Google required to share data anonymously)
  - For Google users: their email is attached to the cloud user_id

Offline behavior:
  - All auth is local (no network needed to log in)
  - Passwords are stored in the local SQLite DB
  - JWT is signed locally, validated locally
  - Cloud sync only happens when online (see sync_queue.py)
"""

from .manager import AuthManager
from .db import User
from .crypto import hash_password, verify_password, create_jwt, decode_jwt
from .db import (
    init_auth_db,
    create_user,
    authenticate_user,
    get_user_by_id,
    get_user_by_email,
    get_user_by_google_id,
    update_last_login,
    delete_user,
    list_users,
    set_current_user,
    get_current_user,
    clear_current_user,
)

__all__ = [
    "AuthManager",
    "User",
    "hash_password",
    "verify_password",
    "create_jwt",
    "decode_jwt",
    "init_auth_db",
    "create_user",
    "authenticate_user",
    "get_user_by_id",
    "get_user_by_email",
    "update_last_login",
    "delete_user",
    "list_users",
    "set_current_user",
    "get_current_user",
    "clear_current_user",
]
