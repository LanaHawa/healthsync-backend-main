# backend/src/healthsync/repositories/prescriptions_repo.py

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from psycopg2.extras import RealDictCursor

from healthsync.db.connection import get_conn


class PrescriptionsRepository:
    def _find_or_create_medication(self, conn, medication_name: str) -> UUID:
        """Find or create a minimal catalog entry for a medication name."""
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT medication_id FROM medications WHERE lower(name) = lower(%s) LIMIT 1;",
                (medication_name,),
            )
            row = cur.fetchone()
            if row:
                return UUID(str(row["medication_id"]))
            cur.execute(
                "INSERT INTO medications (name, strength, form, route) "
                "VALUES (%s, '', '', '') RETURNING medication_id;",
                (medication_name,),
            )
            return UUID(str(cur.fetchone()["medication_id"]))

    def _rows_with_items(
        self, conn, prescription_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """Fetch prescriptions with nested items for the given prescription_ids."""
        if not prescription_ids:
            return []
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT prescription_id, patient_id, clinician_id, issued_at,
                       clinician_name, medication_name, dose, sig
                FROM prescriptions
                WHERE prescription_id = ANY(%s::uuid[])
                ORDER BY issued_at DESC;
                """,
                (prescription_ids,),
            )
            rxs = [dict(r) for r in cur.fetchall()]

            cur.execute(
                """
                SELECT item_id, prescription_id, medication_id,
                       medication_name, dose, sig, duration
                FROM prescription_items
                WHERE prescription_id = ANY(%s::uuid[]);
                """,
                (prescription_ids,),
            )
            items_map: Dict[str, List[Dict[str, Any]]] = {}
            for item in cur.fetchall():
                pid = str(item["prescription_id"])
                items_map.setdefault(pid, []).append(dict(item))

        for rx in rxs:
            rx["items"] = items_map.get(str(rx["prescription_id"]), [])
        return rxs

    def list_by_patient(self, patient_id: UUID) -> List[Dict[str, Any]]:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT prescription_id FROM prescriptions WHERE patient_id = %s;",
                    (str(patient_id),),
                )
                ids = [str(r["prescription_id"]) for r in cur.fetchall()]
            return self._rows_with_items(conn, ids)

    def get_by_id(self, prescription_id: UUID) -> Optional[Dict[str, Any]]:
        with get_conn() as conn:
            rows = self._rows_with_items(conn, [str(prescription_id)])
            return rows[0] if rows else None

    def create(
        self,
        patient_id: UUID,
        clinician_id: UUID,
        clinician_name: str,
        medication_name: Optional[str] = None,
        dose: Optional[str] = None,
        sig: Optional[str] = None,
    ) -> Dict[str, Any]:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO prescriptions
                        (patient_id, clinician_id, clinician_name, medication_name, dose, sig)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING prescription_id;
                    """,
                    (
                        str(patient_id),
                        str(clinician_id),
                        clinician_name,
                        medication_name,
                        dose,
                        sig,
                    ),
                )
                rx_id = str(cur.fetchone()["prescription_id"])
            rows = self._rows_with_items(conn, [rx_id])
            return rows[0]

    def add_item(
        self,
        prescription_id: UUID,
        medication_name: str,
        dose: str,
        sig: str,
        duration: str,
    ) -> Dict[str, Any]:
        with get_conn() as conn:
            med_id = self._find_or_create_medication(conn, medication_name)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO prescription_items
                        (prescription_id, medication_id, medication_name, dose, sig, duration)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING item_id, prescription_id, medication_id,
                              medication_name, dose, sig, duration;
                    """,
                    (
                        str(prescription_id),
                        str(med_id),
                        medication_name,
                        dose,
                        sig,
                        duration,
                    ),
                )
                return dict(cur.fetchone())

    def delete_item(self, item_id: UUID, prescription_id: UUID) -> bool:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM prescription_items "
                    "WHERE item_id = %s AND prescription_id = %s;",
                    (str(item_id), str(prescription_id)),
                )
                return cur.rowcount > 0

    def delete_prescription(self, prescription_id: UUID, clinician_id: UUID) -> bool:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM prescriptions "
                    "WHERE prescription_id = %s AND clinician_id = %s;",
                    (str(prescription_id), str(clinician_id)),
                )
                return cur.rowcount > 0

    def update_prescription(
        self,
        prescription_id: UUID,
        clinician_id: UUID,
        *,
        medication_name: Optional[str] = None,
        dose: Optional[str] = None,
        sig: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        fields: Dict[str, Any] = {}
        if medication_name is not None:
            fields["medication_name"] = medication_name
        if dose is not None:
            fields["dose"] = dose
        if sig is not None:
            fields["sig"] = sig
        if not fields:
            return self.get_by_id(prescription_id)
        set_clause = ", ".join(f"{k} = %s" for k in fields)
        values = list(fields.values()) + [str(prescription_id), str(clinician_id)]
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE prescriptions SET {set_clause} "
                    "WHERE prescription_id = %s AND clinician_id = %s;",
                    values,
                )
                if cur.rowcount == 0:
                    return None
            rows = self._rows_with_items(conn, [str(prescription_id)])
            return rows[0] if rows else None

    def update_item(
        self,
        item_id: UUID,
        prescription_id: UUID,
        *,
        medication_name: Optional[str] = None,
        dose: Optional[str] = None,
        sig: Optional[str] = None,
        duration: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        fields: Dict[str, Any] = {}
        if medication_name is not None:
            fields["medication_name"] = medication_name
        if dose is not None:
            fields["dose"] = dose
        if sig is not None:
            fields["sig"] = sig
        if duration is not None:
            fields["duration"] = duration
        if not fields:
            # nothing to update — return current item
            with get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        "SELECT item_id, prescription_id, medication_id, "
                        "medication_name, dose, sig, duration "
                        "FROM prescription_items WHERE item_id = %s AND prescription_id = %s;",
                        (str(item_id), str(prescription_id)),
                    )
                    row = cur.fetchone()
                    return dict(row) if row else None
        set_clause = ", ".join(f"{k} = %s" for k in fields)
        values = list(fields.values()) + [str(item_id), str(prescription_id)]
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"UPDATE prescription_items SET {set_clause} "
                    "WHERE item_id = %s AND prescription_id = %s "
                    "RETURNING item_id, prescription_id, medication_id, "
                    "medication_name, dose, sig, duration;",
                    values,
                )
                row = cur.fetchone()
                return dict(row) if row else None
