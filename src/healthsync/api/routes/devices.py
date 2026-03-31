# backend/src/healthsync/routes/devices.py

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from healthsync.auth.jwt import require_role
from healthsync.db.connection import get_conn
from healthsync.repositories.devices_repo import DevicesRepository
from healthsync.repositories.patients import PatientsRepository


router = APIRouter(prefix="/devices", tags=["devices"])

devices_repo = DevicesRepository()
patients_repo = PatientsRepository()


# ---------- Schemas ----------
class DeviceCreateBody(BaseModel):
    patient_id: str
    type: str  # 'Dexcom' | 'LibreSensor'
    serial_number: str
    model: Optional[str] = None
    status: Optional[str] = "ACTIVE"  # ACTIVE | INACTIVE | DISCONNECTED | RETIRED
    linked_app_name: Optional[str] = None
    app_id: Optional[str] = None


class DeviceUpdateBody(BaseModel):
    type: Optional[str] = None
    serial_number: Optional[str] = None
    model: Optional[str] = None
    status: Optional[str] = None
    linked_app_name: Optional[str] = None
    last_sync_at: Optional[str] = None  # ISO string
    app_id: Optional[str] = None


# ---------- Helpers ----------
_ALLOWED_DEVICE_TYPES = {"Dexcom", "LibreSensor"}
_ALLOWED_DEVICE_STATUS = {"ACTIVE", "INACTIVE", "DISCONNECTED", "RETIRED"}


def _validate_device_type(value: str) -> str:
    v = (value or "").strip()
    if v not in _ALLOWED_DEVICE_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid device type. Allowed: {sorted(_ALLOWED_DEVICE_TYPES)}")
    return v


def _validate_device_status(value: str) -> str:
    v = (value or "").strip().upper()
    if v not in _ALLOWED_DEVICE_STATUS:
        raise HTTPException(status_code=400, detail=f"Invalid device status. Allowed: {sorted(_ALLOWED_DEVICE_STATUS)}")
    return v


# ---------- Routes ----------
@router.get("")
def list_devices(
    patient_id: Optional[str] = Query(default=None),
    user=Depends(require_role("CLINICIAN", "PATIENT", "ADMIN")),
):
    """
    - ADMIN/CLINICIAN can list all or filter by patient_id
    - PATIENT can only list their own devices (patient_id is ignored unless it matches self)
    """
    with get_conn() as conn:
        role = (user.get("role") or "").upper()

        if role == "PATIENT":
            patient = patients_repo.get_by_auth_user_id_with_conn(conn, str(user["user_id"]))
            if not patient:
                raise HTTPException(status_code=404, detail="Patient profile not found")
            my_patient_id = str(patient["patient_id"])
            return devices_repo.list_by_patient_with_conn(conn, my_patient_id)

        # clinician/admin
        if patient_id:
            return devices_repo.list_by_patient_with_conn(conn, patient_id)
        return devices_repo.list_all_with_conn(conn)


@router.get("/{device_id}")
def get_device(
    device_id: str,
    user=Depends(require_role("CLINICIAN", "PATIENT", "ADMIN")),
):
    """
    - ADMIN/CLINICIAN can fetch any device
    - PATIENT can only fetch their own device
    """
    with get_conn() as conn:
        device = devices_repo.get_by_id_with_conn(conn, device_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        role = (user.get("role") or "").upper()
        if role == "PATIENT":
            patient = patients_repo.get_by_auth_user_id_with_conn(conn, str(user["user_id"]))
            if not patient:
                raise HTTPException(status_code=404, detail="Patient profile not found")
            if str(device["patient_id"]) != str(patient["patient_id"]):
                raise HTTPException(status_code=403, detail="Forbidden")

        return device


@router.post("", status_code=201)
def create_device(
    payload: DeviceCreateBody,
    user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    """
    Clinician/Admin creates a device for a patient.
    """
    with get_conn() as conn:
        # Validate patient exists
        patient = patients_repo.get_by_id_with_conn(conn, payload.patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        device_type = _validate_device_type(payload.type)
        status = _validate_device_status(payload.status or "ACTIVE")

        return devices_repo.create_with_conn(
            conn,
            {
                "patient_id": payload.patient_id,
                "type": device_type,
                "serial_number": payload.serial_number.strip(),
                "model": payload.model,
                "status": status,
                "linked_app_name": payload.linked_app_name,
                "app_id": payload.app_id,
            },
        )


@router.put("/{device_id}")
def update_device(
    device_id: str,
    payload: DeviceUpdateBody,
    user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    with get_conn() as conn:
        existing = devices_repo.get_by_id_with_conn(conn, device_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Device not found")

        updates = {}

        if payload.type is not None:
            updates["type"] = _validate_device_type(payload.type)

        if payload.status is not None:
            updates["status"] = _validate_device_status(payload.status)

        if payload.serial_number is not None:
            sn = payload.serial_number.strip()
            if not sn:
                raise HTTPException(status_code=400, detail="serial_number cannot be empty")
            updates["serial_number"] = sn

        if payload.model is not None:
            updates["model"] = payload.model

        if payload.linked_app_name is not None:
            updates["linked_app_name"] = payload.linked_app_name

        if payload.last_sync_at is not None:
            # repository should cast; keep as string here
            updates["last_sync_at"] = payload.last_sync_at

        if payload.app_id is not None:
            updates["app_id"] = payload.app_id

        return devices_repo.update_with_conn(conn, device_id, updates)


@router.delete("/{device_id}", status_code=204)
def delete_device(
    device_id: str,
    user=Depends(require_role("ADMIN")),
):
    """
    Only ADMIN can delete devices (safer default).
    """
    with get_conn() as conn:
        ok = devices_repo.delete_with_conn(conn, device_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Device not found")
        return None
