from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from healthsync.db.connection import get_conn
from healthsync.auth.jwt import require_role
from healthsync.repositories.access_permissions import AccessPermissionsRepository
from healthsync.repositories.clinicians_repo import CliniciansRepository
from healthsync.repositories.patients import PatientsRepository


router = APIRouter(prefix="/access-permissions", tags=["access-permissions"])

repo = AccessPermissionsRepository()
clinicians_repo = CliniciansRepository()
patients_repo = PatientsRepository()


class RequestAccessBody(BaseModel):
    patient_id: str  # keep as str for now; later we can switch to UUID if you want


@router.post("/request")
def request_access(
    body: RequestAccessBody, user=Depends(require_role("CLINICIAN", "ADMIN"))
):
    with get_conn() as conn:
        clinician = clinicians_repo.get_by_auth_user_id(conn, str(user["user_id"]))
        if not clinician:
            raise HTTPException(status_code=404, detail="Clinician profile not found")
        clinician_id = str(clinician["clinician_id"])

        # ✅ Validate patient exists
        patient = patients_repo.get_by_id_with_conn(conn, body.patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        # Optional: block requesting access to deleted patient profiles
        if patient.get("deleted_at") is not None:
            raise HTTPException(status_code=400, detail="Patient profile is inactive")

        existing = repo.get_by_patient_and_clinician_with_conn(
            conn, body.patient_id, clinician_id
        )

        # If it doesn't exist, create REQUESTED
        if not existing:
            return repo.create_request_with_conn(conn, body.patient_id, clinician_id)

        status = (existing.get("status") or "").upper()

        # Already requested/approved → no-op
        if status in ("APPROVED", "REQUESTED"):
            return existing

        # Previously rejected or revoked → re-request (set back to REQUESTED)
        return repo.set_status_with_conn(
            conn, str(existing["permission_id"]), "REQUESTED"
        )


@router.get("/clinician/me")
def clinician_inbox(user=Depends(require_role("CLINICIAN", "ADMIN"))):
    with get_conn() as conn:
        clinician = clinicians_repo.get_by_auth_user_id(conn, str(user["user_id"]))
        if not clinician:
            raise HTTPException(status_code=404, detail="Clinician profile not found")
        clinician_id = str(clinician["clinician_id"])
        return repo.list_for_clinician_with_conn(conn, clinician_id)


@router.get("/patient/me")
def patient_inbox(user=Depends(require_role("PATIENT", "ADMIN"))):
    with get_conn() as conn:
        patient = patients_repo.get_by_auth_user_id_with_conn(
            conn, str(user["user_id"])
        )
        if not patient:
            raise HTTPException(status_code=404, detail="Patient profile not found")
        patient_id = str(patient["patient_id"])
        return repo.list_for_patient_with_conn(conn, patient_id)


@router.post("/{permission_id}/approve")
def approve(permission_id: str, user=Depends(require_role("PATIENT", "ADMIN"))):
    with get_conn() as conn:
        patient = patients_repo.get_by_auth_user_id_with_conn(
            conn, str(user["user_id"])
        )
        if not patient:
            raise HTTPException(status_code=404, detail="Patient profile not found")

        perm = repo.get_by_id_with_conn(conn, permission_id)
        if not perm:
            raise HTTPException(status_code=404, detail="Request not found")

        if str(perm["patient_id"]) != str(patient["patient_id"]):
            raise HTTPException(status_code=403, detail="Forbidden")

        # Allow approving from REQUESTED, REJECTED, or REVOKED (patient can change their mind)
        status = (perm.get("status") or "").upper()
        if status not in ("REQUESTED", "REJECTED", "REVOKED"):
            raise HTTPException(
                status_code=400, detail=f"Cannot approve when status is {status}"
            )

        return repo.set_status_with_conn(conn, permission_id, "APPROVED")


@router.post("/{permission_id}/reject")
def reject(permission_id: str, user=Depends(require_role("PATIENT", "ADMIN"))):
    with get_conn() as conn:
        patient = patients_repo.get_by_auth_user_id_with_conn(
            conn, str(user["user_id"])
        )
        if not patient:
            raise HTTPException(status_code=404, detail="Patient profile not found")

        perm = repo.get_by_id_with_conn(conn, permission_id)
        if not perm:
            raise HTTPException(status_code=404, detail="Request not found")

        if str(perm["patient_id"]) != str(patient["patient_id"]):
            raise HTTPException(status_code=403, detail="Forbidden")

        #  Only reject REQUESTED
        status = (perm.get("status") or "").upper()
        if status != "REQUESTED":
            raise HTTPException(
                status_code=400, detail=f"Cannot reject when status is {status}"
            )

        return repo.set_status_with_conn(conn, permission_id, "REJECTED")


@router.post("/{permission_id}/revoke")
def revoke(
    permission_id: str, user=Depends(require_role("PATIENT", "CLINICIAN", "ADMIN"))
):
    """
    Optional but recommended:
    - Patient can revoke an APPROVED permission
    - Clinician can revoke their own permission link
    """
    with get_conn() as conn:
        perm = repo.get_by_id_with_conn(conn, permission_id)
        if not perm:
            raise HTTPException(status_code=404, detail="Request not found")

        role = (user.get("role") or "").upper()
        user_id = str(user["user_id"])

        # Ownership checks
        if role in ("PATIENT", "ADMIN"):
            patient = patients_repo.get_by_auth_user_id_with_conn(conn, user_id)
            if role != "ADMIN":
                if not patient or str(perm["patient_id"]) != str(patient["patient_id"]):
                    raise HTTPException(status_code=403, detail="Forbidden")

        if role in ("CLINICIAN", "ADMIN"):
            clinician = clinicians_repo.get_by_auth_user_id(conn, user_id)
            if role != "ADMIN":
                if not clinician or str(perm["clinician_id"]) != str(
                    clinician["clinician_id"]
                ):
                    raise HTTPException(status_code=403, detail="Forbidden")

        status = (perm.get("status") or "").upper()
        if status != "APPROVED":
            raise HTTPException(
                status_code=400, detail=f"Cannot revoke when status is {status}"
            )

        return repo.set_status_with_conn(conn, permission_id, "REVOKED")
