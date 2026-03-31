"""
11_generate_cgm_data.py

Generates two years of synthetic CGM glucose readings (every 5 minutes) and
corresponding wearable activity data (HR + calories) for every patient that
exists in the database, then inserts the rows directly.

Glucose model:
  - Per-patient fasting baseline: 80–160 mg/dL (Gaussian, seed = patient_id)
  - Post-meal spikes at breakfast (~7 h), lunch (~12 h), dinner (~18 h), snack (~21 h)
  - AR(1) autocorrelation for physiological continuity
  - Clinically plausible HR and calorie-burn estimates per reading

Run from the backend directory (or inside the Docker container):

    python scripts/11_generate_cgm_data.py

Options:
    --patient-id UUID    Process only one patient (default: all patients)
    --start  YYYY-MM-DD  Start date  (default: 2 years ago)
    --end    YYYY-MM-DD  End date    (default: today)
    --batch-size INT     Rows per INSERT batch (default: 500)
    --device-type TEXT   Libre | Dexcom  (default: Libre)

Idempotent: patients that already have glucose data in the requested range
are skipped automatically.  Run with --start / --end to fill a different window.
"""

from __future__ import annotations

import argparse
import logging
import random
import secrets
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR / "src"))

from psycopg2.extras import execute_values  # noqa: E402

from healthsync.db.connection import get_conn  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CGM_INTERVAL_MIN = 5  # minutes between readings

# (start_hour, end_hour, mean_spike_mg_dl, std_spike_mg_dl)
MEAL_WINDOWS = [
    (6.5, 9.0, 55, 15),  # breakfast
    (11.5, 13.5, 50, 15),  # lunch
    (17.5, 20.0, 60, 20),  # dinner
    (21.0, 22.5, 25, 10),  # evening snack
]

DEVICE_TYPE_MAP = {
    "Libre": "LibreSensor",
    "Dexcom": "Dexcom",
}


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _fetch_patients(conn) -> list[dict]:
    """Return all patients with the first available device_id (or None)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.patient_id,
                   (SELECT d.device_id
                    FROM devices d
                    WHERE d.patient_id = p.patient_id
                    ORDER BY d.created_at
                    LIMIT 1) AS device_id
            FROM patients p
            ORDER BY p.patient_id
            """
        )
        rows = cur.fetchall()
    return [
        {"patient_id": str(r[0]), "device_id": str(r[1]) if r[1] else None}
        for r in rows
    ]


def _ensure_device(conn, patient_id: str, device_type_label: str) -> str:
    """Return an existing device_id, or create a synthetic device if none exists."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT device_id FROM devices WHERE patient_id = %s ORDER BY created_at LIMIT 1",
            (patient_id,),
        )
        row = cur.fetchone()
    if row:
        return str(row[0])

    dtype_enum = DEVICE_TYPE_MAP.get(device_type_label, "LibreSensor")
    device_id = str(uuid4())
    serial = f"SN-SYN-{secrets.token_hex(4).upper()}"

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO devices (device_id, patient_id, type, serial_number, status, created_at)
            VALUES (%s, %s, %s::device_type, %s, 'ACTIVE'::device_status, NOW())
            ON CONFLICT (serial_number) DO NOTHING
            """,
            (device_id, patient_id, dtype_enum, serial),
        )
    logger.info(f"  Created new synthetic device {device_id} for patient {patient_id}")
    return device_id


def _has_data_in_range(
    conn, patient_id: str, start_dt: datetime, end_dt: datetime
) -> bool:
    """Return True if any glucose readings already exist for this patient and range."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM glucose_readings
            WHERE patient_id = %s
              AND timestamp >= %s
              AND timestamp <= %s
            LIMIT 1
            """,
            (patient_id, start_dt, end_dt),
        )
        return cur.fetchone() is not None


# ---------------------------------------------------------------------------
# Glucose simulation
# ---------------------------------------------------------------------------


def _build_timestamps(start: date, end: date) -> list[datetime]:
    """Build a list of UTC datetime objects every CGM_INTERVAL_MIN minutes."""
    timestamps: list[datetime] = []
    current = datetime(start.year, start.month, start.day, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=timezone.utc)
    while current <= end_dt:
        timestamps.append(current)
        current += timedelta(minutes=CGM_INTERVAL_MIN)
    return timestamps


def _simulate_patient(
    patient_id: str,
    timestamps: list[datetime],
    device_type: str,
) -> list[dict]:
    """
    Simulate a full CGM series for one patient.

    Returns a list of dicts with keys:
        reading_id, timestamp, value, device_type, hr, calories
    """
    rng = random.Random(patient_id)

    # Per-patient physiology (seeded so re-runs produce identical data)
    fasting = max(80.0, min(160.0, rng.gauss(115, 18)))
    noise_std = rng.uniform(3.5, 7.5)
    ar1 = 0.97  # autocorrelation coefficient

    # Pre-compute one meal spike per meal window per calendar day
    # day_spikes[(date, meal_idx)] = (peak_hour_float, magnitude_mg_dl)
    day_spikes: dict[tuple, tuple] = {}
    for d in sorted({ts.date() for ts in timestamps}):
        for idx, (h_start, h_end, mu, sigma) in enumerate(MEAL_WINDOWS):
            if rng.random() < 0.85:  # 85 % chance a meal was eaten
                peak_hour = rng.uniform(h_start, h_end)
                magnitude = max(10.0, rng.gauss(mu, sigma))
                day_spikes[(d, idx)] = (peak_hour, magnitude)

    records: list[dict] = []
    prev_glucose = fasting

    for ts in timestamps:
        hour_frac = ts.hour + ts.minute / 60.0
        d = ts.date()

        # ---------- meal contribution ----------
        meal_effect = 0.0
        # Only apply meal effects outside the sleeping window (0:30–6:00)
        if not (0.5 <= hour_frac < 6.0):
            for idx in range(len(MEAL_WINDOWS)):
                key = (d, idx)
                if key not in day_spikes:
                    continue
                peak_h, mag = day_spikes[key]
                dt = hour_frac - peak_h
                # Rise 15 min before peak, hold 30 min, decay over 2 h
                if -0.25 <= dt < 0.0:
                    t_norm = (dt + 0.25) / 0.25
                elif 0.0 <= dt < 0.5:
                    t_norm = 1.0
                elif 0.5 <= dt < 2.5:
                    t_norm = max(0.0, 1.0 - (dt - 0.5) / 2.0)
                else:
                    t_norm = 0.0
                meal_effect += mag * t_norm

        # ---------- AR(1) glucose model ----------
        target = fasting + meal_effect
        glucose = ar1 * prev_glucose + (1.0 - ar1) * target + rng.gauss(0, noise_std)
        glucose = max(40.0, min(400.0, glucose))
        prev_glucose = glucose

        # ---------- Heart rate (correlated with glucose change / meal) ----------
        hr = int(max(40, min(180, 62 + meal_effect * 0.25 + rng.gauss(0, 7))))

        # ---------- Calories burned (kcal / 5-min period) ----------
        cal = round(max(0.3, 1.05 + meal_effect * 0.008 + rng.gauss(0, 0.25)), 3)

        records.append(
            {
                "reading_id": str(uuid4()),
                "timestamp": ts,
                "value": round(glucose, 2),
                "device_type": device_type,
                "hr": hr,
                "calories": cal,
            }
        )

    return records


# ---------------------------------------------------------------------------
# Batch insert
# ---------------------------------------------------------------------------


def _insert_patient_data(
    conn,
    patient_id: str,
    device_id: str,
    records: list[dict],
    batch_size: int,
) -> tuple[int, int]:
    """Bulk-insert glucose_readings and activity_data in batches."""
    glucose_inserted = 0
    activity_inserted = 0

    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]

        # ---- glucose_readings ----
        glucose_rows = [
            (
                r["reading_id"],
                patient_id,
                device_id,
                r["timestamp"],
                r["value"],
                r["device_type"],
            )
            for r in batch
        ]
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO glucose_readings
                    (reading_id, patient_id, device_id, timestamp, value,
                     unit, device_type, acquired_at)
                VALUES %s
                ON CONFLICT DO NOTHING
                """,
                glucose_rows,
                template="(%s, %s, %s, %s, %s, 'mg/dL'::glucose_unit, %s, NOW())",
            )
        glucose_inserted += len(batch)

        # ---- activity_data ----
        activity_rows = [
            (
                str(uuid4()),
                patient_id,
                r["reading_id"],
                r["timestamp"],
                r["timestamp"],
                r["hr"],
                r["calories"],
            )
            for r in batch
        ]
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO activity_data
                    (activity_id, patient_id, reading_id, reading_timestamp,
                     timestamp, heart_rate, calories_burned, created_at)
                VALUES %s
                ON CONFLICT DO NOTHING
                """,
                activity_rows,
                template="(%s, %s, %s, %s, %s, %s, %s, NOW())",
            )
        activity_inserted += len(batch)

        if (i // batch_size + 1) % 10 == 0:
            logger.info(f"    … {glucose_inserted:,} / {len(records):,} rows processed")

    return glucose_inserted, activity_inserted


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def generate(
    patient_id_filter: str | None,
    start: date,
    end: date,
    batch_size: int,
    device_type: str,
) -> None:
    timestamps = _build_timestamps(start, end)
    start_dt = datetime(
        start.year, start.month, start.day, 0, 0, 0, tzinfo=timezone.utc
    )
    end_dt = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=timezone.utc)

    logger.info(
        f"Date range : {start} → {end}  ({len(timestamps):,} timestamps per patient)"
    )
    logger.info(f"Batch size : {batch_size}  |  Device type: {device_type}")

    with get_conn() as conn:
        patients = _fetch_patients(conn)

    if patient_id_filter:
        patients = [p for p in patients if p["patient_id"] == patient_id_filter]
        if not patients:
            logger.error(f"Patient {patient_id_filter} not found in the database.")
            sys.exit(1)

    logger.info(f"Patients   : {len(patients)}")

    for idx, p in enumerate(patients, 1):
        pid = p["patient_id"]
        logger.info(f"[{idx}/{len(patients)}] Patient {pid}")

        # Idempotency check
        with get_conn() as conn:
            if _has_data_in_range(conn, pid, start_dt, end_dt):
                logger.info("  Skipping – glucose data already exists in this range.")
                continue

            # Ensure there is a device row
            dev_id = _ensure_device(conn, pid, device_type)

        # Simulate (CPU-bound, outside DB connection)
        logger.info(f"  Simulating {len(timestamps):,} readings…")
        records = _simulate_patient(pid, timestamps, device_type)

        # Insert
        with get_conn() as conn:
            g_cnt, a_cnt = _insert_patient_data(conn, pid, dev_id, records, batch_size)

        logger.info(
            f"  ✓ Inserted {g_cnt:,} glucose readings + {a_cnt:,} activity rows"
        )

    logger.info("Done.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate 2 years of synthetic CGM data and insert into the DB."
    )
    parser.add_argument(
        "--patient-id",
        dest="patient_id",
        default=None,
        metavar="UUID",
        help="Process only this patient UUID (default: all patients).",
    )
    parser.add_argument(
        "--start",
        default=None,
        metavar="YYYY-MM-DD",
        help="Start date (default: 2 years before --end).",
    )
    parser.add_argument(
        "--end",
        default=None,
        metavar="YYYY-MM-DD",
        help="End date (default: today).",
    )
    parser.add_argument(
        "--batch-size",
        dest="batch_size",
        type=int,
        default=500,
        metavar="N",
        help="Rows per INSERT batch (default: 500).",
    )
    parser.add_argument(
        "--device-type",
        dest="device_type",
        default="Libre",
        choices=["Libre", "Dexcom"],
        help="CGM device type label (default: Libre).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    today = date.today()
    end_date = date.fromisoformat(args.end) if args.end else today
    start_date = (
        date.fromisoformat(args.start)
        if args.start
        else end_date.replace(year=end_date.year - 2)
    )

    generate(
        patient_id_filter=args.patient_id,
        start=start_date,
        end=end_date,
        batch_size=args.batch_size,
        device_type=args.device_type,
    )
