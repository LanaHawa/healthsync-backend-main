# backend/src/healthsync/repositories/agenda_items_repo.py

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from psycopg2.extras import RealDictCursor

from healthsync.db.connection import get_conn


ALLOWED_STATUSES = {"OPEN", "DONE", "SKIPPED"}


class AgendaItemsRepository:
    def list_by_visit(self, visit_id: UUID) -> List[Dict[str, Any]]:
        sql = """
        SELECT agenda_item_id, visit_id, title, description, order_index, status
        FROM agenda_items
        WHERE visit_id = %s
        ORDER BY order_index ASC, agenda_item_id ASC;
        """
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (str(visit_id),))
                return cur.fetchall()

    def get(self, agenda_item_id: UUID) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT agenda_item_id, visit_id, title, description, order_index, status
        FROM agenda_items
        WHERE agenda_item_id = %s
        LIMIT 1;
        """
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (str(agenda_item_id),))
                return cur.fetchone()

    def create(
        self,
        visit_id: UUID,
        title: str,
        description: Optional[str] = None,
        order_index: int = 0,
    ) -> Dict[str, Any]:
        sql = """
        INSERT INTO agenda_items (visit_id, title, description, order_index)
        VALUES (%s, %s, %s, %s)
        RETURNING agenda_item_id, visit_id, title, description, order_index, status;
        """
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    sql, (str(visit_id), title.strip(), description, order_index)
                )
                return cur.fetchone()

    def patch(
        self,
        agenda_item_id: UUID,
        *,
        status: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        sets: List[str] = []
        params: List[Any] = []

        if status is not None:
            st = status.upper().strip()
            if st not in ALLOWED_STATUSES:
                raise ValueError(f"Invalid status: {status}")
            sets.append("status = %s::agenda_status")
            params.append(st)

        if title is not None:
            if not title.strip():
                raise ValueError("title cannot be empty")
            sets.append("title = %s")
            params.append(title.strip())

        if description is not None:
            sets.append("description = %s")
            params.append(description)

        if not sets:
            return self.get(agenda_item_id)

        sql = f"""
        UPDATE agenda_items
        SET {", ".join(sets)}
        WHERE agenda_item_id = %s
        RETURNING agenda_item_id, visit_id, title, description, order_index, status;
        """
        params.append(str(agenda_item_id))

        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, tuple(params))
                return cur.fetchone()

    def delete(self, agenda_item_id: UUID) -> bool:
        sql = "DELETE FROM agenda_items WHERE agenda_item_id = %s;"
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (str(agenda_item_id),))
                return cur.rowcount > 0
