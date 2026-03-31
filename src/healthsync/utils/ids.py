from __future__ import annotations

import uuid
from typing import Union


def new_uuid() -> str:
    """
    Generate a new UUID4 string.
    Use this when DB columns are UUID type (recommended).
    """
    return str(uuid.uuid4())


def new_uuid_obj() -> uuid.UUID:
    """
    Generate a new UUID4 object.
    Useful when working directly with UUID-typed Pydantic models.
    """
    return uuid.uuid4()


def new_id() -> str:
    """
    Backwards-compatible alias used across the codebase.
    """
    return new_uuid()


def is_uuid(value: Union[str, uuid.UUID]) -> bool:
    """
    Return True if value is a valid UUID string or UUID object.
    """
    if isinstance(value, uuid.UUID):
        return True

    try:
        uuid.UUID(str(value))
        return True
    except Exception:
        return False
