# backend/src/healthsync/repositories/activity_data_repo.py

"""Repository for activity data operations."""

from __future__ import annotations

import logging
from typing import Dict, List, Any, Optional
from uuid import uuid4
from datetime import datetime

logger = logging.getLogger(__name__)


class ActivityDataRepository:
    """Repository for activity data CRUD operations with composite PK (activity_id, timestamp)."""

    def create_with_conn(self, conn, activity_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new activity data record."""
        with conn.cursor() as cursor:
            activity_id = activity_data.get("activity_id") or str(uuid4())

            cursor.execute(
                """
                INSERT INTO activity_data (
                    activity_id, patient_id, reading_id, reading_timestamp,
                    timestamp, heart_rate, steps, calories_burned, distance_meters
                )
                VALUES (
                    %(activity_id)s, %(patient_id)s, %(reading_id)s, %(reading_timestamp)s,
                    %(timestamp)s, %(heart_rate)s, %(steps)s, %(calories_burned)s, %(distance_meters)s
                )
                RETURNING activity_id, patient_id, timestamp, heart_rate, steps,
                          calories_burned, distance_meters, created_at
                """,
                {
                    "activity_id": activity_id,
                    "patient_id": activity_data["patient_id"],
                    "reading_id": activity_data.get("reading_id"),
                    "reading_timestamp": activity_data.get("reading_timestamp"),
                    "timestamp": activity_data["timestamp"],
                    "heart_rate": activity_data.get("heart_rate"),
                    "steps": activity_data.get("steps"),
                    "calories_burned": activity_data.get("calories_burned"),
                    "distance_meters": activity_data.get("distance_meters"),
                },
            )

            row = cursor.fetchone()
            return {
                "activity_id": str(row[0]),
                "patient_id": str(row[1]),
                "timestamp": row[2].isoformat() if row[2] else None,
                "heart_rate": int(row[3]) if row[3] else None,
                "steps": int(row[4]) if row[4] else None,
                "calories_burned": float(row[5]) if row[5] else None,
                "distance_meters": float(row[6]) if row[6] else None,
                "created_at": row[7].isoformat() if row[7] else None,
            }

    def get_by_id_with_conn(
        self, conn, activity_id: str, timestamp: Optional[datetime] = None
    ) -> Optional[Dict[str, Any]]:
        """Get activity data by composite key (activity_id, timestamp)."""
        with conn.cursor() as cursor:
            if timestamp:
                cursor.execute(
                    """
                    SELECT activity_id, patient_id, reading_id, reading_timestamp,
                           timestamp, heart_rate, steps, calories_burned,
                           distance_meters, created_at
                    FROM activity_data
                    WHERE activity_id = %(activity_id)s AND timestamp = %(timestamp)s
                    """,
                    {"activity_id": activity_id, "timestamp": timestamp},
                )
            else:
                # Fallback: get most recent activity with this ID
                cursor.execute(
                    """
                    SELECT activity_id, patient_id, reading_id, reading_timestamp,
                           timestamp, heart_rate, steps, calories_burned,
                           distance_meters, created_at
                    FROM activity_data
                    WHERE activity_id = %(activity_id)s
                    ORDER BY timestamp DESC
                    LIMIT 1
                    """,
                    {"activity_id": activity_id},
                )

            row = cursor.fetchone()
            if row:
                return {
                    "activity_id": str(row[0]),
                    "patient_id": str(row[1]),
                    "reading_id": str(row[2]) if row[2] else None,
                    "reading_timestamp": row[3].isoformat() if row[3] else None,
                    "timestamp": row[4].isoformat() if row[4] else None,
                    "heart_rate": int(row[5]) if row[5] else None,
                    "steps": int(row[6]) if row[6] else None,
                    "calories_burned": float(row[7]) if row[7] else None,
                    "distance_meters": float(row[8]) if row[8] else None,
                    "created_at": row[9].isoformat() if row[9] else None,
                }
            return None

    def list_by_patient_with_conn(
        self,
        conn,
        patient_id: str,
        from_ts: Optional[datetime] = None,
        to_ts: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Get activity data for a patient within time range."""
        with conn.cursor() as cursor:
            query = """
                SELECT activity_id, patient_id, reading_id, reading_timestamp,
                       timestamp, heart_rate, steps, calories_burned,
                       distance_meters, created_at
                FROM activity_data
                WHERE patient_id = %(patient_id)s
            """
            params = {"patient_id": patient_id, "limit": limit}

            if from_ts:
                query += " AND timestamp >= %(from_ts)s"
                params["from_ts"] = from_ts

            if to_ts:
                query += " AND timestamp <= %(to_ts)s"
                params["to_ts"] = to_ts

            query += " ORDER BY timestamp DESC LIMIT %(limit)s"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [
                {
                    "activity_id": str(row[0]),
                    "patient_id": str(row[1]),
                    "reading_id": str(row[2]) if row[2] else None,
                    "reading_timestamp": row[3].isoformat() if row[3] else None,
                    "timestamp": row[4].isoformat() if row[4] else None,
                    "heart_rate": int(row[5]) if row[5] else None,
                    "steps": int(row[6]) if row[6] else None,
                    "calories_burned": float(row[7]) if row[7] else None,
                    "distance_meters": float(row[8]) if row[8] else None,
                    "created_at": row[9].isoformat() if row[9] else None,
                }
                for row in rows
            ]

    def update_with_conn(
        self, conn, activity_id: str, timestamp: datetime, updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update activity data by composite key."""
        if not updates:
            return None

        with conn.cursor() as cursor:
            set_clauses = []
            params = {"activity_id": activity_id, "timestamp": timestamp}

            for key, value in updates.items():
                if key in ["heart_rate", "steps", "calories_burned", "distance_meters"]:
                    set_clauses.append(f"{key} = %({key})s")
                    params[key] = value

            if not set_clauses:
                return None

            query = f"""
                UPDATE activity_data
                SET {", ".join(set_clauses)}
                WHERE activity_id = %(activity_id)s AND timestamp = %(timestamp)s
                RETURNING activity_id, patient_id, timestamp, heart_rate, steps,
                          calories_burned, distance_meters, created_at
            """

            cursor.execute(query, params)
            row = cursor.fetchone()

            if row:
                return {
                    "activity_id": str(row[0]),
                    "patient_id": str(row[1]),
                    "timestamp": row[2].isoformat() if row[2] else None,
                    "heart_rate": int(row[3]) if row[3] else None,
                    "steps": int(row[4]) if row[4] else None,
                    "calories_burned": float(row[5]) if row[5] else None,
                    "distance_meters": float(row[6]) if row[6] else None,
                    "created_at": row[7].isoformat() if row[7] else None,
                }
            return None

    def delete_with_conn(
        self, conn, activity_id: str, timestamp: Optional[datetime] = None
    ) -> bool:
        """Delete activity data by composite key."""
        with conn.cursor() as cursor:
            if timestamp:
                cursor.execute(
                    """
                    DELETE FROM activity_data
                    WHERE activity_id = %(activity_id)s AND timestamp = %(timestamp)s
                    """,
                    {"activity_id": activity_id, "timestamp": timestamp},
                )
            else:
                # Delete all activity records with this ID
                cursor.execute(
                    """
                    DELETE FROM activity_data
                    WHERE activity_id = %(activity_id)s
                    """,
                    {"activity_id": activity_id},
                )

            return cursor.rowcount > 0
