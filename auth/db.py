"""
User storage and authentication in the local SQLite DB.

The `users` table replaces/extends the previous single-row `db_users`
table. We keep both for backward compatibility (db_users = the
anonymous community opt-in record, users = the authenticated local
account).

Schema:
  users (
    id TEXT PRIMARY KEY,           -- UUID
    email TEXT UNIQUE,             -- nullable (Google users have one)
    display_name TEXT NOT NULL,
    password_hash TEXT,            -- nullable (Google-only users have none)
    auth_provider TEXT NOT NULL,   -- 'email' or 'google'
    google_id TEXT,                -- nullable
    created_at TEXT NOT NULL,
    last_login_at TEXT,
    is_active INTEGER NOT NULL DEFAULT 1
  )

  active_session (
    user_id TEXT PRIMARY KEY,
    jwt_token TEXT NOT NULL,
    expires_at TEXT NOT NULL
  )
"""

import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from typing import Optional, List

import paths
from .crypto import hash_password, verify_password, create_jwt


# The local users DB lives next to laps DB so a single SQLite file
# can host both. Default: same file as laps DB.
def _users_db_path() -> str:
    return paths.data_path("lmu_pit_strategist.db")


@dataclass
class User:
    id: str
    email: Optional[str]
    display_name: str
    auth_provider: str
    google_id: Optional[str]
    created_at: str
    last_login_at: Optional[str]
    is_active: bool
    password_hash: Optional[str] = None  # bcrypt hash; Google users have None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "display_name": self.display_name,
            "auth_provider": self.auth_provider,
            "google_id": self.google_id,
            "created_at": self.created_at,
            "last_login_at": self.last_login_at,
            "is_active": self.is_active,
        }


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_users_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_auth_db() -> None:
    """Create the users + active_session tables if they don't exist."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE,
            display_name TEXT NOT NULL,
            password_hash TEXT,
            auth_provider TEXT NOT NULL DEFAULT 'email',
            google_id TEXT,
            created_at TEXT NOT NULL,
            last_login_at TEXT,
            is_active INTEGER NOT NULL DEFAULT 1
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS active_session (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            user_id TEXT,
            jwt_token TEXT,
            expires_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    # Ensure the singleton row exists (user_id/jwt empty until login)
    cur.execute("INSERT OR IGNORE INTO active_session (id, created_at) VALUES (1, '')")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_google ON users(google_id)
    """)
    conn.commit()
    conn.close()


# ── CRUD ─────────────────────────────────────────────────────────────────────

def create_user(
    email: Optional[str] = None,
    display_name: str = "",
    password: Optional[str] = None,
    auth_provider: str = "email",
    google_id: Optional[str] = None,
) -> User:
    """
    Create a new local user.

    Required:
      - email (for 'email' provider)
      - password (for 'email' provider)
      - display_name
    Optional:
      - google_id (for 'google' provider)
    """
    if not display_name:
        raise ValueError("display_name is required")
    if auth_provider == "email":
        if not email:
            raise ValueError("email is required for email auth")
        if not password:
            raise ValueError("password is required for email auth")
    if auth_provider == "google":
        if not google_id:
            raise ValueError("google_id is required for Google auth")

    user_id = str(uuid.uuid4())
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    pw_hash = hash_password(password) if password else None

    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users "
            "(id, email, display_name, password_hash, auth_provider, google_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, email, display_name, pw_hash, auth_provider, google_id, now),
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.close()
        raise ValueError(f"user with that email already exists: {e}")
    conn.close()

    return User(
        id=user_id, email=email, display_name=display_name,
        auth_provider=auth_provider, google_id=google_id,
        created_at=now, last_login_at=None, is_active=True,
    )


def authenticate_user(email: str, password: str) -> Optional[User]:
    """
    Verify email + password. Returns the User on success, None on failure.
    """
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM users WHERE email = ? AND is_active = 1",
        (email,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    if not verify_password(password, row["password_hash"] or ""):
        return None
    return _row_to_user(row)


def get_user_by_id(user_id: str) -> Optional[User]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return _row_to_user(row) if row else None


def get_user_by_email(email: str) -> Optional[User]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cur.fetchone()
    conn.close()
    return _row_to_user(row) if row else None


def get_user_by_google_id(google_id: str) -> Optional[User]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE google_id = ?", (google_id,))
    row = cur.fetchone()
    conn.close()
    return _row_to_user(row) if row else None


def update_last_login(user_id: str) -> None:
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET last_login_at = ? WHERE id = ?",
        (now, user_id),
    )
    conn.commit()
    conn.close()


def delete_user(user_id: str) -> bool:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def list_users() -> List[User]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [_row_to_user(r) for r in rows]


# ── Active session (single user logged in at a time on the same install) ─

def set_current_user(user_id: str) -> str:
    """
    Set the currently logged-in user and return a fresh JWT for them.
    Stores the token in the active_session singleton (id=1).
    """
    user = get_user_by_id(user_id)
    if not user:
        raise ValueError(f"user {user_id} not found")
    token = create_jwt(
        user_id=user.id, email=user.email,
        display_name=user.display_name,
        auth_provider=user.auth_provider,
    )
    expires_at = time.strftime(
        "%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() + 30 * 24 * 60 * 60)
    )
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE active_session SET user_id = ?, jwt_token = ?, expires_at = ?, created_at = ? "
        "WHERE id = 1",
        (user_id, token, expires_at, now),
    )
    if cur.rowcount == 0:
        # First time, insert
        cur.execute(
            "INSERT INTO active_session (id, user_id, jwt_token, expires_at, created_at) "
            "VALUES (1, ?, ?, ?, ?)",
            (user_id, token, expires_at, now),
        )
    cur.execute(
        "UPDATE users SET last_login_at = ? WHERE id = ?",
        (now, user_id),
    )
    conn.commit()
    conn.close()
    return token


def get_current_user() -> Optional[User]:
    """Return the currently logged-in user (or None if not logged in)."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM active_session WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    if not row or not row["user_id"]:
        return None
    return get_user_by_id(row["user_id"])


def get_current_token() -> Optional[str]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT jwt_token FROM active_session WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    if not row or not row["jwt_token"]:
        return None
    return row["jwt_token"]


def clear_current_user() -> None:
    """Log out: clear the active session (keeps the user record)."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE active_session SET user_id = NULL, jwt_token = NULL, expires_at = NULL "
        "WHERE id = 1"
    )
    conn.commit()
    conn.close()


# ── Helpers ─────────────────────────────────────────────────────────────────

def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        auth_provider=row["auth_provider"],
        google_id=row["google_id"],
        created_at=row["created_at"],
        last_login_at=row["last_login_at"],
        is_active=bool(row["is_active"]),
        password_hash=row["password_hash"],
    )
