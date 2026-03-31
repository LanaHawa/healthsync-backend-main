from __future__ import annotations

from typing import Any, Dict

from psycopg2.errors import UniqueViolation
from fastapi import HTTPException

from healthsync.db.connection import get_conn
from healthsync.repositories.auth_repo import AuthRepository
from healthsync.repositories.patients import PatientsRepository
from healthsync.repositories.clinicians_repo import CliniciansRepository
from healthsync.utils.security import hash_password, verify_password
from healthsync.auth.jwt import create_access_token


class AuthService:
    def __init__(self) -> None:
        self.auth_repo = AuthRepository()
        self.patients_repo = PatientsRepository()
        self.clinicians_repo = CliniciansRepository()

    @staticmethod
    def create_user_with_conn(
        conn, email: str, password: str, role: str
    ) -> Dict[str, Any]:
        """
        Create an auth_users row inside an existing transaction.
        `password` here is RAW; we hash it before inserting.
        """
        pw_hash = hash_password(password)
        auth_repo = AuthRepository()
        return auth_repo.create_user(conn, email.lower().strip(), pw_hash, role=role)

    def signup_patient(self, payload) -> Dict[str, Any]:
        """
        Creates:
          - auth_users (PATIENT)
          - patients (linked via auth_user_id)

        Notes based on your latest schema:
          - patients.phone_number is OPTIONAL in SQL (DROP NOT NULL), so we allow None/""
          - patients.date_of_birth exists and is expected
          - patients.phn is CHAR(9) and unique (9 digits)
        """
        email = str(payload.email).lower().strip()
        pw_hash = hash_password(payload.password)

        # normalize optional phone (since DB allows NULL now)
        phone = getattr(payload, "phone_number", None)
        if isinstance(phone, str):
            phone = phone.strip()
            if phone == "":
                phone = None

        with get_conn() as conn:
            try:
                # 1) create auth user
                user = self.auth_repo.create_user(conn, email, pw_hash, role="PATIENT")

                # 2) create patient linked to auth user
                patient = self.patients_repo.create_with_conn(
                    conn,
                    {
                        "auth_user_id": user["user_id"],
                        "first_name": payload.first_name,
                        "last_name": payload.last_name,
                        "email": email,
                        "phone_number": phone,
                        "address": payload.address,
                        "phn": payload.phn,
                        "date_of_birth": payload.date_of_birth,
                        # optional
                        "primary_clinician_id": getattr(
                            payload, "primary_clinician_id", None
                        ),
                        "clinic_id": getattr(payload, "clinic_id", None),
                    },
                )

                return {"user": user, "patient": patient}

            except UniqueViolation:
                # could be auth_users.email, patients.phn
                raise HTTPException(
                    status_code=409, detail="Duplicate value (email or PHN)"
                )
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

    def login(self, email: str, password: str) -> Dict[str, Any]:
        email = email.lower().strip()

        with get_conn() as conn:
            user = self.auth_repo.get_user_by_email(conn, email)
            if not user:
                raise ValueError("Invalid email or password")

            if not verify_password(password, user["password_hash"]):
                raise ValueError("Invalid email or password")

            # Prepare token payload
            token_payload = {
                "user_id": str(user["user_id"]),
                "email": user["email"],
                "role": user["role"],
            }

            response: Dict[str, Any] = {
                "token_type": "bearer",
                "user_id": str(user["user_id"]),
                "email": user["email"],
                "role": user["role"],
            }

            # Attach domain-specific ID for the frontend and JWT token
            role = (user["role"] or "").upper()

            if role == "CLINICIAN":
                clinician = self.clinicians_repo.get_by_auth_user_id(
                    conn, str(user["user_id"])
                )
                if not clinician:
                    raise ValueError("Clinician profile not found")
                response["clinician_id"] = str(clinician["clinician_id"])
                token_payload["clinician_id"] = str(clinician["clinician_id"])

            elif role == "PATIENT":
                patient = self.patients_repo.get_by_auth_user_id_with_conn(
                    conn, user["user_id"]
                )
                if not patient:
                    raise ValueError("Patient profile not found")
                response["patient_id"] = str(patient["patient_id"])
                token_payload["patient_id"] = str(patient["patient_id"])

            # Generate JWT token with patient_id/clinician_id included
            access_token = create_access_token(token_payload)
            response["access_token"] = access_token

            return response
