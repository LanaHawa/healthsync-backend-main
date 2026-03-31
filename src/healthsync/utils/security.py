from __future__ import annotations

from passlib.context import CryptContext
from typing import Optional


# bcrypt is production-safe.
# "auto" allows future hash upgrades without breaking existing users.
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)


def hash_password(password: str) -> str:
    """
    Hash a raw password using bcrypt.
    """
    if not password or not password.strip():
        raise ValueError("Password cannot be empty")

    return pwd_context.hash(password)


def verify_password(password: str, password_hash: Optional[str]) -> bool:
    """
    Verify raw password against stored hash.
    Safe against None values.
    """
    if not password_hash:
        return False

    try:
        return pwd_context.verify(password, password_hash)
    except Exception:
        # In case of corrupted hash or unexpected format
        return False
