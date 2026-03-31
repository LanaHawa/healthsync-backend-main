# backend/src/healthsync/repositories/clinician_clinic_repo.py

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional, List

from psycopg2.extras import RealDictCursor


class ClinicianClinicRepository:
    # ---------------------------------------------------------
    # Link clinician to clinic (idempotent)
    # - If already linked, returns the existing row (not None)
    # ---------------------------------------------------------
    def link_with_conn(
        self,
        conn,
        clinician_id: str,
        clinic_id: str,
        role: Optional[str] = "CLINICIAN",
        start_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        sql = """
        INSERT INTO clinician_clinic (clinician_id, clinic_id, role, start_date)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (clinician_id, clinic_id) DO UPDATE
        SET role = EXCLUDED.role
        RETURNING id, clinician_id, clinic_id, start_date, end_date, role;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (clinician_id, clinic_id, role, start_date))
            return cur.fetchone()

    # ---------------------------------------------------------
    # List clinics for a clinician
    # ---------------------------------------------------------
    def list_by_clinician_with_conn(self, conn, clinician_id: str) -> List[Dict[str, Any]]:
        sql = """
        SELECT id, clinician_id, clinic_id, start_date, end_date, role
        FROM clinician_clinic
        WHERE clinician_id = %s
        ORDER BY start_date NULLS LAST, id;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (clinician_id,))
            return cur.fetchall()

    # ---------------------------------------------------------
    # Remove link (optional helper)
    # ---------------------------------------------------------
    def unlink_with_conn(self, conn, clinician_id: str, clinic_id: str) -> bool:
        sql = """
        DELETE FROM clinician_clinic
        WHERE clinician_id = %s AND clinic_id = %s;
        """
        with conn.cursor() as cur:
            cur.execute(sql, (clinician_id, clinic_id))
            return cur.rowcount > 0
