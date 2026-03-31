# backend/src/healthsync/repositories/clinicians_repo.py

from __future__ import annotations

from typing import Any, Dict, Optional

from psycopg2.extras import RealDictCursor


class CliniciansRepository:
    # ---------------------------
    # Uniqueness check (used in signup)
    # ---------------------------
    def exists_license_with_conn(self, conn, license_number: str) -> bool:
        sql = "SELECT 1 FROM clinicians WHERE license_number = %s LIMIT 1;"
        with conn.cursor() as cur:
            cur.execute(sql, (license_number,))
            return cur.fetchone() is not None

    # ---------------------------
    # Create clinician (used in signup)
    # ---------------------------
    def create_with_conn(self, conn, data: Dict[str, Any]) -> Dict[str, Any]:
        sql = """
        INSERT INTO clinicians (auth_user_id, first_name, last_name, email, license_number)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING clinician_id, auth_user_id, first_name, last_name, email, license_number;
        """
        params = (
            str(data["auth_user_id"]),
            data["first_name"],
            data["last_name"],
            data["email"],
            data["license_number"],
        )
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    # ---------------------------
    # Fetch clinician by auth user (JWT -> clinician_id)
    # ---------------------------
    def get_by_auth_user_id(self, conn, auth_user_id: str) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT clinician_id, auth_user_id, first_name, last_name, email, license_number
        FROM clinicians
        WHERE auth_user_id = %s
        LIMIT 1;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (str(auth_user_id),))
            return cur.fetchone()

    # ---------------------------
    # Fetch clinician by clinician_id
    # ---------------------------
    def get_by_id_with_conn(self, conn, clinician_id: str) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT clinician_id, auth_user_id, first_name, last_name, email, license_number
        FROM clinicians
        WHERE clinician_id = %s
        LIMIT 1;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (clinician_id,))
            return cur.fetchone()

    # ---------------------------
    # Update clinician email
    # ---------------------------
    def update_email_with_conn(
        self, conn, clinician_id: str, email: str
    ) -> Optional[Dict[str, Any]]:
        sql = """
        UPDATE clinicians
        SET email = %s
        WHERE clinician_id = %s
        RETURNING clinician_id, auth_user_id, first_name, last_name, email, license_number;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (email, clinician_id))
            return cur.fetchone()
