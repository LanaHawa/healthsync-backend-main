"""
09_generate_lifestyle_data.py
Generates 2 years of synthetic lifestyle data (sleep, meals, steps, activity
sessions) for every patient found in the database and writes four CSV files:

  data/synthetic_data/sleep_records.csv
  data/synthetic_data/meal_logs.csv
  data/synthetic_data/step_records.csv
  data/synthetic_data/activity_sessions.csv

Run from the backend directory:
  python scripts/09_generate_lifestyle_data.py

Or target a specific patient:
  python scripts/09_generate_lifestyle_data.py --patient-id <uuid>

Date range defaults to 2 years ending today.  Override with --start / --end.
"""

import csv
import logging
import random
import sys
import argparse
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from uuid import uuid4

SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent
SYNTHETIC_DIR = BACKEND_DIR / "data" / "synthetic_data"
sys.path.insert(0, str(BACKEND_DIR / "src"))

from healthsync.db.connection import get_conn  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Constants – clinically plausible for a T2D cohort
# ---------------------------------------------------------------------------

MEAL_TYPES = ["BREAKFAST", "LUNCH", "DINNER", "SNACK"]

MEAL_PROFILES = {
    "BREAKFAST": {
        "hour_range": (6, 10),
        "calories": (250, 550),
        "carbs_g": (30, 80),
        "protein_g": (10, 25),
        "fat_g": (8, 25),
        "fiber_g": (2, 10),
        "gi_range": (30, 70),
        "descriptions": [
            "Oatmeal with berries and nuts",
            "Scrambled eggs with whole-wheat toast",
            "Greek yogurt with granola and fruit",
            "Whole-grain cereal with low-fat milk",
            "Avocado toast with poached egg",
            "Smoothie with spinach, banana and protein powder",
            "Cottage cheese with sliced tomatoes",
        ],
    },
    "LUNCH": {
        "hour_range": (11, 14),
        "calories": (400, 750),
        "carbs_g": (40, 90),
        "protein_g": (20, 45),
        "fat_g": (10, 30),
        "fiber_g": (5, 15),
        "gi_range": (35, 65),
        "descriptions": [
            "Grilled chicken salad with vinaigrette",
            "Whole-wheat sandwich with turkey and veggies",
            "Lentil soup with multigrain bread",
            "Brown rice bowl with black beans and salsa",
            "Tuna wrap with mixed greens",
            "Quinoa salad with roasted vegetables",
            "Vegetable stir-fry with tofu and brown rice",
        ],
    },
    "DINNER": {
        "hour_range": (17, 21),
        "calories": (450, 850),
        "carbs_g": (35, 95),
        "protein_g": (25, 55),
        "fat_g": (12, 35),
        "fiber_g": (5, 18),
        "gi_range": (30, 60),
        "descriptions": [
            "Baked salmon with roasted asparagus and quinoa",
            "Chicken stir-fry with broccoli and brown rice",
            "Lentil and vegetable curry with basmati rice",
            "Grilled pork tenderloin with sweet potato and green beans",
            "Pasta primavera with whole-grain pasta",
            "Turkey meatballs with zucchini noodles",
            "Black bean tacos with corn tortillas and salsa",
        ],
    },
    "SNACK": {
        "hour_range": (9, 22),
        "calories": (80, 250),
        "carbs_g": (8, 35),
        "protein_g": (3, 15),
        "fat_g": (2, 12),
        "fiber_g": (1, 6),
        "gi_range": (20, 55),
        "descriptions": [
            "Apple slices with almond butter",
            "Handful of mixed nuts",
            "Celery with hummus",
            "Low-fat cheese and whole-grain crackers",
            "Hard-boiled egg",
            "Carrot sticks with guacamole",
            "Small cup of plain Greek yogurt",
        ],
    },
}

ACTIVITY_TYPES = [
    "WALKING",
    "RUNNING",
    "CYCLING",
    "SWIMMING",
    "STRENGTH_TRAINING",
    "YOGA",
    "HIIT",
]
ACTIVITY_INTENSITY = {
    "WALKING": ("LOW", (20, 60), (120, 210)),
    "RUNNING": ("HIGH", (20, 50), (280, 650)),
    "CYCLING": ("MODERATE", (30, 90), (200, 700)),
    "SWIMMING": ("MODERATE", (25, 60), (200, 500)),
    "STRENGTH_TRAINING": ("MODERATE", (30, 75), (150, 450)),
    "YOGA": ("LOW", (30, 60), (80, 250)),
    "HIIT": ("HIGH", (20, 40), (250, 600)),
}
# (intensity_label, duration_min_range, calories_range)

ACTIVITY_HR = {
    "LOW": (80, 110),
    "MODERATE": (110, 145),
    "HIGH": (145, 185),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rand_float(lo: float, hi: float, dp: int = 1) -> float:
    return round(random.uniform(lo, hi), dp)


def _rand_int(lo: int, hi: int) -> int:
    return random.randint(lo, hi)


def _ts(d: date, hour: int, minute: int = 0) -> str:
    """Return ISO-8601 UTC timestamptz string."""
    return datetime(
        d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc
    ).isoformat()


def _jitter_minutes(target: int, spread: int = 20) -> int:
    return max(5, target + random.randint(-spread, spread))


# ---------------------------------------------------------------------------
# Per-patient generators
# ---------------------------------------------------------------------------


def gen_sleep(patient_id: str, start_date: date, end_date: date) -> list[dict]:
    rows = []
    d = start_date
    while d <= end_date:
        # ~95 % of nights have data (skip some for realism)
        if random.random() < 0.05:
            d += timedelta(days=1)
            continue

        # Bedtime: 21:00–01:00 (next day)
        bedtime_hour = random.randint(21, 25)  # 25 = 01:00 next day
        bedtime_minute = random.randint(0, 59)
        actual_bed_hour = bedtime_hour % 24
        bed_day = d if bedtime_hour < 24 else d + timedelta(days=1)
        sleep_start = datetime(
            bed_day.year,
            bed_day.month,
            bed_day.day,
            actual_bed_hour,
            bedtime_minute,
            tzinfo=timezone.utc,
        )

        # Duration: 5.5–8.5 h
        total_min = _jitter_minutes(420, 60)  # ~7 h ± 60 min
        total_min = max(200, min(total_min, 540))

        sleep_end = sleep_start + timedelta(minutes=total_min)

        # Stage breakdown: deep ~20 %, REM ~25 %, light remainder
        deep_min = int(total_min * random.uniform(0.15, 0.25))
        rem_min = int(total_min * random.uniform(0.20, 0.30))
        light_min = total_min - deep_min - rem_min
        awakenings = _rand_int(0, 4)
        quality = min(
            10,
            max(
                1,
                int(
                    7
                    + (total_min - 420) / 60 * 2
                    - awakenings * 0.5
                    + random.uniform(-1.5, 1.5)
                ),
            ),
        )

        rows.append(
            {
                "sleep_id": str(uuid4()),
                "patient_id": patient_id,
                "sleep_start": sleep_start.isoformat(),
                "sleep_end": sleep_end.isoformat(),
                "duration_min": total_min,
                "deep_sleep_min": deep_min,
                "rem_sleep_min": rem_min,
                "light_sleep_min": light_min,
                "awakenings": awakenings,
                "quality_score": quality,
                "recorded_at": sleep_end.isoformat(),
            }
        )
        d += timedelta(days=1)
    return rows


def gen_meals(patient_id: str, start_date: date, end_date: date) -> list[dict]:
    rows = []
    d = start_date
    while d <= end_date:
        # Always breakfast + lunch + dinner; 50 % chance of a snack
        meals_today = ["BREAKFAST", "LUNCH", "DINNER"]
        if random.random() < 0.5:
            meals_today.append("SNACK")

        for meal_type in meals_today:
            p = MEAL_PROFILES[meal_type]
            h = _rand_int(*p["hour_range"])
            m = _rand_int(0, 59)
            logged_at = datetime(d.year, d.month, d.day, h, m, tzinfo=timezone.utc)

            rows.append(
                {
                    "log_id": str(uuid4()),
                    "patient_id": patient_id,
                    "logged_at": logged_at.isoformat(),
                    "meal_type": meal_type,
                    "description": random.choice(p["descriptions"]),
                    "calories_kcal": _rand_float(*p["calories"]),
                    "carbs_g": _rand_float(*p["carbs_g"]),
                    "protein_g": _rand_float(*p["protein_g"]),
                    "fat_g": _rand_float(*p["fat_g"]),
                    "fiber_g": _rand_float(*p["fiber_g"]),
                    "glycemic_index": _rand_int(*p["gi_range"]),
                }
            )
        d += timedelta(days=1)
    return rows


def gen_steps(patient_id: str, start_date: date, end_date: date) -> list[dict]:
    rows = []
    d = start_date
    # Patient baseline step tendency (4k–11k)
    baseline = _rand_int(4000, 11000)
    while d <= end_date:
        # Weekends slightly less active
        if d.weekday() >= 5:
            steps = int(baseline * random.uniform(0.7, 1.1))
        else:
            steps = int(baseline * random.uniform(0.85, 1.25))
        steps = max(500, steps)

        distance_m = round(steps * 0.762, 1)  # avg stride ~76 cm
        floors = _rand_int(0, 12)
        active_min = min(int(steps / 100), 180) + _rand_int(-10, 10)
        active_min = max(0, active_min)
        sedentary_min = max(0, 1440 - active_min - _rand_int(360, 540))
        calories = round(steps * 0.04 + random.uniform(-30, 30), 1)

        rows.append(
            {
                "step_id": str(uuid4()),
                "patient_id": patient_id,
                "record_date": d.isoformat(),
                "step_count": steps,
                "distance_meters": distance_m,
                "floors_climbed": floors,
                "active_minutes": active_min,
                "sedentary_minutes": sedentary_min,
                "calories_burned": round(max(0, calories), 1),
            }
        )
        d += timedelta(days=1)
    return rows


def gen_activity_sessions(
    patient_id: str, start_date: date, end_date: date
) -> list[dict]:
    rows = []
    d = start_date
    # Each patient has a preferred activity (70 % of sessions)
    preferred = random.choice(ACTIVITY_TYPES)
    while d <= end_date:
        # ~55 % chance of an activity session on any given day
        if random.random() > 0.55:
            d += timedelta(days=1)
            continue

        activity_type = (
            preferred if random.random() < 0.70 else random.choice(ACTIVITY_TYPES)
        )
        intensity_label, dur_range, cal_range = ACTIVITY_INTENSITY[activity_type]
        hr_range = ACTIVITY_HR[intensity_label]

        duration = _rand_int(*dur_range)
        calories = _rand_float(*cal_range)
        avg_hr = _rand_int(*hr_range)
        max_hr = min(200, avg_hr + _rand_int(10, 35))

        # Typical times: morning (06-09), lunch (11-13), evening (17-20)
        start_hour = random.choice(
            [_rand_int(6, 9), _rand_int(11, 13), _rand_int(17, 20)]
        )
        start_minute = _rand_int(0, 59)
        start_dt = datetime(
            d.year, d.month, d.day, start_hour, start_minute, tzinfo=timezone.utc
        )
        end_dt = start_dt + timedelta(minutes=duration)

        # Steps only for walking/running
        steps = None
        if activity_type in ("WALKING", "RUNNING"):
            steps = int(duration * random.uniform(80, 180))
        distance = None
        if activity_type in ("WALKING", "RUNNING", "CYCLING"):
            speed_m_per_min = {
                "WALKING": random.uniform(70, 110),
                "RUNNING": random.uniform(150, 280),
                "CYCLING": random.uniform(200, 500),
            }[activity_type]
            distance = round(duration * speed_m_per_min, 1)

        rows.append(
            {
                "session_id": str(uuid4()),
                "patient_id": patient_id,
                "start_time": start_dt.isoformat(),
                "end_time": end_dt.isoformat(),
                "activity_type": activity_type,
                "intensity": intensity_label,
                "duration_min": duration,
                "calories_burned": calories,
                "avg_heart_rate": avg_hr,
                "max_heart_rate": max_hr,
                "steps": steps if steps is not None else "",
                "distance_meters": distance if distance is not None else "",
                "notes": "",
            }
        )
        d += timedelta(days=1)
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def fetch_patient_ids() -> list[str]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT patient_id FROM patients ORDER BY patient_id;")
            return [str(r[0]) for r in cur.fetchall()]


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        logger.warning("No rows – skipping %s", path.name)
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Wrote %d rows → %s", len(rows), path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic lifestyle data")
    parser.add_argument("--patient-id", help="Limit to a single patient UUID")
    parser.add_argument(
        "--start",
        default=(date.today() - timedelta(days=730)).isoformat(),
        help="Start date YYYY-MM-DD (default: 2 years ago)",
    )
    parser.add_argument(
        "--end",
        default=date.today().isoformat(),
        help="End date YYYY-MM-DD (default: today)",
    )
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)
    logger.info("Date range: %s → %s", start_date, end_date)

    if args.patient_id:
        patient_ids = [args.patient_id]
    else:
        patient_ids = fetch_patient_ids()

    logger.info("Generating lifestyle data for %d patient(s)…", len(patient_ids))

    all_sleep: list[dict] = []
    all_meals: list[dict] = []
    all_steps: list[dict] = []
    all_activity: list[dict] = []

    for pid in patient_ids:
        random.seed(pid)  # reproducible per-patient
        all_sleep += gen_sleep(pid, start_date, end_date)
        all_meals += gen_meals(pid, start_date, end_date)
        all_steps += gen_steps(pid, start_date, end_date)
        all_activity += gen_activity_sessions(pid, start_date, end_date)
        logger.info(
            "  %s: sleep=%d meals=%d steps=%d activity=%d",
            pid,
            sum(1 for r in all_sleep if r["patient_id"] == pid),
            sum(1 for r in all_meals if r["patient_id"] == pid),
            sum(1 for r in all_steps if r["patient_id"] == pid),
            sum(1 for r in all_activity if r["patient_id"] == pid),
        )

    write_csv(SYNTHETIC_DIR / "sleep_records.csv", all_sleep)
    write_csv(SYNTHETIC_DIR / "meal_logs.csv", all_meals)
    write_csv(SYNTHETIC_DIR / "step_records.csv", all_steps)
    write_csv(SYNTHETIC_DIR / "activity_sessions.csv", all_activity)

    logger.info("Done. CSVs written to %s", SYNTHETIC_DIR)


if __name__ == "__main__":
    main()
