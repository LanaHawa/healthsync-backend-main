# backend/src/healthsync/data/schemas/models.py

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime, date


# --------------------------------------------------
# Patient (aligned with your Timescale/Postgres schema)
# --------------------------------------------------
class Patient(BaseModel):
    patient_id: UUID
    auth_user_id: UUID
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone_number: Optional[str] = None
    address: Optional[str] = None
    date_of_birth: date
    phn: Optional[str] = None

    # Optional bio data fields (from your updated schema)
    age: Optional[int] = None
    gender: Optional[str] = None
    body_weight_lbs: Optional[float] = None
    height_inches: Optional[float] = None
    bmi: Optional[float] = None
    insulin_sensitivity: Optional[float] = None

    primary_clinician_id: Optional[UUID] = None
    clinic_id: Optional[UUID] = None
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# routers expect this alias
PatientOut = Patient


# --------------------------------------------------
# Device (aligned with DB schema)
# --------------------------------------------------
class Device(BaseModel):
    device_id: UUID
    patient_id: UUID
    type: str
    serial_number: str
    model: Optional[str] = None
    status: str
    linked_app_name: Optional[str] = None
    app_id: Optional[UUID] = None
    last_sync_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --------------------------------------------------
# GlucoseReading (Timescale hypertable-compatible)
# --------------------------------------------------
class GlucoseReading(BaseModel):
    reading_id: UUID
    patient_id: UUID
    device_id: UUID
    timestamp: datetime
    value: float
    unit: str
    device_type: str
    acquired_at: Optional[datetime] = None

    class Config:
        from_attributes = True
