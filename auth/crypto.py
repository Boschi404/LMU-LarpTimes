"""
Password hashing + JWT tokens for the local auth system.

Passwords are hashed with bcrypt (work factor 12, ~250ms per hash — slow
enough to defeat brute force, fast enough for login UX).

JWTs are signed with HS256 using a secret stored in .env (or generated
once and saved on first run). Tokens expire after 30 days.
"""

import os
import time
import secrets
import hashlib
from typing import Optional, Dict, Any

import bcrypt
import jwt


# Default expiration: 30 days
DEFAULT_JWT_EXPIRATION = 30 * 24 * 60 * 60


def _get_jwt_secret() -> str:
    """
    Return the JWT signing secret. Loaded from JWT_SECRET env var,
    falling back to a file in the user's data dir.
    """
    env = os.environ.get("JWT_SECRET")
    if env:
        return env
    # Fall back to a file
    import paths
    secret_path = paths.data_path("auth_secret.txt")
    if os.path.exists(secret_path):
        return open(secret_path).read().strip()
    # First run: generate and save
    secret = secrets.token_urlsafe(64)
    os.makedirs(os.path.dirname(secret_path), exist_ok=True)
    with open(secret_path, "w") as f:
        f.write(secret)
    return secret


def hash_password(plain: str) -> str:
    """
    Hash a plain-text password with bcrypt (work factor 12).
    Returns a string like '$2b$12$...' (bcrypt format).
    """
    if not plain:
        raise ValueError("password must not be empty")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Check that a plain password matches a bcrypt hash."""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_jwt(
    user_id: str,
    email: Optional[str] = None,
    display_name: Optional[str] = None,
    auth_provider: str = "email",
    expiration: int = DEFAULT_JWT_EXPIRATION,
) -> str:
    """
    Sign a JWT with the user's identity. The token is used as a
    Bearer token for API authentication.
    """
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "name": display_name,
        "provider": auth_provider,
        "iat": now,
        "exp": now + expiration,
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm="HS256")


def decode_jwt(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify and decode a JWT. Returns the payload dict, or None if
    the token is invalid or expired.
    """
    try:
        return jwt.decode(token, _get_jwt_secret(), algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, ValueError):
        return None


def fingerprint_password(plain: str) -> str:
    """
    Compute a non-reversible hash of a password for quick lookups
    (NOT a substitute for bcrypt — used only to check if a user
    has set the same password twice without exposing it).

    For now unused, kept for future migration helpers.
    """
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()
