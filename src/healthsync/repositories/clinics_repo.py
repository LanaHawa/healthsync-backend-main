# backend/src/healthsync/repositories/clinics_repo.py

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from psycopg2.extras import RealDictCursor

from healthsync.db.connection import get_conn


class ClinicsRepository:
    """
    Repository for clinics table.
    Handles lookup by clinic_code (used during clinician signup).
    """

    # ---------------------------
    # Read operations
    # ---------------------------
    def list(self) -> List[Dict[str, Any]]:
        sql = """
        SELECT
            clinic_id,
            name,
            address,
            phone_number,
            last_number,
            clinic_code
        FROM clinics
        ORDER BY name;
        """
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql)
                return cur.fetchall()

    def get_by_id(self, clinic_id: UUID) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT
            clinic_id,
            name,
            address,
            phone_number,
            last_number,
            clinic_code
        FROM clinics
        WHERE clinic_id = %s
        LIMIT 1;
        """
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (str(clinic_id),))
                return cur.fetchone()

    def get_by_code(self, clinic_code: str) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT
            clinic_id,
            name,
            address,
            phone_number,
            last_number,
            clinic_code
        FROM clinics
        WHERE clinic_code = %s
        LIMIT 1;
        """
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (clinic_code,))
                return cur.fetchone()

    # ---------------------------
    # Transaction-safe lookup
    # ---------------------------
    def get_by_code_with_conn(self, conn, clinic_code: str) -> Optional[Dict[str, Any]]:
        """
        Same as get_by_code(), but uses an existing transaction connection.
        Used during signup so user+clinician+membership can be created atomically.
        """
        sql = """
        SELECT
            clinic_id,
            name,
            address,
            phone_number,
            last_number,
            clinic_code
        FROM clinics
        WHERE clinic_code = %s
        LIMIT 1;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (clinic_code,))
            return cur.fetchone()

    # ---------------------------
    # Create
    # ---------------------------
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new clinic.
        clinic_code must already be validated as 5 digits and unique.
        """
        sql = """
        INSERT INTO clinics (name, address, phone_number, clinic_code)
        VALUES (%s, %s, %s, %s)
        RETURNING
            clinic_id,
            name,
            address,
            phone_number,
            last_number,
            clinic_code;
        """
        params = (
            data["name"],
            data["address"],
            data["phone_number"],
            data["clinic_code"],
        )

        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                return cur.fetchone()
