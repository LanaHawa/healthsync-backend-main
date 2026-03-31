# backend/src/healthsync/routes/glucose_readings.py

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from pydantic import BaseModel, Field

from healthsync.db.connection import get_conn

from healthsync.utils.validators import (
    validate_device_type,
    validate_glucose_value,
    validate_unit,
)

from healthsync.auth.jwt import require_role
from healthsync.services.glucose_r_service import GlucoseReadingsService
from healthsync.repositories.patients import PatientsRepository


router = APIRouter(prefix="/glucose-readings", tags=["glucose"])
glucose_service = GlucoseReadingsService()
patients_repo = PatientsRepository()


class GlucoseReadingBase(BaseModel):
    """Base schema for glucose readings."""

    timestamp: datetime
    value: float = Field(
        ..., ge=20.0, le=600.0, description="Glucose value in mg/dL or mmol/L"
    )  # sanity check based on typical glucose ranges
    unit: str = Field(
        default="mg/dL", pattern=r"^(mg/dL|mmol/L)$"
    )  # 'mg/dL' | 'mmol/L'
    device_type: str = Field(
        default="Libre", pattern=r"^(Libre|Dexcom)$"
    )  # 'Libre' | 'Dexcom'


class GlucoseReading(BaseModel):
    """Schema for glucose reading response. Matches the DB fields."""

    reading_id: str
    patient_id: str
    device_id: str
    timestamp: datetime
    value: float
    unit: str
    device_type: Optional[str] = None
    source_type: Optional[str] = None
    acquired_at: datetime

    class Config:
        from_attr = True  # allow creating from DB dicts with snake_case keys


class GlucoseReadingCreate(GlucoseReadingBase):
    """Schema for creating a glucose reading. Matches the expected request body."""

    patient_id: str
    device_id: str


class GlucoseReadingUpdate(BaseModel):
    """Schema for updating a glucose reading. All fields optional.
    Note: timestamp cannot be updated as it's part of the composite primary key.
    """

    value: Optional[float] = Field(
        None, ge=20.0, le=600.0, description="Glucose value in mg/dL or mmol/L"
    )  # sanity check
    unit: Optional[str] = Field(None, pattern=r"^(mg/dL|mmol/L)$")  # 'mg/dL' | 'mmol/L'
    device_type: Optional[str] = Field(
        None, pattern=r"^(Libre|Dexcom)$"
    )  # 'Libre' | 'Dexcom'


class GlucoseStatistics(BaseModel):
    """Schema for glucose statistics response."""

    total_count: int
    average_value: Optional[float]
    min: Optional[float]
    max: Optional[float]
    std_dev: Optional[float]
    time_range_percent: Optional[float]
    time_below_range_percent: Optional[float]
    time_above_range_percent: Optional[float]
    period_start: str
    period_end: str


@router.get("", response_model=list[GlucoseReading])
def list_readings(
    patient_id: Optional[str] = Query(None, description="Filter by patient ID"),
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    from_ts: Optional[datetime] = Query(
        None, description="Filter readings from this timestamp"
    ),
    to_ts: Optional[datetime] = Query(
        None, description="Filter readings until this timestamp"
    ),
    limit: Optional[int] = Query(
        None,
        ge=1,
        le=100000,
        description="Maximum number of readings to return. None returns all readings.",
    ),
    current_user=Depends(require_role("CLINICIAN", "PATIENT", "ADMIN")),
):
    """
    - **PATIENT**: can only read their own readings (patient_id forced to self)
    - **CLINICIAN**: can view readings for any patient, with optional filters
    - **ADMIN**: can view readings for any patient, with optional filters
    """
    role = (current_user.get("role") or "").upper()

    # If PATIENT role, auto-detect their patient_id from token or database
    if role == "PATIENT":
        # First, try to get patient_id from the JWT token
        patient_id = current_user.get("patient_id")

        # If not in token, query database
        if not patient_id:
            patient = patients_repo.get_by_auth_user_id(str(current_user["user_id"]))
            if not patient:
                raise HTTPException(status_code=404, detail="Patient profile not found")
            patient_id = str(patient["patient_id"])
    elif not patient_id:
        # For CLINICIAN/ADMIN, patient_id is required
        raise HTTPException(
            status_code=400,
            detail="patient_id is required for CLINICIAN and ADMIN roles",
        )

    return glucose_service.get_patient_readings(
        patient_id=patient_id,
        device_id=device_id,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
    )


@router.get("/statistics", response_model=GlucoseStatistics)
def get_reading_statistics(
    patient_id: Optional[str] = Query(
        None, description="Patient ID to calculate statistics for"
    ),
    from_ts: Optional[datetime] = Query(
        None, description="Start of time range for statistics"
    ),
    to_ts: Optional[datetime] = Query(
        None, description="End of time range for statistics"
    ),
    current_user=Depends(require_role("CLINICIAN", "PATIENT", "ADMIN")),
):
    """
    Get statistics about a patient's glucose readings over a specified time range.
    - **PATIENT**: can only view their own statistics (patient_id auto-detected from token)
    - **CLINICIAN**: can view statistics for any patient (must provide patient_id)
    - **ADMIN**: can view statistics for any patient (must provide patient_id)
    """
    role = (current_user.get("role") or "").upper()

    # If PATIENT role, auto-detect their patient_id from token
    if role == "PATIENT":
        # First, try to get patient_id from the JWT token
        patient_id = current_user.get("patient_id")

        # If not in token, query database
        if not patient_id:
            with get_conn() as conn:
                patient = patients_repo.get_by_auth_user_id_with_conn(
                    conn, str(current_user["user_id"])
                )
                if not patient:
                    raise HTTPException(
                        status_code=404, detail="Patient profile not found"
                    )
                patient_id = str(patient["patient_id"])
    elif not patient_id:
        # For CLINICIAN/ADMIN, patient_id is required
        raise HTTPException(
            status_code=400,
            detail="patient_id is required for CLINICIAN and ADMIN roles",
        )

    return glucose_service.get_reading_statistics(
        patient_id=patient_id,
        from_ts=from_ts,
        to_ts=to_ts,
    )


@router.get("/{reading_id}", response_model=GlucoseReading)
def get_glucose_reading(
    reading_id: str,
    timestamp: Optional[datetime] = Query(
        None,
        description="Reading timestamp (ISO format). If not provided, returns most recent reading with this ID.",
    ),
    current_user: dict = Depends(require_role("CLINICIAN", "PATIENT", "ADMIN")),
):
    """
    Get a specific glucose reading by composite key (reading_id, timestamp).
    If timestamp not provided, returns the most recent reading with that ID.

    - **PATIENT**: Can only view their own readings
    - **CLINICIAN**: Can view their patients' reading
    - **ADMIN**: Can view any reading
    """
    reading = glucose_service.get_reading_by_id(reading_id, timestamp)

    # Verify access based on role
    glucose_service.verify_parent_access(
        patient_id=reading["patient_id"],
        auth_user_id=current_user.get("user_id"),
        role=current_user.get("role"),
    )

    return reading


@router.post("", response_model=GlucoseReading, status_code=201)
def create_glucose_reading(
    payload: GlucoseReadingCreate,
    current_user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    """
    Clinician/Admin can insert readings (for seeding/testing).
    In production, these would usually come from an ingestion pipeline/device sync.
    """
    return glucose_service.create_reading(payload.dict())


@router.put("/{reading_id}", response_model=GlucoseReading)
def update_glucose_reading(
    reading_id: str,
    payload: GlucoseReadingUpdate,
    timestamp: datetime = Query(
        ..., description="Reading timestamp (ISO format) - required for composite key"
    ),
    current_user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    """
    Update an existing glucose reading by composite key (reading_id, timestamp).

    - **CLINICIAN**: Can update readings for their patients
    - **ADMIN**: Can update any reading

    At least one field must be provided in the payload to update.
    Note: timestamp itself cannot be updated as it's part of the primary key.
    """
    # Convert Pydantic model to a dict, excluding the unset fields
    updates = payload.dict(exclude_unset=True)

    # Remove timestamp from updates if present (can't update PK component)
    if "timestamp" in updates:
        del updates["timestamp"]

    if not updates:
        raise HTTPException(
            status_code=400, detail="At least one field must be provided for update"
        )

    # Verify reading exists and check access
    reading = glucose_service.get_reading_by_id(reading_id, timestamp)
    glucose_service.verify_parent_access(
        patient_id=reading["patient_id"],
        auth_user_id=current_user.get("user_id"),
        role=current_user.get("role"),
    )

    return glucose_service.update_reading(reading_id, timestamp, updates)


@router.delete("/{reading_id}", status_code=204)
def delete_glucose_reading(
    reading_id: str,
    timestamp: Optional[datetime] = Query(
        None,
        description="Reading timestamp (ISO format). If not provided, deletes all readings with this ID.",
    ),
    current_user=Depends(require_role("ADMIN")),
):
    """
    Delete a glucose reading by composite key (reading_id, timestamp).
    If timestamp not provided, deletes ALL readings with that reading_id (use with caution).

    - **ADMIN**: Can delete any reading
    """
    # Verify reading exists before deletion
    reading = glucose_service.get_reading_by_id(reading_id, timestamp)

    glucose_service.delete_reading(reading_id, timestamp)
    return None
