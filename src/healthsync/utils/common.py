from __future__ import annotations

from typing import Any, Dict
import uuid
from datetime import datetime, date
from decimal import Decimal


def is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except Exception:
        return False


def to_dict(obj: Any) -> Dict[str, Any]:
    """
    Best-effort conversion to dict for:
      - Pydantic v2 models
      - Pydantic v1 models
      - dataclasses / regular objects

    Additionally:
      - Converts UUID to str
      - Converts datetime/date to ISO format
      - Converts Decimal to float
    """
    if obj is None:
        return {}

    if hasattr(obj, "model_dump"):  # Pydantic v2
        data = obj.model_dump()
    elif hasattr(obj, "dict"):  # Pydantic v1
        data = obj.dict()
    elif hasattr(obj, "__dict__"):
        data = dict(obj.__dict__)
    elif isinstance(obj, dict):
        data = obj
    else:
        return {"value": obj}

    return _normalize_values(data)


def _normalize_values(data: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}

    for key, value in data.items():
        if isinstance(value, uuid.UUID):
            normalized[key] = str(value)
        elif isinstance(value, (datetime, date)):
            normalized[key] = value.isoformat()
        elif isinstance(value, Decimal):
            normalized[key] = float(value)
        else:
            normalized[key] = value

    return normalized
