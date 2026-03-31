# backend/src/healthsync/repositories/crud_helpers.py

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def clean_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    """Remove keys with None values (useful for PATCH/update payloads)."""
    return {k: v for k, v in d.items() if v is not None}


def build_set_clause(data: Dict[str, Any]) -> Tuple[str, List[Any]]:
    """
    Build a SQL SET clause for updates.
    Returns (sql_fragment, values)

    Example:
        {"name": "A", "age": 2} -> ("name=%s, age=%s", ["A", 2])
    """
    items = list(data.items())
    if not items:
        return "", []

    parts: List[str] = []
    values: List[Any] = []
    for key, value in items:
        parts.append(f"{key}=%s")
        values.append(value)

    return ", ".join(parts), values


def paginate(limit: int = 50, offset: int = 0, max_limit: int = 200) -> Tuple[int, int]:
    """Clamp pagination inputs to safe ranges."""
    limit = 50 if limit is None else int(limit)
    offset = 0 if offset is None else int(offset)

    limit = max(1, min(limit, max_limit))
    offset = max(0, offset)
    return limit, offset


# -----------------------------------------------------------------------------
# IMPORTANT: Your current routers expect the "functional" helpers that work for
# CSV/in-memory repos:
#   - find_one(rows, predicate, error_message)
#   - delete_one(rows, predicate, error_message)
#
# Your file currently has DB-oriented helpers with the same names, which breaks
# imports like:
#   from healthsync.repositories.crud_helpers import find_one, delete_one
# used in devices.py and glucose_readings.py
# -----------------------------------------------------------------------------

def find_one(rows: List[Any], predicate, not_found_message: str) -> Any:
    """
    Find and return the first element in `rows` that matches `predicate`.
    Raise ValueError with `not_found_message` if none found.
    This matches how your CSV/in-memory routers are using it.
    """
    for r in rows:
        if predicate(r):
            return r
    raise ValueError(not_found_message)


def delete_one(rows: List[Any], predicate, not_found_message: str) -> List[Any]:
    """
    Return a new list with the first matching element removed.
    Raise ValueError if nothing matched.
    """
    removed = False
    out: List[Any] = []
    for r in rows:
        if (not removed) and predicate(r):
            removed = True
            continue
        out.append(r)

    if not removed:
        raise ValueError(not_found_message)
    return out


# -----------------------------------------------------------------------------
# DB cursor rowcount helpers (keep these, but rename to avoid collisions)
# -----------------------------------------------------------------------------

def cursor_deleted(cursor) -> bool:
    """True if a DELETE affected one or more rows (DB cursor)."""
    return (cursor.rowcount or 0) > 0


def cursor_updated(cursor) -> bool:
    """True if an UPDATE affected one or more rows (DB cursor)."""
    return (cursor.rowcount or 0) > 0
