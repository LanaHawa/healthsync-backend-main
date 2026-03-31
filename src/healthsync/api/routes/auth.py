# backend/src/healthsync/routes/auth.py

from fastapi import APIRouter, HTTPException, Depends
from psycopg2.errors import UniqueViolation
from pydantic import BaseModel, EmailStr

from healthsync.data.schemas.requests import (
    PatientSignupRequest,
    ClinicianSignupRequest,
)
from healthsync.services.auth_service import AuthService
from healthsync.db.connection import get_conn

from healthsync.repositories.clinics_repo import ClinicsRepository
from healthsync.repositories.clinicians_repo import CliniciansRepository
from healthsync.repositories.clinician_clinic_repo import ClinicianClinicRepository
from healthsync.repositories.auth_repo import AuthRepository
from healthsync.utils.security import hash_password, verify_password
from healthsync.auth.jwt import require_user


router = APIRouter(prefix="/auth", tags=["auth"])

auth_repo = AuthRepository()

service = AuthService()
clinics_repo = ClinicsRepository()
clinicians_repo = CliniciansRepository()
cc_repo = ClinicianClinicRepository()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/login")
def login(payload: LoginRequest):
    try:
        return service.login(payload.email.lower().strip(), payload.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/signup/patient", status_code=201)
def signup_patient(payload: PatientSignupRequest):
    """
    Patient signup is handled fully inside AuthService.
    Keep this thin to avoid breaking existing logic/endpoints.
    """
    try:
        return service.signup_patient(payload)

    except Exception as e:
        msg = str(e)
        # Covers common psycopg2 unique constraint messages for email
        if "auth_users_email_key" in msg or "duplicate key value" in msg:
            raise HTTPException(status_code=409, detail="Email already exists")
        raise HTTPException(status_code=500, detail=msg)


@router.post("/signup/clinician", status_code=201)
def signup_clinician(payload: ClinicianSignupRequest):
    """
    Clinician signup:
      1) validate clinic_code exists
      2) validate license_number uniqueness
      3) create auth_user (role=CLINICIAN)
      4) create clinicians row
      5) link clinician to clinic via clinician_clinic bridge
    """
    try:
        with get_conn() as conn:
            email = str(payload.email).lower().strip()
            clinic_code = str(payload.clinic_code).strip()
            license_number = str(payload.license_number).strip()

            # 1) clinic code must exist
            clinic = clinics_repo.get_by_code_with_conn(conn, clinic_code)
            if not clinic:
                raise HTTPException(status_code=400, detail="Invalid clinic code")

            # 2) license must be unique
            if clinicians_repo.exists_license_with_conn(conn, license_number):
                raise HTTPException(
                    status_code=409, detail="License number already in use"
                )

            # 3) create auth user (CLINICIAN)
            auth_user = AuthService.create_user_with_conn(
                conn,
                email=email,
                password=payload.password,
                role="CLINICIAN",
            )

            # 4) create clinician
            clinician = clinicians_repo.create_with_conn(
                conn,
                {
                    "auth_user_id": auth_user["user_id"],
                    "first_name": payload.first_name,
                    "last_name": payload.last_name,
                    "email": email,
                    "license_number": license_number,
                },
            )

            # 5) link clinician to clinic
            membership = cc_repo.link_with_conn(
                conn,
                clinician_id=str(clinician["clinician_id"]),
                clinic_id=str(clinic["clinic_id"]),
                role="CLINICIAN",
            )

            return {
                "user": auth_user,
                "clinician": clinician,
                "clinic": clinic,
                "membership": membership,
            }

    except UniqueViolation:
        # Usually covers duplicate email (auth_users.email) or license_number unique index
        raise HTTPException(
            status_code=409, detail="Duplicate value (email or license)"
        )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password", status_code=200)
def change_password(
    payload: ChangePasswordRequest,
    user=Depends(require_user),
):
    """
    Authenticated endpoint to change the caller's password.
    Verifies current_password before updating.
    """
    if len(payload.new_password) < 8:
        raise HTTPException(
            status_code=400, detail="New password must be at least 8 characters"
        )

    with get_conn() as conn:
        current_hash = auth_repo.get_password_hash(conn, str(user["user_id"]))
        if current_hash is None:
            raise HTTPException(status_code=404, detail="User not found")

        if not verify_password(payload.current_password, current_hash):
            raise HTTPException(status_code=401, detail="Current password is incorrect")

        new_hash = hash_password(payload.new_password)
        auth_repo.update_password(conn, str(user["user_id"]), new_hash)

    return {"message": "Password updated successfully"}
