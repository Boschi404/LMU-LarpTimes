"""
Tests for the local auth system (auth/).

Covers:
  - Password hashing: bcrypt format, verify, wrong password fails
  - JWT: create, decode, expired token returns None
  - User CRUD: create, lookup by id/email/google_id, update, delete, list
  - Session: set/get/clear current user
  - AuthManager: register, login (email + Google), logout
  - Edge cases: empty password, duplicate email, inactive user
"""

import os
import sys
import time
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Project root on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def fresh_auth_db(tmp_path, monkeypatch):
    """Reset the auth DB to a fresh tmp file for the test."""
    import paths
    # Redirect paths.data_path to tmp
    def fake_data_path(*parts):
        return str(tmp_path.joinpath(*parts))
    monkeypatch.setattr(paths, "data_path", fake_data_path)
    # JWT secret deterministic for test
    monkeypatch.setenv("JWT_SECRET", "test-secret-do-not-use-in-prod")
    # Clean any cached auth_secret.txt
    secret_file = tmp_path / "auth_secret.txt"
    if secret_file.exists():
        secret_file.unlink()
    # Init
    from auth import init_auth_db
    init_auth_db()
    return tmp_path


# ──────────────────────────────────────────────────────────────────────────────
# crypto.py
# ──────────────────────────────────────────────────────────────────────────────

def test_hash_password_returns_bcrypt_format(fresh_auth_db):
    from auth import hash_password
    h = hash_password("hello123")
    assert h.startswith("$2b$") or h.startswith("$2a$")
    assert len(h) >= 60


def test_hash_password_rejects_empty(fresh_auth_db):
    from auth import hash_password
    with pytest.raises(ValueError):
        hash_password("")


def test_verify_password_correct(fresh_auth_db):
    from auth import hash_password, verify_password
    h = hash_password("secret")
    assert verify_password("secret", h) is True


def test_verify_password_wrong(fresh_auth_db):
    from auth import hash_password, verify_password
    h = hash_password("secret")
    assert verify_password("wrong", h) is False


def test_verify_password_empty_inputs(fresh_auth_db):
    from auth import verify_password
    assert verify_password("", "x") is False
    assert verify_password("x", "") is False
    assert verify_password("", "") is False


def test_jwt_round_trip(fresh_auth_db):
    from auth import create_jwt, decode_jwt
    token = create_jwt("user-123", email="x@y.com", display_name="X")
    payload = decode_jwt(token)
    assert payload is not None
    assert payload["sub"] == "user-123"
    assert payload["email"] == "x@y.com"
    assert payload["name"] == "X"


def test_jwt_invalid_token_returns_none(fresh_auth_db):
    from auth import decode_jwt
    assert decode_jwt("not.a.token") is None
    assert decode_jwt("") is None


def test_jwt_expired(fresh_auth_db, monkeypatch):
    from auth import create_jwt, decode_jwt
    # Create a token that expired 1 second ago
    token = create_jwt("user-1", expiration=-1)
    assert decode_jwt(token) is None


# ──────────────────────────────────────────────────────────────────────────────
# db.py — user CRUD
# ──────────────────────────────────────────────────────────────────────────────

def test_create_user_email(fresh_auth_db):
    from auth import create_user, get_user_by_id
    u = create_user(email="a@b.com", password="pw", display_name="Alice")
    assert u.id
    assert u.email == "a@b.com"
    assert u.display_name == "Alice"
    assert u.auth_provider == "email"
    assert u.is_active is True
    # password_hash is not exposed on the User object (security)
    u_db = get_user_by_id(u.id)
    assert u_db.password_hash is not None
    assert u_db.password_hash.startswith("$2")


def test_create_user_google(fresh_auth_db):
    from auth import create_user, get_user_by_id
    u = create_user(
        email="g@g.com", display_name="Bob",
        auth_provider="google", google_id="google-sub-xyz",
    )
    assert u.auth_provider == "google"
    assert u.google_id == "google-sub-xyz"
    # Google users have no password
    u_db = get_user_by_id(u.id)
    assert u_db.password_hash is None


def test_create_user_duplicate_email_fails(fresh_auth_db):
    from auth import create_user
    create_user(email="dup@x.com", password="pw", display_name="X")
    with pytest.raises(ValueError):
        create_user(email="dup@x.com", password="pw", display_name="Y")


def test_create_user_missing_required_fields(fresh_auth_db):
    from auth import create_user
    with pytest.raises(ValueError):
        create_user(password="pw", display_name="X")  # no email
    with pytest.raises(ValueError):
        create_user(email="a@b.com", display_name="X")  # no pw
    with pytest.raises(ValueError):
        create_user(email="a@b.com", password="pw")  # no name
    with pytest.raises(ValueError):
        create_user(display_name="X", auth_provider="google")  # no google_id


def test_authenticate_user(fresh_auth_db):
    from auth import create_user, authenticate_user
    create_user(email="a@b.com", password="secret", display_name="A")
    assert authenticate_user("a@b.com", "secret") is not None
    assert authenticate_user("a@b.com", "wrong") is None
    assert authenticate_user("nobody@x.com", "secret") is None


def test_get_user_by_id_and_email(fresh_auth_db):
    from auth import create_user, get_user_by_id, get_user_by_email
    u = create_user(email="a@b.com", password="pw", display_name="A")
    assert get_user_by_id(u.id).id == u.id
    assert get_user_by_email("a@b.com").id == u.id
    assert get_user_by_id("nonexistent") is None
    assert get_user_by_email("nope@x.com") is None


def test_get_user_by_google_id(fresh_auth_db):
    from auth import create_user, get_user_by_google_id
    u = create_user(
        email="g@g.com", display_name="G",
        auth_provider="google", google_id="gid-1",
    )
    assert get_user_by_google_id("gid-1") is not None
    assert get_user_by_google_id("gid-1").id == u.id
    assert get_user_by_google_id("nonexistent") is None


def test_delete_user(fresh_auth_db):
    from auth import create_user, delete_user, get_user_by_id
    u = create_user(email="a@b.com", password="pw", display_name="A")
    assert delete_user(u.id) is True
    assert get_user_by_id(u.id) is None
    assert delete_user(u.id) is False


def test_list_users(fresh_auth_db):
    from auth import create_user, list_users
    for i in range(3):
        create_user(email=f"u{i}@x.com", password="pw", display_name=f"U{i}")
    users = list_users()
    assert len(users) == 3


def test_inactive_user_cannot_authenticate(fresh_auth_db):
    import sqlite3
    from auth import create_user, authenticate_user, get_user_by_id
    from auth.db import _get_conn
    u = create_user(email="a@b.com", password="pw", display_name="A")
    # Deactivate
    conn = _get_conn()
    conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (u.id,))
    conn.commit()
    conn.close()
    assert authenticate_user("a@b.com", "pw") is None


# ──────────────────────────────────────────────────────────────────────────────
# Active session
# ──────────────────────────────────────────────────────────────────────────────

def test_set_get_current_user(fresh_auth_db):
    from auth import create_user, set_current_user, get_current_user, clear_current_user
    u = create_user(email="a@b.com", password="pw", display_name="A")
    assert get_current_user() is None
    set_current_user(u.id)
    cur = get_current_user()
    assert cur.id == u.id
    clear_current_user()
    assert get_current_user() is None


def test_set_current_user_returns_jwt(fresh_auth_db):
    from auth import create_user, set_current_user, decode_jwt
    u = create_user(email="a@b.com", password="pw", display_name="A")
    token = set_current_user(u.id)
    payload = decode_jwt(token)
    assert payload["sub"] == u.id
    assert payload["email"] == "a@b.com"


def test_set_current_user_replaces_previous(fresh_auth_db):
    from auth import create_user, set_current_user, get_current_user, get_user_by_id
    u1 = create_user(email="a@b.com", password="pw", display_name="A")
    u2 = create_user(email="c@d.com", password="pw", display_name="C")
    set_current_user(u1.id)
    set_current_user(u2.id)
    cur = get_current_user()
    assert cur is not None
    assert cur.id == u2.id


def test_get_current_token(fresh_auth_db):
    from auth import create_user, set_current_user
    from auth.db import get_current_token as gct
    u = create_user(email="a@b.com", password="pw", display_name="A")
    set_current_user(u.id)
    assert gct() is not None
    assert len(gct()) > 50  # JWT is long


# ──────────────────────────────────────────────────────────────────────────────
# AuthManager
# ──────────────────────────────────────────────────────────────────────────────

def test_authmanager_register_and_login_email(fresh_auth_db):
    from auth import AuthManager
    u = AuthManager.register_email("a@b.com", "secret", "Alice")
    assert u.email == "a@b.com"
    logged = AuthManager.login_email("a@b.com", "secret")
    assert logged is not None
    assert AuthManager.is_logged_in()
    assert AuthManager.get_current().id == u.id


def test_authmanager_login_google_creates_new_user(fresh_auth_db):
    from auth import AuthManager
    g = AuthManager.login_google("gid-1", "g@g.com", "Bob")
    assert g.auth_provider == "google"
    assert g.google_id == "gid-1"
    # Logging in again returns the same user
    g2 = AuthManager.login_google("gid-1", "g@g.com", "Bob")
    assert g2.id == g.id


def test_authmanager_logout_clears_session(fresh_auth_db):
    from auth import AuthManager
    AuthManager.register_email("a@b.com", "secret", "A")
    AuthManager.login_email("a@b.com", "secret")
    assert AuthManager.is_logged_in()
    AuthManager.logout()
    assert not AuthManager.is_logged_in()


def test_authmanager_verify_token(fresh_auth_db):
    from auth import AuthManager
    u = AuthManager.register_email("a@b.com", "secret", "A")
    AuthManager.login_email("a@b.com", "secret")
    token = AuthManager.get_token()
    verified = AuthManager.verify_token(token)
    assert verified is not None
    assert verified.id == u.id
    # Invalid token
    assert AuthManager.verify_token("garbage.token.here") is None
    assert AuthManager.verify_token("") is None
    assert AuthManager.verify_token(None) is None
