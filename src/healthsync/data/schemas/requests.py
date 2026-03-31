# backend/src/healthsync/data/schemas/requests.py

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Literal
from uuid import UUID
from datetime import datetime, date


# ---------------- Patients ----------------
class PatientCreate(BaseModel):
    auth_user_id: UUID
    email: EmailStr

    phn: str = Field(..., pattern=r"^\d{9}$")
    first_name: str
    last_name: str

    phone_number: Optional[str] = None
    address: str
    date_of_birth: date

    age: Optional[int] = None
    gender: Optional[Literal["M", "F", "OTHER"]] = None

    # Bio data fields (your schema has these; allow optional so UI/manual creates can omit)
    body_weight_lbs: Optional[float] = None
    height_inches: Optional[float] = None
    bmi: Optional[float] = None
    insulin_sensitivity: Optional[float] = None

    primary_clinician_id: Optional[UUID] = None
    clinic_id: Optional[UUID] = None


class PatientUpdate(BaseModel):
    email: Optional[EmailStr] = None

    phn: Optional[str] = Field(None, pattern=r"^\d{9}$")
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    phone_number: Optional[str] = None
    address: Optional[str] = None
    date_of_birth: Optional[date] = None

    age: Optional[int] = None
    gender: Optional[Literal["M", "F", "OTHER"]] = None

    body_weight_lbs: Optional[float] = None
    height_inches: Optional[float] = None
    bmi: Optional[float] = None
    insulin_sensitivity: Optional[float] = None

    primary_clinician_id: Optional[UUID] = None
    clinic_id: Optional[UUID] = None


class PatientSignupRequest(BaseModel):
    email: EmailStr
    password: str

    phn: str = Field(..., pattern=r"^\d{9}$")
    first_name: str
    last_name: str

    phone_number: Optional[str] = None
    address: str
    date_of_birth: date

    age: Optional[int] = None
    gender: Optional[Literal["M", "F", "OTHER"]] = None

    body_weight_lbs: Optional[float] = None
    height_inches: Optional[float] = None
    bmi: Optional[float] = None
    insulin_sensitivity: Optional[float] = None

    primary_clinician_id: Optional[UUID] = None
    clinic_id: Optional[UUID] = None


# ---------------- Devices ----------------
class DeviceCreate(BaseModel):
    patient_id: UUID

    # DB-required fields
    type: Literal["Dexcom", "LibreSensor"]
    serial_number: str = Field(..., min_length=3, max_length=100)

    # Optional fields
    model: Optional[str] = None
    status: Optional[Literal["ACTIVE", "INACTIVE", "DISCONNECTED", "RETIRED"]] = "ACTIVE"
    linked_app_name: Optional[str] = None
    app_id: Optional[UUID] = None
    last_sync_at: Optional[datetime] = None


class DeviceUpdate(BaseModel):
    type: Optional[Literal["Dexcom", "LibreSensor"]] = None
    model: Optional[str] = None
    serial_number: Optional[str] = Field(None, min_length=3, max_length=100)
    status: Optional[Literal["ACTIVE", "INACTIVE", "DISCONNECTED", "RETIRED"]] = None
    linked_app_name: Optional[str] = None
    app_id: Optional[UUID] = None
    last_sync_at: Optional[datetime] = None


# ------------- Glucose Readings ----------
class GlucoseReadingCreate(BaseModel):
    patient_id: UUID
    device_id: UUID

    timestamp: datetime
    value: float = Field(..., ge=20.0, le=600.0)

    unit: Literal["mg/dL", "mmol/L"] = "mg/dL"
    device_type: Literal["Libre", "Dexcom"]


class GlucoseReadingUpdate(BaseModel):
    timestamp: Optional[datetime] = None
    value: Optional[float] = Field(None, ge=20.0, le=600.0)
    unit: Optional[Literal["mg/dL", "mmol/L"]] = None
    device_type: Optional[Literal["Libre", "Dexcom"]] = None


# ------------- Clinician ----------
class ClinicianSignupRequest(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    license_number: str = Field(..., pattern=r"^\d{7}$")
    clinic_code: str = Field(..., pattern=r"^\d{5}$")
