# backend/src/healthsync/repositories/devices_repo.py

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from psycopg2.extras import RealDictCursor

from healthsync.db.connection import get_conn


class DevicesRepository:
    """
    Repository for managing patient devices (CGM sensors, etc.)
    """

    def list_all_with_conn(self, conn) -> List[Dict[str, Any]]:
        """List all devices"""
        sql = """
        SELECT
            device_id,
            patient_id,
            type,
            serial_number,
            model,
            status,
            linked_app_name,
            last_sync_at,
            app_id,
            created_at,
            updated_at
        FROM devices
        ORDER BY created_at DESC;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql)
            return cur.fetchall()

    def list_by_patient_with_conn(self, conn, patient_id: str) -> List[Dict[str, Any]]:
        """List all devices for a specific patient"""
        sql = """
        SELECT
            device_id,
            patient_id,
            type,
            serial_number,
            model,
            status,
            linked_app_name,
            last_sync_at,
            app_id,
            created_at,
            updated_at
        FROM devices
        WHERE patient_id = %s
        ORDER BY created_at DESC;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (patient_id,))
            return cur.fetchall()

    def get_by_id_with_conn(self, conn, device_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific device by ID"""
        sql = """
        SELECT
            device_id,
            patient_id,
            type,
            serial_number,
            model,
            status,
            linked_app_name,
            last_sync_at,
            app_id,
            created_at,
            updated_at
        FROM devices
        WHERE device_id = %s
        LIMIT 1;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (device_id,))
            return cur.fetchone()

    def create_with_conn(self, conn, device_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new device"""
        sql = """
        INSERT INTO devices (
            patient_id,
            type,
            serial_number,
            model,
            status,
            linked_app_name,
            app_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING
            device_id,
            patient_id,
            type,
            serial_number,
            model,
            status,
            linked_app_name,
            last_sync_at,
            app_id,
            created_at,
            updated_at;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                sql,
                (
                    device_data.get("patient_id"),
                    device_data.get("type"),
                    device_data.get("serial_number"),
                    device_data.get("model"),
                    device_data.get("status", "ACTIVE"),
                    device_data.get("linked_app_name"),
                    device_data.get("app_id"),
                ),
            )
            return cur.fetchone()

    def update_with_conn(
        self, conn, device_id: str, updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a device"""
        set_clauses = []
        values = []

        for key in [
            "type",
            "serial_number",
            "model",
            "status",
            "linked_app_name",
            "last_sync_at",
            "app_id",
        ]:
            if key in updates and updates[key] is not None:
                set_clauses.append(f"{key} = %s")
                values.append(updates[key])

        if not set_clauses:
            return self.get_by_id_with_conn(conn, device_id)

        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        values.append(device_id)

        sql = f"""
        UPDATE devices
        SET {", ".join(set_clauses)}
        WHERE device_id = %s
        RETURNING
            device_id,
            patient_id,
            type,
            serial_number,
            model,
            status,
            linked_app_name,
            last_sync_at,
            app_id,
            created_at,
            updated_at;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, values)
            return cur.fetchone()

    def delete_with_conn(self, conn, device_id: str) -> bool:
        """Delete a device"""
        sql = "DELETE FROM devices WHERE device_id = %s;"
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (device_id,))
            return cur.rowcount > 0
