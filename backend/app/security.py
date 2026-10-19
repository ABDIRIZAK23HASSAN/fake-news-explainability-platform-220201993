"""Password hashing (bcrypt) and JWT helpers (spec 8.1 / 8.15)."""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings


def hash_password(password: str) -> str:
    # bcrypt only looks at the first 72 bytes; hash a SHA-256 digest first so
    # long passphrases are not silently truncated.
    digest = hashlib.sha256(password.encode()).hexdigest().encode()
    return bcrypt.hashpw(digest, bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    digest = hashlib.sha256(password.encode()).hexdigest().encode()
    try:
        return bcrypt.checkpw(digest, hashed.encode())
    except ValueError:
        return False


def create_access_token(user_id: int, role: str) -> tuple[str, str, datetime]:
    jti = uuid.uuid4().hex
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    token = jwt.encode({"sub": str(user_id), "role": role, "jti": jti, "exp": exp},
                       settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, jti, exp


def decode_token(token: str) -> dict:
    """Raises jwt.PyJWTError (incl. ExpiredSignatureError) on any problem."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def new_reset_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def hash_reset_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def validate_password_strength(password: str) -> str | None:
    """Returns an error message or None if acceptable."""
    if len(password) < 8:
        return "Password is too short (minimum 8 characters)"
    if not any(c.isdigit() for c in password) or not any(c.isalpha() for c in password):
        return "Password must contain both letters and numbers"
    return None
