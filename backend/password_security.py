"""Password hashing and legacy verification helpers."""
import hashlib
import secrets

import bcrypt


BCRYPT_PREFIX = "$2"


def hash_password(password: str) -> str:
    """Hash a password for new accounts using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, stored_hash: str, salt: str = "") -> bool:
    """Verify bcrypt hashes and legacy SHA-256 hashes during migration."""
    if not stored_hash:
        return False
    if stored_hash.startswith(BCRYPT_PREFIX):
        try:
            return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
        except ValueError:
            return False
    if salt:
        legacy = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
    else:
        legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return secrets.compare_digest(legacy, stored_hash)


def needs_password_rehash(stored_hash: str) -> bool:
    """Return True when a successfully verified password should be upgraded."""
    return not stored_hash.startswith(BCRYPT_PREFIX)
