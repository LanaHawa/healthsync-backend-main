# backend/src/healthsync/api/routes/prescriptions.py

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from healthsync.auth.jwt import require_role
from healthsync.db.connection import get_conn
from healthsync.repositories.patients import PatientsRepository
from healthsync.repositories.clinicians_repo import CliniciansRepository
from healthsync.repositories.prescriptions_repo import PrescriptionsRepository

router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])
patients_repo = PatientsRepository()
clinicians_repo = CliniciansRepository()
repo = PrescriptionsRepository()


class PrescriptionCreate(BaseModel):
    medication_name: Optional[str] = None
    dose: Optional[str] = None
    sig: Optional[str] = None


class PrescriptionUpdate(BaseModel):
    medication_name: Optional[str] = None
    dose: Optional[str] = None
    sig: Optional[str] = None


class PrescriptionItemCreate(BaseModel):
    medication_name: str
    dose: str
    sig: str
    duration: str


class PrescriptionItemUpdate(BaseModel):
    medication_name: Optional[str] = None
    dose: Optional[str] = None
    sig: Optional[str] = None
    duration: Optional[str] = None


# ── Patient: read own prescriptions (read-only) ───────────────────────────────


@router.get("/me")
def list_my_prescriptions(user=Depends(require_role("PATIENT"))):
    with get_conn() as conn:
        patient = patients_repo.get_by_auth_user_id_with_conn(
            conn, str(user["user_id"])
        )
        if not patient:
            raise HTTPException(status_code=404, detail="Patient profile not found")
    return repo.list_by_patient(UUID(str(patient["patient_id"])))


@router.get("/me/{prescription_id}")
def get_my_prescription(prescription_id: UUID, user=Depends(require_role("PATIENT"))):
    with get_conn() as conn:
        patient = patients_repo.get_by_auth_user_id_with_conn(
            conn, str(user["user_id"])
        )
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
    rx = repo.get_by_id(prescription_id)
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found")
    if str(rx["patient_id"]) != str(patient["patient_id"]):
        raise HTTPException(status_code=404, detail="Prescription not found")
    return rx


# ── Clinician endpoints ───────────────────────────────────────────────────────


@router.get("/by-patient/{patient_id}")
def list_patient_prescriptions(
    patient_id: UUID, user=Depends(require_role("CLINICIAN"))
):
    return repo.list_by_patient(patient_id)


@router.get("/{prescription_id}")
def get_prescription(prescription_id: UUID, user=Depends(require_role("CLINICIAN"))):
    rx = repo.get_by_id(prescription_id)
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found")
    return rx


@router.post("/by-patient/{patient_id}", status_code=201)
def create_prescription(
    patient_id: UUID,
    payload: PrescriptionCreate,
    user=Depends(require_role("CLINICIAN")),
):
    auth_user_id = str(user["user_id"])
    with get_conn() as conn:
        clinician = clinicians_repo.get_by_auth_user_id(conn, auth_user_id)
    if not clinician:
        raise HTTPException(status_code=404, detail="Clinician profile not found")
    clinician_id = UUID(str(clinician["clinician_id"]))
    clinician_name = f"Dr. {clinician['first_name']} {clinician['last_name']}".strip()
    return repo.create(
        patient_id=patient_id,
        clinician_id=clinician_id,
        clinician_name=clinician_name,
        medication_name=payload.medication_name,
        dose=payload.dose,
        sig=payload.sig,
    )


@router.post("/{prescription_id}/items", status_code=201)
def add_prescription_item(
    prescription_id: UUID,
    payload: PrescriptionItemCreate,
    user=Depends(require_role("CLINICIAN")),
):
    rx = repo.get_by_id(prescription_id)
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found")
    return repo.add_item(
        prescription_id=prescription_id,
        medication_name=payload.medication_name,
        dose=payload.dose,
        sig=payload.sig,
        duration=payload.duration,
    )


@router.patch("/{prescription_id}")
def update_prescription(
    prescription_id: UUID,
    payload: PrescriptionUpdate,
    user=Depends(require_role("CLINICIAN")),
):
    auth_user_id = str(user["user_id"])
    with get_conn() as conn:
        clinician = clinicians_repo.get_by_auth_user_id(conn, auth_user_id)
    if not clinician:
        raise HTTPException(status_code=404, detail="Clinician profile not found")
    clinician_id = UUID(str(clinician["clinician_id"]))
    updated = repo.update_prescription(
        prescription_id,
        clinician_id,
        medication_name=payload.medication_name,
        dose=payload.dose,
        sig=payload.sig,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Prescription not found")
    return updated


@router.patch("/{prescription_id}/items/{item_id}")
def update_prescription_item(
    prescription_id: UUID,
    item_id: UUID,
    payload: PrescriptionItemUpdate,
    user=Depends(require_role("CLINICIAN")),
):
    rx = repo.get_by_id(prescription_id)
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found")
    updated = repo.update_item(
        item_id,
        prescription_id,
        medication_name=payload.medication_name,
        dose=payload.dose,
        sig=payload.sig,
        duration=payload.duration,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Item not found")
    return updated


@router.delete("/{prescription_id}/items/{item_id}")
def delete_prescription_item(
    prescription_id: UUID,
    item_id: UUID,
    user=Depends(require_role("CLINICIAN")),
):
    ok = repo.delete_item(item_id, prescription_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"deleted": True}


@router.delete("/{prescription_id}")
def delete_prescription(
    prescription_id: UUID,
    user=Depends(require_role("CLINICIAN")),
):
    auth_user_id = str(user["user_id"])
    with get_conn() as conn:
        clinician = clinicians_repo.get_by_auth_user_id(conn, auth_user_id)
    if not clinician:
        raise HTTPException(status_code=404, detail="Clinician profile not found")
    clinician_id = UUID(str(clinician["clinician_id"]))
    ok = repo.delete_prescription(prescription_id, clinician_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Prescription not found")
    return {"deleted": True}
