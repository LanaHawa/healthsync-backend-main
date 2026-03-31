# backend/src/healthsync/api/routes/medications.py

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from healthsync.auth.jwt import require_role
from healthsync.db.connection import get_conn
from healthsync.repositories.patients import PatientsRepository
from healthsync.repositories.medications_repo import MedicationsRepository

router = APIRouter(prefix="/medications", tags=["medications"])
patients_repo = PatientsRepository()
repo = MedicationsRepository()


class MedicationCreate(BaseModel):
    name: str
    strength: str = ""
    form: str = ""
    route: str = ""
    start_date: str  # ISO date string e.g. "2024-01-15"
    end_date: Optional[str] = None


class MedicationPatch(BaseModel):
    name: Optional[str] = None
    strength: Optional[str] = None
    form: Optional[str] = None
    route: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


# ── Patient: read own medications ─────────────────────────────────────────────


@router.get("/me")
def list_my_medications(user=Depends(require_role("PATIENT"))):
    with get_conn() as conn:
        patient = patients_repo.get_by_auth_user_id_with_conn(
            conn, str(user["user_id"])
        )
        if not patient:
            raise HTTPException(status_code=404, detail="Patient profile not found")
        return repo.list_by_patient_with_conn(conn, UUID(str(patient["patient_id"])))


# ── Clinician: list a patient's medications ───────────────────────────────────


@router.get("/by-patient/{patient_id}")
def list_patient_medications(patient_id: UUID, user=Depends(require_role("CLINICIAN"))):
    return repo.list_by_patient(patient_id)


# ── Clinician: add a medication to a patient ──────────────────────────────────


@router.post("/by-patient/{patient_id}", status_code=201)
def add_patient_medication(
    patient_id: UUID,
    payload: MedicationCreate,
    user=Depends(require_role("CLINICIAN")),
):
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Medication name is required")
    return repo.add_for_patient(
        patient_id,
        name=name,
        strength=payload.strength or "",
        form=payload.form or "",
        route=payload.route or "",
        start_date=payload.start_date,
        end_date=payload.end_date,
    )


# ── Clinician: update a patient's medication entry ────────────────────────────


@router.patch("/by-patient/{patient_id}/{medication_link_id}")
def update_patient_medication(
    patient_id: UUID,
    medication_link_id: UUID,
    payload: MedicationPatch,
    user=Depends(require_role("CLINICIAN")),
):
    result = repo.update_for_patient(
        medication_link_id,
        patient_id,
        name=payload.name,
        strength=payload.strength,
        form=payload.form,
        route=payload.route,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Medication entry not found")
    return result


# ── Clinician: remove a medication from a patient ────────────────────────────


@router.delete("/by-patient/{patient_id}/{medication_link_id}")
def remove_patient_medication(
    patient_id: UUID,
    medication_link_id: UUID,
    user=Depends(require_role("CLINICIAN")),
):
    ok = repo.remove_for_patient(medication_link_id, patient_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Medication entry not found")
    return {"deleted": True}
