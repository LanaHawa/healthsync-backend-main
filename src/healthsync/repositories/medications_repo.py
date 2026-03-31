# backend/src/healthsync/repositories/medications_repo.py

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from psycopg2.extras import RealDictCursor

from healthsync.db.connection import get_conn


class MedicationsRepository:
    # ── Catalog helpers ─────────────────────────────────────────────────────

    def find_or_create_medication(
        self,
        conn,
        name: str,
        strength: str,
        form: str,
        route: str,
    ) -> UUID:
        """Return existing medication_id by (name, strength) or create a new one."""
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT medication_id FROM medications "
                "WHERE lower(name) = lower(%s) AND lower(strength) = lower(%s) LIMIT 1;",
                (name, strength),
            )
            row = cur.fetchone()
            if row:
                return UUID(str(row["medication_id"]))
            cur.execute(
                """
                INSERT INTO medications (name, strength, form, route)
                VALUES (%s, %s, %s, %s)
                RETURNING medication_id;
                """,
                (name, strength, form, route),
            )
            return UUID(str(cur.fetchone()["medication_id"]))

    # ── Patient medications ──────────────────────────────────────────────────

    _LIST_SQL = """
        SELECT pm.id, pm.medication_id, m.name, m.strength, m.form, m.route,
               pm.start_date, pm.end_date
        FROM patient_medications pm
        JOIN medications m ON m.medication_id = pm.medication_id
        WHERE pm.patient_id = %s
        ORDER BY pm.start_date DESC;
    """

    def list_by_patient(self, patient_id: UUID) -> List[Dict[str, Any]]:
        with get_conn() as conn:
            return self.list_by_patient_with_conn(conn, patient_id)

    def list_by_patient_with_conn(self, conn, patient_id: UUID) -> List[Dict[str, Any]]:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(self._LIST_SQL, (str(patient_id),))
            return [dict(r) for r in cur.fetchall()]

    def add_for_patient(
        self,
        patient_id: UUID,
        name: str,
        strength: str,
        form: str,
        route: str,
        start_date: str,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        with get_conn() as conn:
            med_id = self.find_or_create_medication(conn, name, strength, form, route)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO patient_medications (patient_id, medication_id, start_date, end_date)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id;
                    """,
                    (str(patient_id), str(med_id), start_date, end_date),
                )
                new_id = str(cur.fetchone()["id"])
            # Return full joined row
            rows = self.list_by_patient_with_conn(conn, patient_id)
            for r in rows:
                if str(r["id"]) == new_id:
                    return r
            return {"id": new_id}

    def update_for_patient(
        self,
        link_id: UUID,
        patient_id: UUID,
        *,
        name: Optional[str] = None,
        strength: Optional[str] = None,
        form: Optional[str] = None,
        route: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        with get_conn() as conn:
            # Verify ownership
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, medication_id FROM patient_medications "
                    "WHERE id = %s AND patient_id = %s;",
                    (str(link_id), str(patient_id)),
                )
                pm = cur.fetchone()
                if not pm:
                    return None
                med_id = UUID(str(pm["medication_id"]))

                # Update catalog entry if any catalog fields provided
                med_sets: List[str] = []
                med_params: List[Any] = []
                if name is not None:
                    med_sets.append("name = %s")
                    med_params.append(name)
                if strength is not None:
                    med_sets.append("strength = %s")
                    med_params.append(strength)
                if form is not None:
                    med_sets.append("form = %s")
                    med_params.append(form)
                if route is not None:
                    med_sets.append("route = %s")
                    med_params.append(route)
                if med_sets:
                    med_params.append(str(med_id))
                    cur.execute(
                        f"UPDATE medications SET {', '.join(med_sets)} WHERE medication_id = %s;",
                        med_params,
                    )

                # Update link dates if provided
                pm_sets: List[str] = []
                pm_params: List[Any] = []
                if start_date is not None:
                    pm_sets.append("start_date = %s")
                    pm_params.append(start_date)
                if end_date is not None:
                    pm_sets.append("end_date = %s")
                    pm_params.append(end_date)
                if pm_sets:
                    pm_params.append(str(link_id))
                    cur.execute(
                        f"UPDATE patient_medications SET {', '.join(pm_sets)} WHERE id = %s;",
                        pm_params,
                    )

            rows = self.list_by_patient_with_conn(conn, patient_id)
            for r in rows:
                if str(r["id"]) == str(link_id):
                    return r
            return None

    def remove_for_patient(self, link_id: UUID, patient_id: UUID) -> bool:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM patient_medications WHERE id = %s AND patient_id = %s;",
                    (str(link_id), str(patient_id)),
                )
                return cur.rowcount > 0
