# backend/src/healthsync/api/routes/lifestyle.py
"""
Lifestyle data endpoints: sleep, meals, steps, activity sessions.

Patient routes  → /lifestyle/sleep/me, /lifestyle/meals/me, etc.
Clinician routes→ /lifestyle/sleep/by-patient/{id}, etc.

All clinician endpoints require the CLINICIAN role.
All patient endpoints require the PATIENT role.
"""

from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from psycopg2.extras import RealDictCursor

from healthsync.auth.jwt import require_role
from healthsync.db.connection import get_conn
from healthsync.repositories.patients import PatientsRepository

router = APIRouter(prefix="/lifestyle", tags=["lifestyle"])
patients_repo = PatientsRepository()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetch_sleep(
    conn, patient_id: UUID, from_date: Optional[date], to_date: Optional[date]
):
    filters = ["patient_id = %s"]
    params: list = [str(patient_id)]
    if from_date:
        filters.append("sleep_start >= %s")
        params.append(from_date)
    if to_date:
        filters.append("sleep_start < %s")
        params.append(to_date)
    where = " AND ".join(filters)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            f"""
            SELECT sleep_id, patient_id, sleep_start, sleep_end, duration_min,
                   deep_sleep_min, rem_sleep_min, light_sleep_min,
                   awakenings, quality_score, recorded_at
            FROM sleep_records
            WHERE {where}
            ORDER BY sleep_start DESC;
            """,
            params,
        )
        return [dict(r) for r in cur.fetchall()]


def _fetch_meals(
    conn,
    patient_id: UUID,
    from_date: Optional[date],
    to_date: Optional[date],
    meal_type: Optional[str],
):
    filters = ["patient_id = %s"]
    params: list = [str(patient_id)]
    if from_date:
        filters.append("logged_at >= %s")
        params.append(from_date)
    if to_date:
        filters.append("logged_at < %s")
        params.append(to_date)
    if meal_type:
        filters.append("meal_type = %s")
        params.append(meal_type)
    where = " AND ".join(filters)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            f"""
            SELECT log_id, patient_id, logged_at, meal_type, description,
                   calories_kcal, carbs_g, protein_g, fat_g, fiber_g, glycemic_index
            FROM meal_logs
            WHERE {where}
            ORDER BY logged_at DESC;
            """,
            params,
        )
        return [dict(r) for r in cur.fetchall()]


def _fetch_steps(
    conn, patient_id: UUID, from_date: Optional[date], to_date: Optional[date]
):
    filters = ["patient_id = %s"]
    params: list = [str(patient_id)]
    if from_date:
        filters.append("record_date >= %s")
        params.append(from_date)
    if to_date:
        filters.append("record_date <= %s")
        params.append(to_date)
    where = " AND ".join(filters)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            f"""
            SELECT step_id, patient_id, record_date, step_count,
                   distance_meters, floors_climbed, active_minutes,
                   sedentary_minutes, calories_burned
            FROM step_records
            WHERE {where}
            ORDER BY record_date DESC;
            """,
            params,
        )
        return [dict(r) for r in cur.fetchall()]


def _fetch_activity(
    conn,
    patient_id: UUID,
    from_date: Optional[date],
    to_date: Optional[date],
    activity_type: Optional[str],
):
    filters = ["patient_id = %s"]
    params: list = [str(patient_id)]
    if from_date:
        filters.append("start_time >= %s")
        params.append(from_date)
    if to_date:
        filters.append("start_time < %s")
        params.append(to_date)
    if activity_type:
        filters.append("activity_type = %s")
        params.append(activity_type)
    where = " AND ".join(filters)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            f"""
            SELECT session_id, patient_id, start_time, end_time,
                   activity_type, intensity, duration_min, calories_burned,
                   avg_heart_rate, max_heart_rate, steps, distance_meters, notes
            FROM activity_sessions
            WHERE {where}
            ORDER BY start_time DESC;
            """,
            params,
        )
        return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Patient — own data (PATIENT role)
# ---------------------------------------------------------------------------


@router.get("/sleep/me")
def get_my_sleep(
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    user=Depends(require_role("PATIENT")),
):
    with get_conn() as conn:
        patient = patients_repo.get_by_auth_user_id_with_conn(
            conn, str(user["user_id"])
        )
        if not patient:
            from fastapi import HTTPException

            raise HTTPException(404, "Patient profile not found")
        return _fetch_sleep(conn, UUID(str(patient["patient_id"])), from_date, to_date)


@router.get("/meals/me")
def get_my_meals(
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    meal_type: Optional[str] = Query(None),
    user=Depends(require_role("PATIENT")),
):
    with get_conn() as conn:
        patient = patients_repo.get_by_auth_user_id_with_conn(
            conn, str(user["user_id"])
        )
        if not patient:
            from fastapi import HTTPException

            raise HTTPException(404, "Patient profile not found")
        return _fetch_meals(
            conn, UUID(str(patient["patient_id"])), from_date, to_date, meal_type
        )


@router.get("/steps/me")
def get_my_steps(
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    user=Depends(require_role("PATIENT")),
):
    with get_conn() as conn:
        patient = patients_repo.get_by_auth_user_id_with_conn(
            conn, str(user["user_id"])
        )
        if not patient:
            from fastapi import HTTPException

            raise HTTPException(404, "Patient profile not found")
        return _fetch_steps(conn, UUID(str(patient["patient_id"])), from_date, to_date)


@router.get("/activity/me")
def get_my_activity(
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    activity_type: Optional[str] = Query(None),
    user=Depends(require_role("PATIENT")),
):
    with get_conn() as conn:
        patient = patients_repo.get_by_auth_user_id_with_conn(
            conn, str(user["user_id"])
        )
        if not patient:
            from fastapi import HTTPException

            raise HTTPException(404, "Patient profile not found")
        return _fetch_activity(
            conn, UUID(str(patient["patient_id"])), from_date, to_date, activity_type
        )


# ---------------------------------------------------------------------------
# Clinician — patient data (CLINICIAN role)
# ---------------------------------------------------------------------------


@router.get("/sleep/by-patient/{patient_id}")
def get_patient_sleep(
    patient_id: UUID,
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    user=Depends(require_role("CLINICIAN")),
):
    with get_conn() as conn:
        return _fetch_sleep(conn, patient_id, from_date, to_date)


@router.get("/meals/by-patient/{patient_id}")
def get_patient_meals(
    patient_id: UUID,
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    meal_type: Optional[str] = Query(None),
    user=Depends(require_role("CLINICIAN")),
):
    with get_conn() as conn:
        return _fetch_meals(conn, patient_id, from_date, to_date, meal_type)


@router.get("/steps/by-patient/{patient_id}")
def get_patient_steps(
    patient_id: UUID,
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    user=Depends(require_role("CLINICIAN")),
):
    with get_conn() as conn:
        return _fetch_steps(conn, patient_id, from_date, to_date)


@router.get("/activity/by-patient/{patient_id}")
def get_patient_activity(
    patient_id: UUID,
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    activity_type: Optional[str] = Query(None),
    user=Depends(require_role("CLINICIAN")),
):
    with get_conn() as conn:
        return _fetch_activity(conn, patient_id, from_date, to_date, activity_type)
