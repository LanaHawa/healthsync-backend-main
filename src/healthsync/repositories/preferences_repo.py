from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from psycopg2.extras import RealDictCursor

from healthsync.db.connection import get_conn


class PreferencesRepository:
    _GET_SQL = """
        SELECT preference_id, auth_user_id, language, color_palette,
               simplified_view_enabled, time_format, date_format,
               default_glucose_unit, has_completed_onboarding
        FROM user_preferences
        WHERE auth_user_id = %s
        LIMIT 1;
    """

    _UPSERT_SQL = """
        INSERT INTO user_preferences (auth_user_id)
        VALUES (%s)
        ON CONFLICT (auth_user_id) DO NOTHING
        RETURNING preference_id, auth_user_id, language, color_palette,
                  simplified_view_enabled, time_format, date_format,
                  default_glucose_unit, has_completed_onboarding;
    """

    def get_by_auth_user_id(self, auth_user_id: UUID) -> Optional[Dict[str, Any]]:
        with get_conn() as conn:
            return self.get_by_auth_user_id_with_conn(conn, auth_user_id)

    def get_by_auth_user_id_with_conn(
        self, conn, auth_user_id: UUID
    ) -> Optional[Dict[str, Any]]:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(self._GET_SQL, (str(auth_user_id),))
            return cur.fetchone()

    def get_or_create_with_conn(self, conn, auth_user_id: UUID) -> Dict[str, Any]:
        """Return existing row, inserting defaults if none exists."""
        row = self.get_by_auth_user_id_with_conn(conn, auth_user_id)
        if row:
            return row
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(self._UPSERT_SQL, (str(auth_user_id),))
            new_row = cur.fetchone()
        # fetchone returns None on ON CONFLICT DO NOTHING when row already existed —
        # do a plain select to be safe
        return new_row or self.get_by_auth_user_id_with_conn(conn, auth_user_id)

    def update_with_conn(
        self,
        conn,
        auth_user_id: UUID,
        simplified_view_enabled: Optional[bool] = None,
        time_format: Optional[str] = None,
        date_format: Optional[str] = None,
        default_glucose_unit: Optional[str] = None,
    ) -> Dict[str, Any]:
        sets = []
        params = []

        if simplified_view_enabled is not None:
            sets.append("simplified_view_enabled = %s")
            params.append(simplified_view_enabled)
        if time_format is not None:
            sets.append("time_format = %s")
            params.append(time_format)
        if date_format is not None:
            sets.append("date_format = %s")
            params.append(date_format)
        if default_glucose_unit is not None:
            sets.append("default_glucose_unit = %s")
            params.append(default_glucose_unit)

        if not sets:
            return self.get_or_create_with_conn(conn, auth_user_id)

        params.append(str(auth_user_id))
        sql = f"""
            UPDATE user_preferences
            SET {", ".join(sets)}
            WHERE auth_user_id = %s
            RETURNING preference_id, auth_user_id, language, color_palette,
                      simplified_view_enabled, time_format, date_format,
                      default_glucose_unit, has_completed_onboarding;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchone()
