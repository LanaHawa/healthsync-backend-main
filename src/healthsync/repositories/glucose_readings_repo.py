# backend/src/healthsync/repositories/glucose_readings_repo.py

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from psycopg2.extras import RealDictCursor

from healthsync.db.connection import get_conn


class GlucoseReadingsRepository:
    """
    Repository for managing glucose readings from CGM devices
    """

    def list_with_filters_with_conn(
        self,
        conn,
        patient_id: Optional[str] = None,
        device_id: Optional[str] = None,
        from_ts: Optional[datetime] = None,
        to_ts: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get glucose readings with filters using TimescaleDB optimized queries."""
        with conn.cursor() as cursor:
            query = """
                SELECT reading_id, patient_id, device_id, timestamp, value, unit,
                       device_type, source_type, acquired_at
                FROM glucose_readings
                WHERE patient_id = %(patient_id)s
            """
            params = {"patient_id": patient_id}

            if device_id:
                query += " AND device_id = %(device_id)s"
                params["device_id"] = device_id

            if from_ts:
                query += " AND timestamp >= %(from_ts)s"
                params["from_ts"] = from_ts

            if to_ts:
                query += " AND timestamp <= %(to_ts)s"
                params["to_ts"] = to_ts

            query += " ORDER BY timestamp DESC"
            if limit is not None:
                query += " LIMIT %(limit)s"
                params["limit"] = limit

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [
                {
                    "reading_id": str(row[0]),
                    "patient_id": str(row[1]),
                    "device_id": str(row[2]),
                    "timestamp": row[3].isoformat() if row[3] else None,
                    "value": float(row[4]),
                    "unit": row[5],
                    "device_type": row[6],
                    "source_type": row[7],
                    "acquired_at": row[8].isoformat() if row[8] else None,
                }
                for row in rows
            ]

    def get_by_id_with_conn(
        self, conn, reading_id: str, timestamp: Optional[datetime] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get glucose reading by composite key (reading_id, timestamp).
        If timestamp not provided, return the most recent reading with that reading_id.
        """
        with conn.cursor() as cursor:
            if timestamp:
                cursor.execute(
                    """
                    SELECT reading_id, patient_id, device_id, timestamp, value, unit,
                           device_type, source_type, acquired_at
                    FROM glucose_readings
                    WHERE reading_id = %(reading_id)s AND timestamp = %(timestamp)s
                    """,
                    {"reading_id": reading_id, "timestamp": timestamp},
                )
            else:
                cursor.execute(
                    """
                    SELECT reading_id, patient_id, device_id, timestamp, value, unit,
                           device_type, source_type, acquired_at
                    FROM glucose_readings
                    WHERE reading_id = %s
                    ORDER BY timestamp DESC
                    LIMIT 1
                    """,
                    (reading_id,),
                )
            row = cursor.fetchone()
            if row:
                return {
                    "reading_id": str(row[0]),
                    "patient_id": str(row[1]),
                    "device_id": str(row[2]),
                    "timestamp": row[3].isoformat() if row[3] else None,
                    "value": float(row[4]),
                    "unit": row[5],
                    "device_type": row[6],
                    "source_type": row[7],
                    "acquired_at": row[8].isoformat() if row[8] else None,
                }
            return None

    def create_with_conn(self, conn, reading_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new glucose reading with composite PK."""
        from uuid import uuid4

        with conn.cursor() as cursor:
            # Auto-generate reading_id if not provided
            reading_id = reading_data.get("reading_id") or str(uuid4())

            cursor.execute(
                """
                INSERT INTO glucose_readings (
                    reading_id, patient_id, device_id, timestamp,
                    value, unit, device_type, source_type, acquired_at
                )
                VALUES (
                    %(reading_id)s, %(patient_id)s, %(device_id)s, %(timestamp)s,
                    %(value)s, %(unit)s::glucose_unit, %(device_type)s,
                    %(source_type)s, %(acquired_at)s
                )
                RETURNING reading_id, patient_id, device_id, timestamp,
                          value, unit, device_type, acquired_at
                """,
                {
                    "reading_id": reading_id,
                    "patient_id": reading_data["patient_id"],
                    "device_id": reading_data["device_id"],
                    "timestamp": reading_data["timestamp"],
                    "value": reading_data["value"],
                    "unit": reading_data.get("unit", "mg/dL"),
                    "device_type": reading_data.get("device_type"),
                    "source_type": reading_data.get("source_type", "CGM"),
                    "acquired_at": reading_data.get(
                        "acquired_at", reading_data["timestamp"]
                    ),
                },
            )

            row = cursor.fetchone()
            return {
                "reading_id": str(row[0]),
                "patient_id": str(row[1]),
                "device_id": str(row[2]),
                "timestamp": row[3].isoformat() if row[3] else None,
                "value": float(row[4]),
                "unit": row[5],
                "device_type": row[6],
                "acquired_at": row[7].isoformat() if row[7] else None,
            }

    def update_with_conn(
        self, conn, reading_id: str, timestamp: datetime, updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a glucose reading by composite key."""
        if not updates:
            return None

        with conn.cursor() as cursor:
            set_clauses = []
            params = {"reading_id": reading_id, "timestamp": timestamp}

            for key, value in updates.items():
                if key in ["value", "unit", "device_type", "source_type"]:
                    set_clauses.append(f"{key} = %({key})s")
                    params[key] = value

            if not set_clauses:
                return None

            query = f"""
                UPDATE glucose_readings
                SET {"  ".join(set_clauses)}
                WHERE reading_id = %(reading_id)s AND timestamp = %(timestamp)s
                RETURNING reading_id, patient_id, device_id, timestamp, value, unit,
                          device_type, source_type, acquired_at
            """

            cursor.execute(query, params)
            row = cursor.fetchone()

            if row:
                return {
                    "reading_id": str(row[0]),
                    "patient_id": str(row[1]),
                    "device_id": str(row[2]),
                    "timestamp": row[3].isoformat() if row[3] else None,
                    "value": float(row[4]),
                    "unit": row[5],
                    "device_type": row[6],
                    "source_type": row[7],
                    "acquired_at": row[8].isoformat() if row[8] else None,
                }
            return None

    def delete_with_conn(
        self, conn, reading_id: str, timestamp: Optional[datetime]
    ) -> bool:
        """Delete a glucose reading by composite key."""
        with conn.cursor() as cursor:
            if timestamp:
                cursor.execute(
                    """
                    DELETE FROM glucose_readings
                    WHERE reading_id = %(reading_id)s AND timestamp = %(timestamp)s
                    """,
                    {"reading_id": reading_id, "timestamp": timestamp},
                )
            else:
                # Delete all readings with this ID (be careful!)
                cursor.execute(
                    """
                    DELETE FROM glucose_readings
                    WHERE reading_id = %(reading_id)s
                    """,
                    {"reading_id": reading_id},
                )

            return cursor.rowcount > 0

    def bulk_insert_with_conn(self, conn, readings: List[Dict[str, Any]]) -> int:
        """Bulk insert glucose readings (useful for importing historical data)"""
        if not readings:
            return 0

        sql = """
        INSERT INTO glucose_readings (
            patient_id,
            device_id,
            timestamp,
            value,
            unit,
            device_type
        ) VALUES (%s, %s, %s, %s, %s, %s);
        """
        with conn.cursor() as cur:
            for reading in readings:
                cur.execute(
                    sql,
                    (
                        reading.get("patient_id"),
                        reading.get("device_id"),
                        reading.get("timestamp"),
                        reading.get("value"),
                        reading.get("unit"),
                        reading.get("device_type"),
                    ),
                )
            return len(readings)
