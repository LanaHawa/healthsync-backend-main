# backend/src/healthsync/repositories/patients.py

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from psycopg2.extras import RealDictCursor

from healthsync.db.connection import get_conn


class PatientsRepository:
    """
    Postgres-backed repository for patients.

    Notes:
    - Respects soft delete: deleted_at IS NULL for normal reads.
    - Uses psycopg2 via get_conn() (cursor-based SQL).
    """

    # ----------------------------
    # READ
    # ----------------------------
    def list(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        sql = """
        SELECT
          patient_id,
          auth_user_id,
          first_name,
          last_name,
          email,
          phone_number,
          address,
          phn,
          date_of_birth,
          age,
          gender,
          body_weight_lbs,
          height_inches,
          bmi,
          insulin_sensitivity,
          primary_clinician_id,
          clinic_id,
          deleted_at
        FROM patients
        WHERE deleted_at IS NULL
        ORDER BY last_name, first_name
        LIMIT %s OFFSET %s;
        """
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (limit, offset))
                return cur.fetchall()

    def get(self, patient_id: UUID) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT
          patient_id,
          auth_user_id,
          first_name,
          last_name,
          email,
          phone_number,
          address,
          phn,
          date_of_birth,
          age,
          gender,
          body_weight_lbs,
          height_inches,
          bmi,
          insulin_sensitivity,
          primary_clinician_id,
          clinic_id,
          deleted_at
        FROM patients
        WHERE patient_id = %s
        LIMIT 1;
        """
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (str(patient_id),))
                row = cur.fetchone()
                if not row:
                    return None
                if row.get("deleted_at") is not None:
                    return None
                return row

    def get_by_auth_user_id(
        self, auth_user_id: Union[str, UUID]
    ) -> Optional[Dict[str, Any]]:
        """
        Used a lot by routes to find the patient's patient_id using JWT user_id.
        """
        sql = """
        SELECT
          patient_id,
          auth_user_id,
          first_name,
          last_name,
          email,
          phone_number,
          address,
          phn,
          date_of_birth,
          age,
          gender,
          body_weight_lbs,
          height_inches,
          bmi,
          insulin_sensitivity,
          primary_clinician_id,
          clinic_id,
          deleted_at
        FROM patients
        WHERE auth_user_id = %s AND deleted_at IS NULL
        LIMIT 1;
        """
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (str(auth_user_id),))
                return cur.fetchone()

    def get_by_auth_user_id_with_conn(
        self, conn, auth_user_id: Union[str, UUID]
    ) -> Optional[Dict[str, Any]]:
        """
        Same as get_by_auth_user_id(), but uses an existing transaction connection.
        """
        sql = """
        SELECT
          patient_id,
          auth_user_id,
          first_name,
          last_name,
          email,
          phone_number,
          address,
          phn,
          date_of_birth,
          age,
          gender,
          body_weight_lbs,
          height_inches,
          bmi,
          insulin_sensitivity,
          primary_clinician_id,
          clinic_id,
          deleted_at
        FROM patients
        WHERE auth_user_id = %s AND deleted_at IS NULL
        LIMIT 1;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (str(auth_user_id),))
            return cur.fetchone()

    def search_by_phn(self, phn: str, limit: int = 20) -> List[Dict[str, Any]]:
        sql = """
        SELECT patient_id, first_name, last_name, address, phn
        FROM patients
        WHERE deleted_at IS NULL AND phn = %s
        ORDER BY last_name, first_name
        LIMIT %s;
        """
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (phn, limit))
                return cur.fetchall()

    def search_by_query(self, q: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search by exact PHN (9 digits) or by partial first/last name (case-insensitive)."""
        q = q.strip()
        if re.match(r"^[0-9]{9}$", q):
            sql = """
            SELECT patient_id, first_name, last_name, address, phn
            FROM patients
            WHERE deleted_at IS NULL AND phn = %s
            ORDER BY last_name, first_name
            LIMIT %s;
            """
            params: tuple = (q, limit)
        else:
            pattern = f"%{q}%"
            sql = """
            SELECT patient_id, first_name, last_name, address, phn
            FROM patients
            WHERE deleted_at IS NULL AND (
              LOWER(first_name) LIKE LOWER(%s)
              OR LOWER(last_name) LIKE LOWER(%s)
              OR LOWER(first_name || ' ' || last_name) LIKE LOWER(%s)
            )
            ORDER BY last_name, first_name
            LIMIT %s;
            """
            params = (pattern, pattern, pattern, limit)

        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                return cur.fetchall()

    def get_by_id_with_conn(
        self, conn, patient_id: Union[str, UUID]
    ) -> Optional[Dict[str, Any]]:
        """Fetch a patient by patient_id using an existing connection."""
        sql = """
        SELECT
          patient_id,
          auth_user_id,
          first_name,
          last_name,
          email,
          phone_number,
          address,
          phn,
          date_of_birth,
          age,
          gender,
          body_weight_lbs,
          height_inches,
          bmi,
          insulin_sensitivity,
          primary_clinician_id,
          clinic_id,
          deleted_at
        FROM patients
        WHERE patient_id = %s
        LIMIT 1;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (str(patient_id),))
            return cur.fetchone()

    # ----------------------------
    # CREATE
    # ----------------------------
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Creates a patient row using its own connection.
        phone_number is nullable in DB (your latest ALTER drops NOT NULL),
        so we allow it to be missing/None.
        """
        sql = """
        INSERT INTO patients (
            auth_user_id,
            first_name,
            last_name,
            email,
            phone_number,
            address,
            phn,
            date_of_birth,
            primary_clinician_id,
            clinic_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING
            patient_id,
            auth_user_id,
            first_name,
            last_name,
            email,
            phone_number,
            address,
            phn,
            date_of_birth,
            primary_clinician_id,
            clinic_id,
            deleted_at;
        """
        params = (
            str(data["auth_user_id"]),
            data["first_name"],
            data["last_name"],
            data.get("email"),
            data.get("phone_number"),  # nullable
            data.get("address"),
            data.get("phn"),
            data.get("date_of_birth"),
            str(data["primary_clinician_id"])
            if data.get("primary_clinician_id")
            else None,
            str(data["clinic_id"]) if data.get("clinic_id") else None,
        )

        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                return cur.fetchone()

    def create_with_conn(self, conn, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Same as create(), but uses an existing transaction connection
        (used in signup so auth_user + patient can be atomic).
        """
        sql = """
        INSERT INTO patients (
            auth_user_id,
            first_name,
            last_name,
            email,
            phone_number,
            address,
            phn,
            date_of_birth,
            primary_clinician_id,
            clinic_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING
            patient_id,
            auth_user_id,
            first_name,
            last_name,
            email,
            phone_number,
            address,
            phn,
            date_of_birth,
            primary_clinician_id,
            clinic_id,
            deleted_at;
        """
        params = (
            str(data["auth_user_id"]),
            data["first_name"],
            data["last_name"],
            data.get("email"),
            data.get("phone_number"),  # nullable
            data.get("address"),
            data.get("phn"),
            data.get("date_of_birth"),
            str(data["primary_clinician_id"])
            if data.get("primary_clinician_id")
            else None,
            str(data["clinic_id"]) if data.get("clinic_id") else None,
        )
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    # ----------------------------
    # UPDATE / DELETE
    # ----------------------------
    def update(
        self, patient_id: UUID, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Patch update:
        - Only updates provided (non-None) fields.
        - Treats soft-deleted patients as not found.
        """
        allowed_fields = {
            "first_name",
            "last_name",
            "phone_number",
            "address",
            "phn",
            "date_of_birth",
            "primary_clinician_id",
            "clinic_id",
        }
        updates = {
            k: v for k, v in data.items() if k in allowed_fields and v is not None
        }
        if not updates:
            return self.get(patient_id)

        set_clauses: List[str] = []
        params: List[Any] = []

        for k, v in updates.items():
            if k in ("primary_clinician_id", "clinic_id") and v is not None:
                v = str(v)
            set_clauses.append(f"{k} = %s")
            params.append(v)

        params.append(str(patient_id))

        sql = f"""
        UPDATE patients
        SET {", ".join(set_clauses)}
        WHERE patient_id = %s AND deleted_at IS NULL
        RETURNING
          patient_id,
          auth_user_id,
          first_name,
          last_name,
          email,
          phone_number,
          address,
          phn,
          date_of_birth,
          age,
          gender,
          body_weight_lbs,
          height_inches,
          bmi,
          insulin_sensitivity,
          primary_clinician_id,
          clinic_id,
          deleted_at;
        """

        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, tuple(params))
                return cur.fetchone()

    def delete(self, patient_id: UUID) -> bool:
        """
        Soft delete: sets deleted_at timestamp.
        """
        sql = """
        UPDATE patients
        SET deleted_at = NOW()
        WHERE patient_id = %s AND deleted_at IS NULL;
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (str(patient_id),))
                return (cur.rowcount or 0) > 0
