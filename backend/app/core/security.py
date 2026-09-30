"""Security helpers: password hashing, JWT, and at-rest token encryption.

Instagram access tokens are encrypted with Fernet (AES-128-CBC + HMAC)
before being written to the database, and are never sent to the frontend.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# JWT (our own app sessions)
# ---------------------------------------------------------------------------

ALGORITHM = "HS256"


def create_access_token(user_id: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Token encryption (Instagram access tokens at rest)
# ---------------------------------------------------------------------------


def _fernet() -> Fernet:
    key = settings.TOKEN_ENCRYPTION_KEY.strip()
    if not key:
        # Development fallback: derive a key from JWT secret so the app still
        # runs without extra setup. Production deployments MUST set
        # TOKEN_ENCRYPTION_KEY explicitly.
        raw = hashlib.sha256(
            ("dev-token-encryption:" + settings.JWT_SECRET).encode("utf-8")
        ).digest()
        import base64

        key = base64.urlsafe_b64encode(raw).decode("utf-8")
    return Fernet(key.encode("utf-8"))


def encrypt_token(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_token(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Stored Instagram token cannot be decrypted") from exc


# ---------------------------------------------------------------------------
# OAuth state (CSRF protection)
# ---------------------------------------------------------------------------


def generate_oauth_state() -> str:
    return secrets.token_urlsafe(32)


def hash_state(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()
