# backend/src/healthsync/repositories/allergies_repo.py

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from psycopg2.extras import RealDictCursor

from healthsync.db.connection import get_conn


ALLOWED_SEVERITIES = {"Low", "Moderate", "High"}


class AllergiesRepository:
    _LIST_SQL = """
        SELECT allergy_id, patient_id, allergen, reaction, severity, created_at
        FROM allergies
        WHERE patient_id = %s
        ORDER BY created_at DESC;
        """

    def list_by_patient(self, patient_id: UUID) -> List[Dict[str, Any]]:
        with get_conn() as conn:
            return self.list_by_patient_with_conn(conn, patient_id)

    def list_by_patient_with_conn(self, conn, patient_id: UUID) -> List[Dict[str, Any]]:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(self._LIST_SQL, (str(patient_id),))
            return cur.fetchall()

    def get_by_id(self, allergy_id: UUID) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT allergy_id, patient_id, allergen, reaction, severity, created_at
        FROM allergies
        WHERE allergy_id = %s
        LIMIT 1;
        """
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (str(allergy_id),))
                return cur.fetchone()

    _INSERT_SQL = """
        INSERT INTO allergies (patient_id, allergen, reaction, severity)
        VALUES (%s, %s, %s, %s)
        RETURNING allergy_id, patient_id, allergen, reaction, severity, created_at;
        """

    def _validate_create(self, allergen: str, severity: str) -> str:
        sev = (severity or "").strip()
        if sev not in ALLOWED_SEVERITIES:
            raise ValueError("Invalid severity. Must be Low, Moderate, or High.")
        if not allergen or not allergen.strip():
            raise ValueError("Allergen is required.")
        return sev

    def create(
        self,
        patient_id: UUID,
        allergen: str,
        reaction: Optional[str],
        severity: str,
    ) -> Dict[str, Any]:
        with get_conn() as conn:
            return self.create_with_conn(conn, patient_id, allergen, reaction, severity)

    def create_with_conn(
        self,
        conn,
        patient_id: UUID,
        allergen: str,
        reaction: Optional[str],
        severity: str,
    ) -> Dict[str, Any]:
        sev = self._validate_create(allergen, severity)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                self._INSERT_SQL,
                (str(patient_id), allergen.strip(), reaction, sev),
            )
            return cur.fetchone()

    def update(
        self,
        allergy_id: UUID,
        patient_id: UUID,
        *,
        allergen: Optional[str] = None,
        reaction: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Patient-scoped update (prevents editing someone else's allergy).
        Only provided fields are updated.
        """
        sets = []
        params: list[Any] = []

        if allergen is not None:
            if not allergen.strip():
                raise ValueError("Allergen cannot be empty.")
            sets.append("allergen = %s")
            params.append(allergen.strip())

        if reaction is not None:
            sets.append("reaction = %s")
            params.append(reaction)

        if severity is not None:
            sev = severity.strip()
            if sev not in ALLOWED_SEVERITIES:
                raise ValueError("Invalid severity. Must be Low, Moderate, or High.")
            sets.append("severity = %s")
            params.append(sev)

        if not sets:
            return self.get_by_id(allergy_id)

        sql = f"""
        UPDATE allergies
        SET {", ".join(sets)}
        WHERE allergy_id = %s AND patient_id = %s
        RETURNING allergy_id, patient_id, allergen, reaction, severity, created_at;
        """
        params.extend([str(allergy_id), str(patient_id)])

        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, tuple(params))
                return cur.fetchone()

    _DELETE_SQL = """
        DELETE FROM allergies
        WHERE allergy_id = %s AND patient_id = %s;
        """

    def delete(self, allergy_id: UUID, patient_id: UUID) -> bool:
        with get_conn() as conn:
            return self.delete_with_conn(conn, allergy_id, patient_id)

    def delete_with_conn(self, conn, allergy_id: UUID, patient_id: UUID) -> bool:
        with conn.cursor() as cur:
            cur.execute(self._DELETE_SQL, (str(allergy_id), str(patient_id)))
            return cur.rowcount > 0
