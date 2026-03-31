"""
Business logic layer for glucose readings.
Handles complex operations, validations, and interactions with the repository.
"""

from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from psycopg2.errors import ForeignKeyViolation, UniqueViolation


from healthsync.db.connection import get_conn
from healthsync.repositories.glucose_readings_repo import GlucoseReadingsRepository
from healthsync.repositories.devices_repo import DevicesRepository
from healthsync.repositories.patients import PatientsRepository
from healthsync.utils.validators import (
    validate_glucose_value,
    validate_unit,
    validate_device_type,
)


class GlucoseReadingsService:
    """Service layer for glucose readings business logic
    Ochestrates between repositories and enforces business rules.
    """

    def __init__(self):
        self.readings_repo = GlucoseReadingsRepository()
        self.devices_repo = DevicesRepository()
        self.patients_repo = PatientsRepository()

    def get_patient_readings(
        self,
        patient_id: str,
        device_id: Optional[str] = None,
        from_ts: Optional[datetime] = None,
        to_ts: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get glucose readings for a patient with optional filters

        Args:
            patient_id: ID of the patient
            device_id: Optional filter by device ID
            from_ts: Optional filter for readings acquired after this timestamp
            to_ts: Optional filter for readings acquired before this timestamp
            limit: Max number of readings to return (None for unlimited)

        Returns:
            List of glucose readings matching the filters

        Raises:
            HTTPException 404 if patient not found
        """

        # Verify patient exists
        patient = self.patients_repo.get(patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        with get_conn() as conn:
            # If device_id filter is provided, verify it belongs to the patient
            if device_id:
                device = self.devices_repo.get_by_id_with_conn(conn, device_id)
                if not device:
                    raise HTTPException(status_code=404, detail="Device not found")
                if str(device["patient_id"]) != patient_id:
                    raise HTTPException(
                        status_code=400, detail="Device does not belong to the patient"
                    )

            return self.readings_repo.list_with_filters_with_conn(
                conn,
                patient_id=patient_id,
                device_id=device_id,
                from_ts=from_ts,
                to_ts=to_ts,
                limit=limit,
            )

    def create_reading(self, reading_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new glucose reading with validation

        Args:
            reading_data: Dict containing patient_id, device_id, timestamp, value, unit, device_type

        Returns:
            The created glucose reading record

        Raises:
            HTTPException 400 for validation errors
            HTTPException 404 if patient or device not found
            HTTPException 500 for other errors
        """

        # Validate required fields
        required_fields = [
            "patient_id",
            "device_id",
            "timestamp",
            "value",
            "unit",
            "device_type",
        ]
        for field in required_fields:
            if field not in reading_data:
                raise HTTPException(
                    status_code=400, detail=f"Missing required field: {field}"
                )

        with get_conn() as conn:
            try:
                # patient must exist
                patient = self.patients_repo.get_by_auth_user_id_with_conn(
                    conn, reading_data["patient_id"]
                )
                if not patient:
                    raise HTTPException(status_code=404, detail="Patient not found")

                # device must exist and belong to patient
                device = self.devices_repo.get_by_id_with_conn(
                    conn, reading_data["device_id"]
                )
                if not device:
                    raise HTTPException(status_code=404, detail="Device not found")
                if str(device["patient_id"]) != str(reading_data["patient_id"]):
                    raise HTTPException(
                        status_code=400,
                        detail="Device does not belong to specified patient",
                    )

                #  Validate unit and device_type
                unit = validate_unit(reading_data["unit"])
                device_type = validate_device_type(reading_data["device_type"])

                # Validate value range using the validate_glucose_value function which raises HTTPException if invalid
                value = validate_glucose_value(reading_data["value"])

                return self.readings_repo.create_with_conn(
                    conn,
                    {
                        "patient_id": reading_data["patient_id"],
                        "device_id": reading_data["device_id"],
                        "timestamp": reading_data["timestamp"],
                        "value": value,
                        "unit": unit,
                        "device_type": device_type,
                    },
                )

            except ForeignKeyViolation as e:
                # This should be caught by our explicit checks, but just in case
                raise HTTPException(
                    status_code=400, detail="Invalid patient_id or device_id"
                ) from e
            except UniqueViolation:
                raise HTTPException(
                    status_code=409,
                    detail="Duplicate reading (same patient_id, device_id, timestamp)",
                )

    def bulk_created_readings(self, readings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Bulk create glucose readings with validation

        Args:
            readings: List of dicts, each containing patient_id, device_id, timestamp, value, unit, device_type

        Returns:
            Dict with count of created readings and any errors encountered
        """
        with get_conn() as conn:
            success_count = 0
            errors = []

            for idx, reading_data in enumerate(readings):
                try:
                    # Validate required fields
                    required_fields = [
                        "patient_id",
                        "device_id",
                        "timestamp",
                        "value",
                        "unit",
                        "device_type",
                    ]
                    for field in required_fields:
                        if field not in reading_data:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Missing required field: {field}",
                            )

                    # patient must exist
                    patient = self.patients_repo.get_by_auth_user_id_with_conn(
                        conn, reading_data["patient_id"]
                    )
                    if not patient:
                        raise HTTPException(status_code=404, detail="Patient not found")
                    # device must exist and belong to patient
                    device = self.devices_repo.get_by_id_with_conn(
                        conn, reading_data["device_id"]
                    )
                    if not device:
                        raise HTTPException(status_code=404, detail="Device not found")
                    if str(device["patient_id"]) != str(reading_data["patient_id"]):
                        raise HTTPException(
                            status_code=400,
                            detail="Device does not belong to specified patient",
                        )
                    #  Validate unit and device_type
                    unit = validate_unit(reading_data["unit"])
                    device_type = validate_device_type(reading_data["device_type"])

                    # Validate value range using the validate_glucose_value function which raises HTTPException if invalid
                    value = validate_glucose_value(reading_data["value"])
                    self.readings_repo.create_with_conn(
                        conn,
                        {
                            "patient_id": reading_data["patient_id"],
                            "device_id": reading_data["device_id"],
                            "timestamp": reading_data["timestamp"],
                            "value": value,
                            "unit": unit,
                            "device_type": device_type,
                        },
                    )

                    success_count += 1

                except Exception as e:
                    errors.append(
                        {"index": idx, "reading": reading_data, "error": str(e)}
                    )
            conn.commit()

            return {
                "success_count": success_count,
                "error_count": len(errors),
                "errors": errors,
            }

    def get_reading_by_id(
        self, reading_id: str, timestamp: Optional[datetime] = None
    ) -> Optional[Dict[str, Any]]:
        """Get a glucose reading by its composite key (reading_id, timestamp)."""
        with get_conn() as conn:
            reading = self.readings_repo.get_by_id_with_conn(
                conn, reading_id, timestamp
            )
            if not reading:
                raise HTTPException(status_code=404, detail="Glucose reading not found")
            return reading

    def update_reading(
        self, reading_id: str, timestamp: datetime, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an existing glucose reading with validation."""
        with get_conn() as conn:
            # Verify the reading exists first using composite key
            existing = self.readings_repo.get_by_id_with_conn(
                conn, reading_id, timestamp
            )
            if not existing:
                raise HTTPException(status_code=404, detail="Glucose reading not found")

            validated_updates = {}

            if "value" in updates:
                validated_updates["value"] = validate_glucose_value(updates["value"])

            if "unit" in updates:
                validated_updates["unit"] = validate_unit(updates["unit"])

            if "device_type" in updates:
                validated_updates["device_type"] = validate_device_type(
                    updates["device_type"]
                )

            # Note: timestamp itself cannot be updated as it's part of the primary key

            if not validated_updates:
                raise HTTPException(
                    status_code=400, detail="No valid fields provided for update"
                )
            updated_reading = self.readings_repo.update_with_conn(
                conn, reading_id, timestamp, validated_updates
            )
            if not updated_reading:
                raise HTTPException(
                    status_code=404, detail="Glucose reading not found during update"
                )
            conn.commit()
            return updated_reading

    def delete_reading(
        self, reading_id: str, timestamp: Optional[datetime] = None
    ) -> bool:
        """Delete a glucose reading by its composite key (reading_id, timestamp)."""
        with get_conn() as conn:
            success = self.readings_repo.delete_with_conn(conn, reading_id, timestamp)
            if not success:
                raise HTTPException(status_code=404, detail="Glucose reading not found")
            conn.commit()
            return success

    def get_reading_statistics(
        self,
        patient_id: str,
        from_ts: Optional[datetime] = None,
        to_ts: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Calculate statistics for a patient's glucose readings.

        Args:
            patient_id: ID of the patient
            from_ts: Optional filter for readings acquired after this timestamp
            to_ts: Optional filter for readings acquired before this timestamp

        Returns:
            Dict containing count, average, min, max, and standard deviation of glucose values
        """
        # Set default time range to last 30 days if not provided
        if not to_ts:
            to_ts = datetime.utcnow()
        if not from_ts:
            from_ts = to_ts - timedelta(days=30)

        # Verify patient exists
        patient = self.patients_repo.get(patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        patient_readings = self.get_patient_readings(
            patient_id=patient_id,
            from_ts=from_ts,
            to_ts=to_ts,
            limit=None,  # Get all readings in the time range for accurate stats
        )

        if not patient_readings:
            return {
                "total_count": 0,
                "average_value": None,
                "min": None,
                "max": None,
                "std_dev": None,
                "time_range_percent": None,
                "time_below_range_percent": None,
                "time_above_range_percent": None,
                "period_start": from_ts.isoformat(),
                "period_end": to_ts.isoformat(),
            }

        values = [reading["value"] for reading in patient_readings]
        count = len(values)

        average = round(sum(values) / count, 2) if count > 0 else 0

        min_value = min(values) if values else None
        max_value = max(values) if values else None

        std_dev = (
            round((sum((x - average) ** 2 for x in values) / count) ** 0.5, 2)
            if count > 0
            else None
        )

        # Time in range calculations (assuming target range is 70-180 mg/dL)
        target_low = 70
        target_high = 180

        in_range_count = sum(1 for v in values if target_low <= v <= target_high)
        below_range_count = sum(1 for v in values if v < target_low)
        above_range_count = sum(1 for v in values if v > target_high)

        return {
            "total_count": count,
            "average_value": average,
            "min": min_value,
            "max": max_value,
            "std_dev": std_dev,
            "time_range_percent": round(in_range_count / count * 100, 2)
            if count > 0
            else None,
            "time_below_range_percent": round(below_range_count / count * 100, 2)
            if count > 0
            else None,
            "time_above_range_percent": round(above_range_count / count * 100, 2)
            if count > 0
            else None,
            "period_start": from_ts.isoformat(),
            "period_end": to_ts.isoformat(),
        }

    def verify_parent_access(
        self, patient_id: str, auth_user_id: str, role: str
    ) -> bool:
        """Verify the auth user has access to the patient's glucose readings based on their role"""
        role = role.upper()

        if role == "ADMIN":
            return True  # Admins have access to all patients

        with get_conn() as conn:
            if role == "CLINICIAN":
                patient = self.patients_repo.get_by_auth_user_id_with_conn(
                    conn, patient_id
                )
                if not patient:
                    raise HTTPException(status_code=404, detail="Patient not found")
                return str(patient["primary_clinician_id"]) == auth_user_id

            if role == "PATIENT":
                patient = self.patients_repo.get_by_auth_user_id_with_conn(
                    conn, auth_user_id
                )
                if not patient:
                    raise HTTPException(
                        status_code=404, detail="Patient profile not found"
                    )
                return str(patient["patient_id"]) == patient_id
