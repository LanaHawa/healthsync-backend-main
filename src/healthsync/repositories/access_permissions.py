# backend/src/healthsync/repositories/access_permissions.py

from __future__ import annotations

from typing import Any, Dict, List, Optional
from psycopg2.extras import RealDictCursor


ALLOWED_STATUSES = {"REQUESTED", "APPROVED", "REJECTED", "REVOKED"}


class AccessPermissionsRepository:
    def get_by_patient_and_clinician_with_conn(
        self, conn, patient_id: str, clinician_id: str
    ) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT permission_id, patient_id, clinician_id, status,
               requested_at, granted_at, revoked_at, notes
        FROM access_permissions
        WHERE patient_id = %s AND clinician_id = %s
        LIMIT 1;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (patient_id, clinician_id))
            return cur.fetchone()

    def get_by_id_with_conn(self, conn, permission_id: str) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT permission_id, patient_id, clinician_id, status,
               requested_at, granted_at, revoked_at, notes
        FROM access_permissions
        WHERE permission_id = %s
        LIMIT 1;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (permission_id,))
            return cur.fetchone()

    def create_request_with_conn(
        self, conn, patient_id: str, clinician_id: str, notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new access request.
        If you expect duplicates due to UNIQUE(patient_id, clinician_id),
        consider using upsert_request_with_conn instead.
        """
        sql = """
        INSERT INTO access_permissions (patient_id, clinician_id, status, requested_at, notes)
        VALUES (%s, %s, 'REQUESTED'::permission_status, NOW(), %s)
        RETURNING permission_id, patient_id, clinician_id, status,
                  requested_at, granted_at, revoked_at, notes;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (patient_id, clinician_id, notes))
            return cur.fetchone()

    def upsert_request_with_conn(
        self, conn, patient_id: str, clinician_id: str, notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Safe version: if a row already exists for (patient_id, clinician_id),
        it resets it to REQUESTED (unless already REQUESTED/APPROVED — you can decide).
        """
        sql = """
        INSERT INTO access_permissions (patient_id, clinician_id, status, requested_at, notes)
        VALUES (%s, %s, 'REQUESTED'::permission_status, NOW(), %s)
        ON CONFLICT (patient_id, clinician_id)
        DO UPDATE SET
            status = 'REQUESTED'::permission_status,
            requested_at = NOW(),
            granted_at = NULL,
            revoked_at = NULL,
            notes = COALESCE(EXCLUDED.notes, access_permissions.notes)
        RETURNING permission_id, patient_id, clinician_id, status,
                  requested_at, granted_at, revoked_at, notes;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (patient_id, clinician_id, notes))
            return cur.fetchone()

    def set_status_with_conn(
        self,
        conn,
        permission_id: str,
        status: str,
        notes: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Update status and maintain timestamps:
        - APPROVED: granted_at = NOW()
        - REVOKED: revoked_at = NOW()
        - REQUESTED: requested_at = NOW(), granted_at/revoked_at cleared
        - REJECTED: leaves timestamps as-is (or you can clear granted_at if you want)
        """
        status_norm = (status or "").upper().strip()
        if status_norm not in ALLOWED_STATUSES:
            raise ValueError(f"Invalid permission status: {status}")

        if status_norm == "APPROVED":
            sql = """
            UPDATE access_permissions
            SET status = 'APPROVED'::permission_status,
                granted_at = NOW(),
                notes = COALESCE(%s, notes)
            WHERE permission_id = %s
            RETURNING permission_id, patient_id, clinician_id, status,
                      requested_at, granted_at, revoked_at, notes;
            """
            params = (notes, permission_id)

        elif status_norm == "REJECTED":
            sql = """
            UPDATE access_permissions
            SET status = 'REJECTED'::permission_status,
                notes = COALESCE(%s, notes)
            WHERE permission_id = %s
            RETURNING permission_id, patient_id, clinician_id, status,
                      requested_at, granted_at, revoked_at, notes;
            """
            params = (notes, permission_id)

        elif status_norm == "REVOKED":
            sql = """
            UPDATE access_permissions
            SET status = 'REVOKED'::permission_status,
                revoked_at = NOW(),
                notes = COALESCE(%s, notes)
            WHERE permission_id = %s
            RETURNING permission_id, patient_id, clinician_id, status,
                      requested_at, granted_at, revoked_at, notes;
            """
            params = (notes, permission_id)

        else:  # REQUESTED
            sql = """
            UPDATE access_permissions
            SET status = 'REQUESTED'::permission_status,
                requested_at = NOW(),
                granted_at = NULL,
                revoked_at = NULL,
                notes = COALESCE(%s, notes)
            WHERE permission_id = %s
            RETURNING permission_id, patient_id, clinician_id, status,
                      requested_at, granted_at, revoked_at, notes;
            """
            params = (notes, permission_id)

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def list_for_clinician_with_conn(self, conn, clinician_id: str) -> List[Dict[str, Any]]:
        sql = """
        SELECT ap.permission_id, ap.status, ap.requested_at, ap.granted_at, ap.revoked_at, ap.notes,
               p.patient_id, p.first_name, p.last_name, p.phn
        FROM access_permissions ap
        JOIN patients p ON p.patient_id = ap.patient_id
        WHERE ap.clinician_id = %s
        ORDER BY ap.requested_at DESC;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (clinician_id,))
            return cur.fetchall()

    def list_requested_for_clinician_with_conn(self, conn, clinician_id: str) -> List[Dict[str, Any]]:
        """
        Inbox helper: only REQUESTED items.
        """
        sql = """
        SELECT ap.permission_id, ap.status, ap.requested_at, ap.notes,
               p.patient_id, p.first_name, p.last_name, p.phn
        FROM access_permissions ap
        JOIN patients p ON p.patient_id = ap.patient_id
        WHERE ap.clinician_id = %s
          AND ap.status = 'REQUESTED'::permission_status
        ORDER BY ap.requested_at DESC;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (clinician_id,))
            return cur.fetchall()

    def list_for_patient_with_conn(self, conn, patient_id: str) -> List[Dict[str, Any]]:
        sql = """
        SELECT ap.permission_id, ap.status, ap.requested_at, ap.granted_at, ap.revoked_at, ap.notes,
               c.clinician_id, c.first_name, c.last_name, c.email
        FROM access_permissions ap
        JOIN clinicians c ON c.clinician_id = ap.clinician_id
        WHERE ap.patient_id = %s
        ORDER BY ap.requested_at DESC;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (patient_id,))
            return cur.fetchall()
