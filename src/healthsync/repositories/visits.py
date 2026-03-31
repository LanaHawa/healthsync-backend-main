from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from psycopg2.extras import RealDictCursor

from healthsync.db.connection import get_conn


class VisitsRepository:
    # ---------------------------
    # Visits
    # ---------------------------

    def create_with_conn(self, conn, data: Dict[str, Any]) -> Dict[str, Any]:
        sql = """
        INSERT INTO visits (
          patient_id, clinician_id, clinic_id,
          start_time, end_time,
          visit_type, visit_type_other_text,
          notes
        )
        VALUES (%s, %s, %s,
                COALESCE(%s, NOW()), NULL,
                %s, %s,
                %s)
        RETURNING
          visit_id, patient_id, clinician_id, clinic_id,
          start_time, end_time,
          visit_type, visit_type_other_text,
          notes,
          created_at, updated_at;
        """
        params = (
            str(data["patient_id"]),
            str(data["clinician_id"]),
            str(data["clinic_id"]) if data.get("clinic_id") else None,
            data.get("start_time"),
            data["visit_type"],
            data.get("visit_type_other_text"),
            data.get("notes"),
        )
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with get_conn() as conn:
            return self.create_with_conn(conn, data)

    def end_visit_with_conn(
        self,
        conn,
        visit_id: UUID,
        end_time: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        sql = """
        UPDATE visits
        SET end_time = COALESCE(%s, NOW()),
            updated_at = NOW()
        WHERE visit_id = %s
        RETURNING
          visit_id, patient_id, clinician_id, clinic_id,
          start_time, end_time,
          visit_type, visit_type_other_text,
          notes,
          created_at, updated_at;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (end_time, str(visit_id)))
            return cur.fetchone()

    def end_visit(
        self, visit_id: UUID, end_time: Optional[datetime] = None
    ) -> Optional[Dict[str, Any]]:
        with get_conn() as conn:
            return self.end_visit_with_conn(conn, visit_id, end_time)

    def get_with_conn(self, conn, visit_id: UUID) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT
          visit_id, patient_id, clinician_id, clinic_id,
          start_time, end_time,
          visit_type, visit_type_other_text,
          notes,
          created_at, updated_at
        FROM visits
        WHERE visit_id = %s
        LIMIT 1;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (str(visit_id),))
            return cur.fetchone()

    def get(self, visit_id: UUID) -> Optional[Dict[str, Any]]:
        with get_conn() as conn:
            return self.get_with_conn(conn, visit_id)

    def list_for_patient_with_conn(
        self,
        conn,
        patient_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        sql = """
        SELECT
          visit_id, patient_id, clinician_id, clinic_id,
          start_time, end_time,
          visit_type, visit_type_other_text,
          notes,
          created_at, updated_at
        FROM visits
        WHERE patient_id = %s
        ORDER BY start_time DESC
        LIMIT %s OFFSET %s;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (str(patient_id), limit, offset))
            return cur.fetchall()

    def list_for_patient(
        self, patient_id: UUID, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        with get_conn() as conn:
            return self.list_for_patient_with_conn(conn, patient_id, limit, offset)

    def list_for_clinician_with_conn(
        self,
        conn,
        clinician_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        sql = """
        SELECT
          v.visit_id, v.patient_id, v.clinician_id, v.clinic_id,
          v.start_time, v.end_time,
          v.visit_type, v.visit_type_other_text,
          v.notes,
          v.created_at, v.updated_at,
          p.first_name AS patient_first_name,
          p.last_name  AS patient_last_name
        FROM visits v
        LEFT JOIN patients p ON p.patient_id = v.patient_id
        WHERE v.clinician_id = %s
        ORDER BY v.start_time DESC
        LIMIT %s OFFSET %s;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (str(clinician_id), limit, offset))
            return cur.fetchall()

    def list_for_clinician(
        self, clinician_id: UUID, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        with get_conn() as conn:
            return self.list_for_clinician_with_conn(conn, clinician_id, limit, offset)

    def list_for_patient_and_clinician_with_conn(
        self,
        conn,
        patient_id: UUID,
        clinician_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Helpful for enforcing that clinicians can only see visits for patients they are involved in
        (or later: patients with approved access).
        """
        sql = """
        SELECT
          visit_id, patient_id, clinician_id, clinic_id,
          start_time, end_time,
          visit_type, visit_type_other_text,
          notes,
          created_at, updated_at
        FROM visits
        WHERE patient_id = %s AND clinician_id = %s
        ORDER BY start_time DESC
        LIMIT %s OFFSET %s;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (str(patient_id), str(clinician_id), limit, offset))
            return cur.fetchall()

    # ---------------------------
    # Visit Summary (0..1 per visit)
    # ---------------------------

    def upsert_summary_with_conn(
        self,
        conn,
        visit_id: UUID,
        created_by: UUID,
        clinical_findings: str,
        decisions: str,
        follow_up_plan: Optional[str],
    ) -> Dict[str, Any]:
        sql = """
        INSERT INTO visit_summaries (
          visit_id, created_by, clinical_findings, decisions, follow_up_plan
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (visit_id)
        DO UPDATE SET
          clinical_findings = EXCLUDED.clinical_findings,
          decisions = EXCLUDED.decisions,
          follow_up_plan = EXCLUDED.follow_up_plan
        RETURNING
          summary_id, visit_id, created_by, created_at,
          clinical_findings, decisions, follow_up_plan;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                sql,
                (
                    str(visit_id),
                    str(created_by),
                    clinical_findings,
                    decisions,
                    follow_up_plan,
                ),
            )
            return cur.fetchone()

    def upsert_summary(
        self,
        visit_id: UUID,
        created_by: UUID,
        clinical_findings: str,
        decisions: str,
        follow_up_plan: Optional[str],
    ) -> Dict[str, Any]:
        with get_conn() as conn:
            return self.upsert_summary_with_conn(
                conn, visit_id, created_by, clinical_findings, decisions, follow_up_plan
            )

    def get_summary_with_conn(self, conn, visit_id: UUID) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT
          summary_id, visit_id, created_by, created_at,
          clinical_findings, decisions, follow_up_plan
        FROM visit_summaries
        WHERE visit_id = %s
        LIMIT 1;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (str(visit_id),))
            return cur.fetchone()

    def get_summary(self, visit_id: UUID) -> Optional[Dict[str, Any]]:
        with get_conn() as conn:
            return self.get_summary_with_conn(conn, visit_id)

    # ---------------------------
    # After Visit Summary (0..1 per visit)
    # ---------------------------

    def upsert_avs_with_conn(
        self,
        conn,
        visit_id: UUID,
        generated_by: UUID,
        delivered_via: str,
        content: str,
    ) -> Dict[str, Any]:
        sql = """
        INSERT INTO after_visit_summaries (
          visit_id, generated_by, delivered_via, content
        )
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (visit_id)
        DO UPDATE SET
          generated_by = EXCLUDED.generated_by,
          delivered_via = EXCLUDED.delivered_via,
          content = EXCLUDED.content
        RETURNING
          avs_id, visit_id, created_at, generated_by, delivered_via, content;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (str(visit_id), str(generated_by), delivered_via, content))
            return cur.fetchone()

    def upsert_avs(
        self,
        visit_id: UUID,
        generated_by: UUID,
        delivered_via: str,
        content: str,
    ) -> Dict[str, Any]:
        with get_conn() as conn:
            return self.upsert_avs_with_conn(
                conn, visit_id, generated_by, delivered_via, content
            )

    def get_avs_with_conn(self, conn, visit_id: UUID) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT
          avs_id, visit_id, created_at, generated_by, delivered_via, content
        FROM after_visit_summaries
        WHERE visit_id = %s
        LIMIT 1;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (str(visit_id),))
            return cur.fetchone()

    def get_avs(self, visit_id: UUID) -> Optional[Dict[str, Any]]:
        with get_conn() as conn:
            return self.get_avs_with_conn(conn, visit_id)

    # ---------------------------
    # Patient: list their own annotations
    # ---------------------------

    def list_annotations_for_patient_with_conn(
        self,
        conn,
        patient_id: UUID,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        sql = """
        SELECT
          a.annotation_id,
          a.visit_id,
          a.type,
          a.content,
          a.created_at,
          v.start_time AS visit_start_time
        FROM annotations a
        JOIN visits v ON v.visit_id = a.visit_id
        WHERE v.patient_id = %s
        ORDER BY a.created_at DESC
        LIMIT %s;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (str(patient_id), limit))
            return cur.fetchall()

    # ---------------------------
    # Visit notes update (PATCH)
    # ---------------------------

    def update_notes_with_conn(
        self,
        conn,
        visit_id: UUID,
        notes: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        sql = """
        UPDATE visits
        SET notes = %s,
            updated_at = NOW()
        WHERE visit_id = %s
        RETURNING
          visit_id, patient_id, clinician_id, clinic_id,
          start_time, end_time,
          visit_type, visit_type_other_text,
          notes,
          created_at, updated_at;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (notes, str(visit_id)))
            return cur.fetchone()

    def update_notes(
        self, visit_id: UUID, notes: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        with get_conn() as conn:
            return self.update_notes_with_conn(conn, visit_id, notes)

    # ---------------------------
    # Visit Annotation Images (screenshot + freehand composite)
    # ---------------------------

    def create_annotation_image_with_conn(
        self,
        conn,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        sql = """
        INSERT INTO visit_annotation_images
          (visit_id, created_by, chart_key, chart_title, label, image_data)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING
          image_id, visit_id, created_by,
          chart_key, chart_title, label, image_data, saved_at;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                sql,
                (
                    str(data["visit_id"]),
                    str(data["created_by"]),
                    data["chart_key"],
                    data["chart_title"],
                    data.get("label"),
                    data["image_data"],
                ),
            )
            return cur.fetchone()

    def create_annotation_image(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with get_conn() as conn:
            return self.create_annotation_image_with_conn(conn, data)

    def list_annotation_images_for_visit_with_conn(
        self,
        conn,
        visit_id: UUID,
    ) -> List[Dict[str, Any]]:
        sql = """
        SELECT
          image_id, visit_id, created_by,
          chart_key, chart_title, label, image_data, saved_at
        FROM visit_annotation_images
        WHERE visit_id = %s
        ORDER BY saved_at ASC;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (str(visit_id),))
            return cur.fetchall()

    def list_annotation_images_for_visit(self, visit_id: UUID) -> List[Dict[str, Any]]:
        with get_conn() as conn:
            return self.list_annotation_images_for_visit_with_conn(conn, visit_id)
