# backend/src/healthsync/routes/clinicians.py

from pydantic import BaseModel
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from psycopg2.extras import RealDictCursor
from healthsync.db.connection import get_conn
from healthsync.repositories.clinicians_repo import CliniciansRepository
from healthsync.repositories.clinician_clinic_repo import ClinicianClinicRepository
from healthsync.repositories.clinics_repo import ClinicsRepository
from healthsync.auth.jwt import require_role


router = APIRouter(prefix="/clinicians", tags=["clinicians"])
repo = CliniciansRepository()
cc_repo = ClinicianClinicRepository()
clinics_repo = ClinicsRepository()


class _ClinicianEmailUpdate(BaseModel):
    email: str


class _ClinicLinkRequest(BaseModel):
    clinic_code: str


@router.get("/me")
def get_my_clinician_profile(user=Depends(require_role("CLINICIAN"))):
    """
    Clinician views their own profile.
    """
    with get_conn() as conn:
        row = repo.get_by_auth_user_id(conn, str(user["user_id"]))
        if not row:
            raise HTTPException(status_code=404, detail="Clinician profile not found")
        return row


@router.patch("/me")
def update_my_clinician_profile(
    payload: _ClinicianEmailUpdate,
    user=Depends(require_role("CLINICIAN")),
):
    """Clinician updates their own email."""
    with get_conn() as conn:
        clinician = repo.get_by_auth_user_id(conn, str(user["user_id"]))
        if not clinician:
            raise HTTPException(status_code=404, detail="Clinician profile not found")
        updated = repo.update_email_with_conn(
            conn, str(clinician["clinician_id"]), payload.email.strip()
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Clinician not found")
        return updated


@router.get("/me/clinics")
def get_my_clinics(user=Depends(require_role("CLINICIAN"))):
    """List all clinics the authenticated clinician is linked to."""
    with get_conn() as conn:
        clinician = repo.get_by_auth_user_id(conn, str(user["user_id"]))
        if not clinician:
            raise HTTPException(status_code=404, detail="Clinician profile not found")
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT c.clinic_id, c.name, c.address, c.clinic_code
                FROM clinics c
                JOIN clinician_clinic cc ON cc.clinic_id = c.clinic_id
                WHERE cc.clinician_id = %s
                ORDER BY c.name;
                """,
                (str(clinician["clinician_id"]),),
            )
            return cur.fetchall()


@router.post("/me/clinics")
def add_my_clinic(
    payload: _ClinicLinkRequest,
    user=Depends(require_role("CLINICIAN")),
):
    """Find a clinic by 5-digit code and link it to the authenticated clinician."""
    with get_conn() as conn:
        clinician = repo.get_by_auth_user_id(conn, str(user["user_id"]))
        if not clinician:
            raise HTTPException(status_code=404, detail="Clinician profile not found")
        clinic = clinics_repo.get_by_code_with_conn(conn, payload.clinic_code.strip())
        if not clinic:
            raise HTTPException(
                status_code=404, detail="No clinic found with that code"
            )
        cc_repo.link_with_conn(
            conn,
            str(clinician["clinician_id"]),
            str(clinic["clinic_id"]),
        )
        return {
            "clinic_id": str(clinic["clinic_id"]),
            "name": clinic["name"],
            "address": clinic.get("address"),
            "clinic_code": clinic["clinic_code"],
        }


@router.delete("/me/clinics/{clinic_id}")
def remove_my_clinic(clinic_id: str, user=Depends(require_role("CLINICIAN"))):
    """Unlink a clinic from the authenticated clinician."""
    with get_conn() as conn:
        clinician = repo.get_by_auth_user_id(conn, str(user["user_id"]))
        if not clinician:
            raise HTTPException(status_code=404, detail="Clinician profile not found")
        ok = cc_repo.unlink_with_conn(conn, str(clinician["clinician_id"]), clinic_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Clinic link not found")
        return {"unlinked": True}


@router.get("/{clinician_id}")
def get_clinician(clinician_id: str):
    """
    No schema changes needed here.
    This endpoint simply fetches a clinician by clinician_id.
    """
    with get_conn() as conn:
        row = repo.get_by_id_with_conn(conn, clinician_id)
        if not row:
            raise HTTPException(status_code=404, detail="Clinician not found")
        return row
