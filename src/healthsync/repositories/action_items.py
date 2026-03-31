# backend/src/healthsync/repositories/action_items.py

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID
from datetime import datetime

from psycopg2.extras import RealDictCursor

from healthsync.db.connection import get_conn


ALLOWED_OWNER_TYPES = {"PATIENT", "CLINICIAN", "SYSTEM"}
ALLOWED_STATUSES = {"OPEN", "IN_PROGRESS", "COMPLETED", "CANCELLED"}


class ActionItemsRepository:
    # ----------------------------
    # Queries
    # ----------------------------
    def list_by_visit(self, visit_id: UUID) -> List[Dict[str, Any]]:
        sql = """
        SELECT
          action_id, visit_id, patient_id,
          description, owner_type, status,
          due_date, follow_up_plan,
          created_at, created_by
        FROM action_items
        WHERE visit_id = %s
        ORDER BY created_at ASC;
        """
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (str(visit_id),))
                return cur.fetchall()

    def get_by_id(self, action_id: UUID) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT
          action_id, visit_id, patient_id,
          description, owner_type, status,
          due_date, follow_up_plan,
          created_at, created_by
        FROM action_items
        WHERE action_id = %s
        LIMIT 1;
        """
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (str(action_id),))
                return cur.fetchone()

    # ----------------------------
    # Mutations
    # ----------------------------
    def create(
        self,
        visit_id: UUID,
        patient_id: UUID,
        description: str,
        owner_type: str,
        created_by: UUID,
        status: str = "OPEN",
        due_date: Optional[datetime] = None,
        follow_up_plan: Optional[str] = None,
    ) -> Dict[str, Any]:
        owner = (owner_type or "").upper().strip()
        st = (status or "").upper().strip()

        if owner not in ALLOWED_OWNER_TYPES:
            raise ValueError(f"Invalid owner_type: {owner_type}")
        if st not in ALLOWED_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        if not description or not description.strip():
            raise ValueError("description is required")

        sql = """
        INSERT INTO action_items (
          visit_id, patient_id, description,
          owner_type, status, due_date, follow_up_plan,
          created_by
        )
        VALUES (
          %s, %s, %s,
          %s::stakeholder_type, %s::action_status, %s, %s,
          %s
        )
        RETURNING
          action_id, visit_id, patient_id,
          description, owner_type, status,
          due_date, follow_up_plan,
          created_at, created_by;
        """
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    sql,
                    (
                        str(visit_id),
                        str(patient_id),
                        description.strip(),
                        owner,
                        st,
                        due_date,
                        follow_up_plan,
                        str(created_by),
                    ),
                )
                return cur.fetchone()

    def update(
        self,
        action_id: UUID,
        *,
        description: Optional[str] = None,
        owner_type: Optional[str] = None,
        status: Optional[str] = None,
        due_date: Optional[datetime] = None,
        follow_up_plan: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Partial update. Only provided fields are updated.
        """
        sets = []
        params: List[Any] = []

        if description is not None:
            if not description.strip():
                raise ValueError("description cannot be empty")
            sets.append("description = %s")
            params.append(description.strip())

        if owner_type is not None:
            owner = owner_type.upper().strip()
            if owner not in ALLOWED_OWNER_TYPES:
                raise ValueError(f"Invalid owner_type: {owner_type}")
            sets.append("owner_type = %s::stakeholder_type")
            params.append(owner)

        if status is not None:
            st = status.upper().strip()
            if st not in ALLOWED_STATUSES:
                raise ValueError(f"Invalid status: {status}")
            sets.append("status = %s::action_status")
            params.append(st)

        if due_date is not None:
            sets.append("due_date = %s")
            params.append(due_date)

        if follow_up_plan is not None:
            sets.append("follow_up_plan = %s")
            params.append(follow_up_plan)

        if not sets:
            # nothing to update; return current row
            return self.get_by_id(action_id)

        sql = f"""
        UPDATE action_items
        SET {", ".join(sets)}
        WHERE action_id = %s
        RETURNING
          action_id, visit_id, patient_id,
          description, owner_type, status,
          due_date, follow_up_plan,
          created_at, created_by;
        """
        params.append(str(action_id))

        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, tuple(params))
                return cur.fetchone()

    def delete(self, action_id: UUID) -> bool:
        sql = "DELETE FROM action_items WHERE action_id = %s;"
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (str(action_id),))
                return cur.rowcount > 0

    def list_by_patient(self, patient_id: UUID) -> List[Dict[str, Any]]:
        sql = """
        SELECT
          action_id, visit_id, patient_id,
          description, owner_type, status,
          due_date, follow_up_plan,
          created_at, created_by
        FROM action_items
        WHERE patient_id = %s
        ORDER BY COALESCE(due_date, created_at) ASC;
        """
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (str(patient_id),))
                return cur.fetchall()
