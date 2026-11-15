import base64
import hashlib

from passlib.context import CryptContext

from .config import settings

# pbkdf2_sha256 is pure-python (no native bcrypt build needed) and secure.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


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
