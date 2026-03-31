# backend/src/healthsync/data/schemas/allergies.py

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, Literal
from uuid import UUID
from datetime import datetime


# Must match DB CHECK constraint: ('Low','Moderate','High')
Severity = Literal["Low", "Moderate", "High"]


class AllergyCreate(BaseModel):
    allergen: str = Field(..., min_length=1, max_length=120)
    reaction: Optional[str] = Field(default=None, max_length=200)
    severity: Severity

    class Config:
        json_schema_extra = {
            "example": {
                "allergen": "Peanuts",
                "reaction": "Hives and swelling",
                "severity": "High",
            }
        }


class AllergyOut(BaseModel):
    allergy_id: UUID
    patient_id: UUID
    allergen: str
    reaction: Optional[str] = None
    severity: Severity
    created_at: datetime

    class Config:
        from_attributes = True  # Enables ORM / DB row parsing (Pydantic v2 compatible)
        json_schema_extra = {
            "example": {
                "allergy_id": "2f9c5a16-4c4b-4d16-8f2f-9b1f5b0b3a12",
                "patient_id": "7b1c9c8a-9c2b-4f7f-91b1-123456789abc",
                "allergen": "Peanuts",
                "reaction": "Hives and swelling",
                "severity": "High",
                "created_at": "2026-02-14T12:34:56Z",
            }
        }
