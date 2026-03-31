# backend/src/healthsync/routes/allergies.py

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from healthsync.auth.jwt import require_role
from healthsync.db.connection import get_conn
from healthsync.repositories.patients import PatientsRepository
from healthsync.repositories.allergies_repo import AllergiesRepository


router = APIRouter(prefix="/allergies", tags=["allergies"])
patients_repo = PatientsRepository()
repo = AllergiesRepository()


class AllergyCreate(BaseModel):
    allergen: str
    reaction: str | None = None
    severity: str  # "Low" | "Moderate" | "High"


@router.get("/me")
def list_my_allergies(user=Depends(require_role("PATIENT"))):
    with get_conn() as conn:
        patient = patients_repo.get_by_auth_user_id_with_conn(
            conn, str(user["user_id"])
        )
        if not patient:
            raise HTTPException(status_code=404, detail="Patient profile not found")

        return repo.list_by_patient_with_conn(conn, UUID(str(patient["patient_id"])))


@router.post("/me", status_code=201)
def add_my_allergy(payload: AllergyCreate, user=Depends(require_role("PATIENT"))):
    with get_conn() as conn:
        patient = patients_repo.get_by_auth_user_id_with_conn(
            conn, str(user["user_id"])
        )
        if not patient:
            raise HTTPException(status_code=404, detail="Patient profile not found")

        allergen = (payload.allergen or "").strip()
        if not allergen:
            raise HTTPException(status_code=400, detail="Allergen is required")

        severity = (payload.severity or "").strip()
        if severity not in ("Low", "Moderate", "High"):
            raise HTTPException(
                status_code=400,
                detail="Invalid severity (must be Low, Moderate, or High)",
            )

        reaction = payload.reaction.strip() if payload.reaction else None

        return repo.create_with_conn(
            conn,
            UUID(str(patient["patient_id"])),
            allergen,
            reaction,
            severity,
        )


@router.delete("/me/{allergy_id}")
def delete_my_allergy(allergy_id: UUID, user=Depends(require_role("PATIENT"))):
    with get_conn() as conn:
        patient = patients_repo.get_by_auth_user_id_with_conn(
            conn, str(user["user_id"])
        )
        if not patient:
            raise HTTPException(status_code=404, detail="Patient profile not found")

        ok = repo.delete_with_conn(conn, allergy_id, UUID(str(patient["patient_id"])))
        if not ok:
            raise HTTPException(status_code=404, detail="Allergy not found")

        return {"deleted": True}


# ── Clinician-side endpoints ──────────────────────────────────────────────────


@router.get("/by-patient/{patient_id}")
def list_patient_allergies(patient_id: UUID, user=Depends(require_role("CLINICIAN"))):
    return repo.list_by_patient(patient_id)


@router.post("/by-patient/{patient_id}", status_code=201)
def add_patient_allergy(
    patient_id: UUID,
    payload: AllergyCreate,
    user=Depends(require_role("CLINICIAN")),
):
    allergen = (payload.allergen or "").strip()
    if not allergen:
        raise HTTPException(status_code=400, detail="Allergen is required")
    severity = (payload.severity or "").strip()
    if severity not in ("Low", "Moderate", "High"):
        raise HTTPException(
            status_code=400, detail="Invalid severity (must be Low, Moderate, or High)"
        )
    reaction = payload.reaction.strip() if payload.reaction else None
    with get_conn() as conn:
        return repo.create_with_conn(conn, patient_id, allergen, reaction, severity)


@router.delete("/{allergy_id}")
def delete_patient_allergy(
    allergy_id: UUID, patient_id: UUID, user=Depends(require_role("CLINICIAN"))
):
    with get_conn() as conn:
        ok = repo.delete_with_conn(conn, allergy_id, patient_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Allergy not found")
    return {"deleted": True}
