from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel

GlucoseUnit = Literal["mg/dL", "mmol/L"]
TimeFormat = Literal["24h", "12h"]
DateFormat = Literal["YYYY-MM-DD", "MM/DD/YYYY", "DD/MM/YYYY"]


class UserPreferencesOut(BaseModel):
    preference_id: UUID
    auth_user_id: UUID
    language: str
    color_palette: str
    simplified_view_enabled: bool
    time_format: TimeFormat
    date_format: DateFormat
    default_glucose_unit: GlucoseUnit
    has_completed_onboarding: bool

    class Config:
        from_attributes = True


class UserPreferencesPatch(BaseModel):
    simplified_view_enabled: Optional[bool] = None
    time_format: Optional[TimeFormat] = None
    date_format: Optional[DateFormat] = None
    default_glucose_unit: Optional[GlucoseUnit] = None
