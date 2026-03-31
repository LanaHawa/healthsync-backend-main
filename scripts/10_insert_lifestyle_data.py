"""
10_insert_lifestyle_data.py
Reads the four lifestyle CSVs produced by 09_generate_lifestyle_data.py and
bulk-inserts them into the database.  Existing rows are skipped via ON CONFLICT
DO NOTHING so the script is safe to re-run.

Usage:
  python scripts/10_insert_lifestyle_data.py
  python scripts/10_insert_lifestyle_data.py --batch-size 500
"""

import csv
import logging
import sys
import argparse
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent
SYNTHETIC_DIR = BACKEND_DIR / "data" / "synthetic_data"
sys.path.insert(0, str(BACKEND_DIR / "src"))

from healthsync.db.connection import get_conn  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _nullify(val: str):
    """Return None for empty-string CSV values."""
    return val if val.strip() != "" else None


def _int_or_none(val: str):
    v = _nullify(val)
    return int(v) if v is not None else None


def _float_or_none(val: str):
    v = _nullify(val)
    return float(v) if v is not None else None


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        logger.warning("CSV not found, skipping: %s", path)
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def bulk_insert(conn, sql: str, rows: list[tuple], batch_size: int) -> int:
    inserted = 0
    with conn.cursor() as cur:
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            cur.executemany(sql, batch)
            inserted += len(batch)
    conn.commit()
    return inserted


# ---------------------------------------------------------------------------
# Table-specific inserters
# ---------------------------------------------------------------------------


def insert_sleep(conn, rows: list[dict], batch_size: int) -> None:
    sql = """
        INSERT INTO sleep_records
            (sleep_id, patient_id, sleep_start, sleep_end, duration_min,
             deep_sleep_min, rem_sleep_min, light_sleep_min,
             awakenings, quality_score, recorded_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (sleep_id) DO NOTHING;
    """
    tuples = [
        (
            r["sleep_id"],
            r["patient_id"],
            r["sleep_start"],
            r["sleep_end"],
            int(r["duration_min"]),
            _int_or_none(r["deep_sleep_min"]),
            _int_or_none(r["rem_sleep_min"]),
            _int_or_none(r["light_sleep_min"]),
            _int_or_none(r["awakenings"]),
            _int_or_none(r["quality_score"]),
            r["recorded_at"],
        )
        for r in rows
    ]
    n = bulk_insert(conn, sql, tuples, batch_size)
    logger.info("sleep_records: %d rows inserted", n)


def insert_meals(conn, rows: list[dict], batch_size: int) -> None:
    sql = """
        INSERT INTO meal_logs
            (log_id, patient_id, logged_at, meal_type, description,
             calories_kcal, carbs_g, protein_g, fat_g, fiber_g, glycemic_index)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (log_id, logged_at) DO NOTHING;
    """
    tuples = [
        (
            r["log_id"],
            r["patient_id"],
            r["logged_at"],
            r["meal_type"],
            _nullify(r["description"]),
            _float_or_none(r["calories_kcal"]),
            _float_or_none(r["carbs_g"]),
            _float_or_none(r["protein_g"]),
            _float_or_none(r["fat_g"]),
            _float_or_none(r["fiber_g"]),
            _int_or_none(r["glycemic_index"]),
        )
        for r in rows
    ]
    n = bulk_insert(conn, sql, tuples, batch_size)
    logger.info("meal_logs: %d rows inserted", n)


def insert_steps(conn, rows: list[dict], batch_size: int) -> None:
    sql = """
        INSERT INTO step_records
            (step_id, patient_id, record_date, step_count,
             distance_meters, floors_climbed, active_minutes,
             sedentary_minutes, calories_burned)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (patient_id, record_date) DO NOTHING;
    """
    tuples = [
        (
            r["step_id"],
            r["patient_id"],
            r["record_date"],
            int(r["step_count"]),
            _float_or_none(r["distance_meters"]),
            _int_or_none(r["floors_climbed"]),
            _int_or_none(r["active_minutes"]),
            _int_or_none(r["sedentary_minutes"]),
            _float_or_none(r["calories_burned"]),
        )
        for r in rows
    ]
    n = bulk_insert(conn, sql, tuples, batch_size)
    logger.info("step_records: %d rows inserted", n)


def insert_activity(conn, rows: list[dict], batch_size: int) -> None:
    sql = """
        INSERT INTO activity_sessions
            (session_id, patient_id, start_time, end_time,
             activity_type, intensity, duration_min, calories_burned,
             avg_heart_rate, max_heart_rate, steps, distance_meters, notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (session_id, start_time) DO NOTHING;
    """
    tuples = [
        (
            r["session_id"],
            r["patient_id"],
            r["start_time"],
            _nullify(r["end_time"]),
            r["activity_type"],
            _nullify(r["intensity"]),
            _int_or_none(r["duration_min"]),
            _float_or_none(r["calories_burned"]),
            _int_or_none(r["avg_heart_rate"]),
            _int_or_none(r["max_heart_rate"]),
            _int_or_none(r["steps"]),
            _float_or_none(r["distance_meters"]),
            _nullify(r.get("notes", "")),
        )
        for r in rows
    ]
    n = bulk_insert(conn, sql, tuples, batch_size)
    logger.info("activity_sessions: %d rows inserted", n)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Insert lifestyle CSVs into DB")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    sleep_rows = read_csv(SYNTHETIC_DIR / "sleep_records.csv")
    meal_rows = read_csv(SYNTHETIC_DIR / "meal_logs.csv")
    step_rows = read_csv(SYNTHETIC_DIR / "step_records.csv")
    activity_rows = read_csv(SYNTHETIC_DIR / "activity_sessions.csv")

    logger.info(
        "Loaded: sleep=%d  meals=%d  steps=%d  activity=%d",
        len(sleep_rows),
        len(meal_rows),
        len(step_rows),
        len(activity_rows),
    )

    with get_conn() as conn:
        insert_sleep(conn, sleep_rows, args.batch_size)
        insert_meals(conn, meal_rows, args.batch_size)
        insert_steps(conn, step_rows, args.batch_size)
        insert_activity(conn, activity_rows, args.batch_size)

    logger.info("All lifestyle data inserted successfully.")


if __name__ == "__main__":
    main()
