import base64
import hashlib
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from .config import settings

# pbkdf2_sha256 is pure-python (no native bcrypt build needed) and secure.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {"sub": subject, "exp": expire, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


def hash_agent_token(token: str) -> str:
    """One-way digest for extension pairing tokens. The raw token is shown to
    the user exactly once; only this digest is persisted (prefixed so legacy
    plaintext rows are distinguishable and upgraded on first use)."""
    return "sha256:" + hashlib.sha256(token.encode()).hexdigest()


def _fernet_key() -> bytes:
    """Derive a 32-byte Fernet key from the configured encryption_key (or the
    JWT secret_key as a fallback). Deterministic so existing ciphertexts survive
    restarts without a key-management service."""
    raw = settings.encryption_key or settings.secret_key
    digest = hashlib.sha256(raw.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_secret(value: str) -> str:
    """Encrypt a secret string (e.g. li_at cookie) for storage at rest."""
    from cryptography.fernet import Fernet

    return Fernet(_fernet_key()).encrypt(value.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a secret previously encrypted with encrypt_secret."""
    from cryptography.fernet import Fernet

    return Fernet(_fernet_key()).decrypt(ciphertext.encode()).decode()
