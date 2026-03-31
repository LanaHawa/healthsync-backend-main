from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from healthsync.auth.jwt import require_role
from healthsync.db.connection import get_conn
from healthsync.data.schemas.preferences import UserPreferencesOut, UserPreferencesPatch
from healthsync.repositories.preferences_repo import PreferencesRepository
from uuid import UUID

router = APIRouter(prefix="/preferences", tags=["preferences"])
repo = PreferencesRepository()


@router.get("/me", response_model=UserPreferencesOut)
def get_my_preferences(user=Depends(require_role("PATIENT", "CLINICIAN", "ADMIN"))):
    """Return the current user's preferences, creating defaults if none exist yet."""
    with get_conn() as conn:
        row = repo.get_or_create_with_conn(conn, UUID(str(user["user_id"])))
        if not row:
            raise HTTPException(status_code=500, detail="Failed to load preferences")
        return dict(row)


@router.patch("/me", response_model=UserPreferencesOut)
def update_my_preferences(
    payload: UserPreferencesPatch,
    user=Depends(require_role("PATIENT", "CLINICIAN", "ADMIN")),
):
    """Update one or more preference fields for the current user."""
    with get_conn() as conn:
        # Ensure row exists first
        repo.get_or_create_with_conn(conn, UUID(str(user["user_id"])))
        row = repo.update_with_conn(
            conn,
            auth_user_id=UUID(str(user["user_id"])),
            simplified_view_enabled=payload.simplified_view_enabled,
            time_format=payload.time_format,
            date_format=payload.date_format,
            default_glucose_unit=payload.default_glucose_unit,
        )
        if not row:
            raise HTTPException(status_code=500, detail="Failed to update preferences")
        return dict(row)
