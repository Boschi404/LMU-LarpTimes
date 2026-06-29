"""
AuthManager — high-level orchestration of login/logout/sync.

Wraps the lower-level db.py + crypto.py with a single entry point
for the rest of the app.
"""

import time
from typing import Optional

from .db import (
    create_user as _create_user,
    authenticate_user as _authenticate_user,
    get_user_by_google_id,
    create_user as _create_user_google,
    set_current_user,
    get_current_user,
    clear_current_user,
    update_last_login,
    User,
)
from .crypto import create_jwt, decode_jwt, hash_password


class AuthManager:
    """
    High-level auth API. Use this from the web server or the overlay.

    Flow:
      1. User opens app → AuthManager.get_current() returns None or User
      2. If None → show login screen
      3. User logs in with email/pw OR Google → AuthManager.login_*
      4. App stores the JWT, sends it as Bearer token on every API call
      5. Server validates token via AuthManager.verify_token()
    """

    @staticmethod
    def get_current() -> Optional[User]:
        """Return the locally logged-in user (or None if logged out)."""
        return get_current_user()

    @staticmethod
    def is_logged_in() -> bool:
        return get_current_user() is not None

    # ── Email + password login ──────────────────────────────────────────

    @staticmethod
    def register_email(email: str, password: str, display_name: str) -> User:
        """Create a new local account with email + password."""
        return _create_user(
            email=email, password=password,
            display_name=display_name, auth_provider="email",
        )

    @staticmethod
    def login_email(email: str, password: str) -> Optional[User]:
        """Verify credentials and start a session. Returns the User or None."""
        user = _authenticate_user(email, password)
        if not user:
            return None
        set_current_user(user.id)
        update_last_login(user.id)
        return user

    # ── Google login ───────────────────────────────────────────────────

    @staticmethod
    def login_google(google_id: str, email: Optional[str], display_name: str) -> User:
        """
        Log in (or register) a user via Google OAuth.

        google_id is the stable identifier from the Google ID token
        (the `sub` field). If we don't have a user with that google_id
        yet, we create one. The display_name and email are taken from
        the ID token claims.
        """
        existing = get_user_by_google_id(google_id)
        if existing:
            set_current_user(existing.id)
            update_last_login(existing.id)
            return existing
        # New Google user
        user = _create_user_google(
            email=email, display_name=display_name,
            auth_provider="google", google_id=google_id,
        )
        set_current_user(user.id)
        update_last_login(user.id)
        return user

    # ── Logout ────────────────────────────────────────────────────────

    @staticmethod
    def logout() -> None:
        clear_current_user()

    # ── Token ────────────────────────────────────────────────────────

    @staticmethod
    def get_token() -> Optional[str]:
        """Return the current user's JWT (for sending in API calls)."""
        from .db import get_current_token
        return get_current_token()

    @staticmethod
    def verify_token(token: str) -> Optional[User]:
        """
        Verify a JWT and return the user. Returns None if invalid.
        Used by the FastAPI server's auth middleware.
        """
        if not token:
            return None
        payload = decode_jwt(token)
        if not payload:
            return None
        from .db import get_user_by_id
        return get_user_by_id(payload.get("sub"))
