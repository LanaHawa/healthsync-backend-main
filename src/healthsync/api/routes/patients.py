# backend/src/healthsync/routes/patients.py

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel

from healthsync.db.connection import get_conn
from healthsync.data.schemas import PatientCreate, PatientUpdate, PatientOut
from healthsync.repositories.patients import PatientsRepository
from healthsync.auth.jwt import require_role
from healthsync.repositories.clinicians_repo import CliniciansRepository
from healthsync.repositories.access_permissions import AccessPermissionsRepository


class _PatientSelfUpdate(BaseModel):
    """Fields a patient is allowed to update on their own profile."""

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    address: Optional[str] = None
    body_weight_lbs: Optional[float] = None
    height_inches: Optional[float] = None
    bmi: Optional[float] = None
    insulin_sensitivity: Optional[float] = None


class _ClinicianPatientUpdate(BaseModel):
    """Fields a clinician with APPROVED access may update on a patient profile."""

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    address: Optional[str] = None
    body_weight_lbs: Optional[float] = None
    height_inches: Optional[float] = None
    bmi: Optional[float] = None
    insulin_sensitivity: Optional[float] = None


router = APIRouter(prefix="/patients", tags=["patients"])

repo = PatientsRepository()
clinicians_repo = CliniciansRepository()
access_repo = AccessPermissionsRepository()


# ----------------------------
# Clinician/Admin only
# ----------------------------
@router.get("", response_model=List[PatientOut])
def list_patients(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    # MVP: allow clinicians/admins to list patients (no access_permissions filter here)
    return repo.list(limit=limit, offset=offset)


# ----------------------------
# Search by PHN (Clinician/Admin only)
# Uses JWT -> auth user -> clinician_id
# Returns access status for each patient for THAT clinician
# ----------------------------
@router.get("/search")
def search_patients(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    with get_conn() as conn:
        clinician = clinicians_repo.get_by_auth_user_id(conn, str(user["user_id"]))
        if not clinician:
            raise HTTPException(status_code=404, detail="Clinician profile not found")

        clinician_id = str(clinician["clinician_id"])

        rows = repo.search_by_query(q=q, limit=limit)

        results = []
        for p in rows:
            patient_id = str(p["patient_id"])

            perm = access_repo.get_by_patient_and_clinician_with_conn(
                conn, patient_id, clinician_id
            )
            status = perm["status"] if perm else "NONE"

            city = None
            if p.get("address"):
                city = (p.get("address") or "").split(",")[0].strip() or None

            phn_last4 = None
            if p.get("phn"):
                phn_last4 = str(p["phn"])[-4:]

            results.append(
                {
                    "patient_id": patient_id,
                    "first_name": p.get("first_name"),
                    "last_name": p.get("last_name"),
                    "city": city,
                    "phn_last4": phn_last4,
                    "access_status": status,
                    "permission_id": str(perm["permission_id"]) if perm else None,
                }
            )

        return results


# ----------------------------
# Patient: view their own profile
# ----------------------------
@router.get("/me", response_model=PatientOut)
def get_my_patient_profile(user=Depends(require_role("PATIENT"))):
    """
    Patient views their own complete profile including all biographical data.
    """
    # user["user_id"] is auth_users.user_id from JWT
    # get_by_auth_user_id now returns all columns including email, age, gender, BMI, etc.
    row = repo.get_by_auth_user_id(str(user["user_id"]))
    if not row:
        raise HTTPException(status_code=404, detail="Patient profile not found")
    return row


# ----------------------------
# Patient: update their own contact info
# ----------------------------
@router.patch("/me", response_model=PatientOut)
def update_my_patient_profile(
    payload: _PatientSelfUpdate,
    user=Depends(require_role("PATIENT")),
):
    me = repo.get_by_auth_user_id(str(user["user_id"]))
    if not me:
        raise HTTPException(status_code=404, detail="Patient profile not found")
    row = repo.update(
        UUID(str(me["patient_id"])), payload.model_dump(exclude_none=True)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Patient not found")
    return row


# ----------------------------
# Get patient by ID
# Allow:
# - PATIENT: only themselves
# - CLINICIAN: only if access_permissions APPROVED
# - ADMIN: allowed (MVP)
# ----------------------------
@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(
    patient_id: UUID,
    user=Depends(require_role("PATIENT", "CLINICIAN", "ADMIN")),
):
    role = (user.get("role") or "").upper()

    # PATIENT can only read themselves
    if role == "PATIENT":
        me = repo.get_by_auth_user_id(str(user["user_id"]))
        if not me:
            raise HTTPException(status_code=404, detail="Patient profile not found")
        if str(me["patient_id"]) != str(patient_id):
            raise HTTPException(status_code=403, detail="Forbidden")
        row = repo.get(patient_id)
        if not row:
            raise HTTPException(status_code=404, detail="Patient not found")
        return row

    # ADMIN can read any patient (MVP)
    if role == "ADMIN":
        row = repo.get(patient_id)
        if not row:
            raise HTTPException(status_code=404, detail="Patient not found")
        return row

    # CLINICIAN must have APPROVED access
    with get_conn() as conn:
        clinician = clinicians_repo.get_by_auth_user_id(conn, str(user["user_id"]))
        if not clinician:
            raise HTTPException(status_code=404, detail="Clinician profile not found")

        perm = access_repo.get_by_patient_and_clinician_with_conn(
            conn,
            str(patient_id),
            str(clinician["clinician_id"]),
        )
        if not perm or (perm["status"] != "APPROVED"):
            raise HTTPException(status_code=403, detail="Access not approved")

    row = repo.get(patient_id)
    if not row:
        raise HTTPException(status_code=404, detail="Patient not found")
    return row


@router.patch("/{patient_id}/vitals", response_model=PatientOut)
def update_patient_vitals(
    patient_id: UUID,
    payload: _ClinicianPatientUpdate,
    user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    """Clinician with APPROVED access updates a patient's profile and vitals."""
    if (user.get("role") or "").upper() == "CLINICIAN":
        with get_conn() as conn:
            clinician = clinicians_repo.get_by_auth_user_id(conn, str(user["user_id"]))
            if not clinician:
                raise HTTPException(
                    status_code=404, detail="Clinician profile not found"
                )
            perm = access_repo.get_by_patient_and_clinician_with_conn(
                conn, str(patient_id), str(clinician["clinician_id"])
            )
            if not perm or perm["status"] != "APPROVED":
                raise HTTPException(status_code=403, detail="Access not approved")
    row = repo.update(patient_id, payload.model_dump(exclude_none=True))
    if not row:
        raise HTTPException(status_code=404, detail="Patient not found")
    return row


# ----------------------------
# Create/Update/Delete (admin-only for safety)
# (Patient/Clinician creation should happen via /auth/signup)
# ----------------------------
@router.post("", response_model=PatientOut, status_code=201)
def create_patient(payload: PatientCreate, user=Depends(require_role("ADMIN"))):
    return repo.create(payload.model_dump())


@router.patch("/{patient_id}", response_model=PatientOut)
def update_patient(
    patient_id: UUID, payload: PatientUpdate, user=Depends(require_role("ADMIN"))
):
    row = repo.update(patient_id, payload.model_dump())
    if not row:
        raise HTTPException(status_code=404, detail="Patient not found")
    return row


@router.delete("/{patient_id}")
def delete_patient(patient_id: UUID, user=Depends(require_role("ADMIN"))):
    ok = repo.delete(patient_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Patient not found")
    return {"deleted": True}
