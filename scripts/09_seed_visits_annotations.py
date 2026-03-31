"""
Seed visits, visit summaries, visualizations, and annotations.

Depends on: already-inserted patients, clinicians, access_permissions, clinics.
Run after 07_insert_data.py.
"""

import argparse
import json
import logging
import math
import random
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR / "src"))

from healthsync.db.connection import get_conn

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

random.seed(42)

# ──────────────────────────────────────────────────────────────────────────────
# Content pools
# ──────────────────────────────────────────────────────────────────────────────
VISIT_NOTES = [
    "Patient reports increased fatigue and occasional headaches. CGM data reviewed.",
    "Routine diabetes management follow-up. Patient adherent to current regimen.",
    "Patient experiencing more frequent hypoglycemic episodes overnight. Basal insulin adjusted.",
    "Review of last 2 weeks CGM data. Time-in-range improved to 72%.",
    "Patient started new exercise program; adjustments made to pre-meal bolus.",
    "Concerns about meal-time spikes. Discussed carbohydrate counting strategies.",
    "Patient travel upcoming; reviewed sick-day rules and time-zone adjustments.",
    "Quarterly check-in. A1C result reviewed; target not yet met, plan revised.",
    "Post-hospitalization follow-up. Medication reconciliation completed.",
    "Patient feels CGM sensor placement uncomfortable. Alternate sites discussed.",
]

CLINICAL_FINDINGS = [
    "Blood glucose control suboptimal with multiple excursions above 10 mmol/L in AM. "
    "No evidence of DKA. Weight stable.",
    "Time-in-range at 68%, improved from 58% last visit. Overnight lows persisting "
    "between 02:00–04:00. Patient sleeping through alerts.",
    "Fasting glucose consistently elevated (8–11 mmol/L). Post-prandial spikes "
    "within acceptable range. Suspect dawn phenomenon.",
    "Excellent glucose control; TIR 80%. No significant hypoglycemic events recorded. "
    "Patient adherent to bolus timing.",
    "Hyperglycemia observed on weekends correlating with dietary changes. Stress-related "
    "glucose variability noted mid-week.",
    "A1C 7.8%, down from 8.4% three months ago. Continued improvement. Renal function "
    "panel normal. BP 128/78.",
]

DECISIONS = [
    "Increase basal insulin by 2 units. Continue current mealtime regimen.",
    "Reduce overnight basal profile by 20% between 00:00–03:00 to mitigate nocturnal hypoglycemia.",
    "Add Metformin 500mg OD. Re-assess in 4 weeks. Referral to dietitian placed.",
    "No medication changes. Reinforce meal timing and carb counting education.",
    "Switch to closed-loop system discussed. Patient to consider CGM upgrade.",
    "Bolus dose adjustment: reduce correction factor from 1:3 to 1:4 mmol/L.",
    "Order repeat HbA1c, renal panel, lipid profile. Revisit in 3 months.",
]

FOLLOW_UP_PLANS = [
    "Return in 3 months or sooner if glucose control worsens.",
    "Follow up in 4 weeks to assess basal adjustment.",
    "Dietitian appointment scheduled. Review CGM data in 6 weeks.",
    "Phone check-in in 2 weeks; full visit in 8 weeks.",
    "Patient to download CGM data and send via portal before next visit.",
    None,
    None,
]

AVS_CONTENT_TEMPLATES = [
    (
        "After-Visit Summary\n"
        "Date: {date}\n\n"
        "Thank you for your visit today. Here is a summary of what was discussed:\n\n"
        "Key Findings: {findings}\n\n"
        "Plan: {plan}\n\n"
        "Please contact the clinic if you experience severe hypoglycemia (glucose < 3.9 mmol/L), "
        "or if you have any questions about your new medication dose."
    ),
    (
        "Visit Summary – {date}\n\n"
        "Your care team reviewed your CGM data and discussed the following:\n\n"
        "{findings}\n\n"
        "Next Steps: {plan}\n\n"
        "Your next appointment is scheduled. Please bring your CGM device."
    ),
]

ACTION_DESCRIPTIONS = [
    (
        "PATIENT",
        "Log meals in the CGM companion app for at least 7 days before next visit.",
    ),
    ("PATIENT", "Check fasting glucose every morning and record in your logbook."),
    ("PATIENT", "Contact the clinic immediately if glucose is below 3.5 mmol/L."),
    ("PATIENT", "Pick up new CGM sensors from the pharmacy."),
    ("CLINICIAN", "Order repeat HbA1c and kidney function panel."),
    ("CLINICIAN", "Send referral to endocrinologist for insulin pump assessment."),
    ("CLINICIAN", "Follow up with patient in 2 weeks via phone."),
    ("CLINICIAN", "Review uploaded CGM data before next appointment."),
    ("SYSTEM", "Generate monthly glucose trend report."),
    ("SYSTEM", "Send appointment reminder 48 hours before scheduled visit."),
]

ANNOTATION_CONTENT = {
    "TEXT": [
        "Glucose spike at lunch correlates with high-carb meal reported by patient.",
        "Overnight lows may be related to evening exercise. Discussed with patient.",
        "Pattern of morning hyperglycemia consistent with dawn phenomenon.",
        "Rapid rise after dinner — patient admitted to skipping bolus on two occasions.",
        "Good time-in-range overall this period, notable improvement from last visit.",
        "Alert fatigue suspected — patient silencing alarms overnight.",
    ],
    "HIGHLIGHT": [
        "Highlighted hypoglycemic cluster: 3 events in 5 days.",
        "Highlighted post-prandial excursion period (12:00–14:00).",
        "Highlighted stable overnight period — basal rate appears appropriate.",
        "Highlighted weekend variability — compare weekday vs weekend patterns.",
    ],
    "COMMENT": [
        "Discuss mealtime bolus timing at next visit.",
        "Review with dietitian: carb estimation accuracy.",
        "Consider switching to closed-loop system.",
        "Patient expressed concern about hypoglycemia unawareness.",
        "Confirm sensor calibration schedule with patient.",
    ],
    "MARKER": [
        "Sick day — insulin requirements increased.",
        "Exercise event — glucose drop noted 90 min post-activity.",
        "Travel: time-zone shift affecting basal timing.",
        "Missed medication dose reported.",
    ],
    "FREEHAND": [
        "Circled hypoglycemic event on glucose trend",
        "Highlighted overnight lows — basal adjustment needed",
        "Marked post-prandial spike pattern",
        "Bracketed period of glucose variability",
        "Circled dawn phenomenon region",
        "Annotated meal event with glucose response",
    ],
}

VIZ_TYPES = ["GLUCOSE_TREND", "TIME_IN_RANGE", "HEATMAP", "SUMMARY"]
VIZ_TITLES = {
    "GLUCOSE_TREND": [
        "14-Day Glucose Trend",
        "7-Day CGM Overview",
        "30-Day Glucose Trend",
    ],
    "TIME_IN_RANGE": ["Time In Range Summary", "TIR Breakdown", "Daily TIR Analysis"],
    "HEATMAP": ["Glucose Heatmap", "Weekly Glucose Heatmap", "Daily Pattern Heatmap"],
    "SUMMARY": ["Visit Summary Chart", "Patient Overview", "Glycemic Summary"],
}

# Ink stroke colors used by clinicians on the multitouch surface
STROKE_COLORS = ["#1a1a2e", "#1146d8", "#b91c1c", "#15803d", "#7c3aed", "#ea580c"]

# Canvas logical dimensions (must match CANVAS_W/CANVAS_H in AnnotateOverlay.tsx)
CANVAS_W = 1600
CANVAS_H = 780


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _uid() -> str:
    return str(uuid4())


def _rand_ts(days_ago_max: int, days_ago_min: int = 0) -> datetime:
    """Random timestamp between [now - days_ago_max, now - days_ago_min]."""
    now = datetime.now(tz=timezone.utc)
    offset = timedelta(
        seconds=random.randint(
            int(timedelta(days=days_ago_min).total_seconds()),
            int(timedelta(days=days_ago_max).total_seconds()),
        )
    )
    return now - offset


# ── Freehand stroke data generation ───────────────────────────────────────────


def _gen_smooth_stroke(
    start_x: float,
    start_y: float,
    dx: float,
    dy: float,
    n_points: int = 20,
    wobble: float = 8.0,
) -> list[dict]:
    """
    Generate a smooth freehand stroke from (start_x, start_y) in direction (dx, dy)
    with slight random jitter, simulating natural stylus movement.
    """
    pts = []
    t = 0
    pressure_base = random.uniform(0.4, 0.75)
    # Start light, peak mid-stroke, taper at end (natural pen pressure curve)
    for i in range(n_points):
        frac = i / max(n_points - 1, 1)
        pressure = pressure_base * (1 - abs(frac - 0.5) * 0.7) + random.uniform(
            -0.05, 0.05
        )
        pressure = max(0.1, min(1.0, pressure))
        x = start_x + dx * frac + random.uniform(-wobble, wobble)
        y = start_y + dy * frac + random.uniform(-wobble / 2, wobble / 2)
        # clamp to canvas
        x = max(0, min(CANVAS_W, x))
        y = max(0, min(CANVAS_H, y))
        dt = random.randint(14, 24)  # ~60fps stylus input
        t += dt
        pts.append(
            {"x": round(x, 1), "y": round(y, 1), "pressure": round(pressure, 3), "t": t}
        )
    return pts


def _gen_arc_stroke(
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    ang_start: float = 0,
    ang_end: float = math.pi * 1.5,
    n_points: int = 30,
) -> list[dict]:
    """Elliptical arc stroke — clinician circling a region on the chart."""
    pts = []
    t = 0
    for i in range(n_points):
        frac = i / max(n_points - 1, 1)
        angle = ang_start + (ang_end - ang_start) * frac
        x = cx + rx * math.cos(angle) + random.uniform(-4, 4)
        y = cy + ry * math.sin(angle) + random.uniform(-4, 4)
        x = max(0, min(CANVAS_W, x))
        y = max(0, min(CANVAS_H, y))
        pressure = 0.5 + random.uniform(-0.1, 0.1)
        dt = random.randint(14, 22)
        t += dt
        pts.append(
            {"x": round(x, 1), "y": round(y, 1), "pressure": round(pressure, 3), "t": t}
        )
    return pts


def _gen_freehand_stroke_data() -> dict:
    """
    Generate realistic stroke_data JSON representing 1–4 freehand ink strokes
    drawn by a clinician on the annotation canvas with a stylus or finger.
    """
    num_strokes = random.randint(1, 4)
    strokes = []
    color = random.choice(STROKE_COLORS)
    base_width = random.choice([1.5, 4.0, 9.0])
    tool = random.choices(["pen", "highlighter"], weights=[70, 30])[0]

    for _ in range(num_strokes):
        stroke_type = random.choice(["line", "arc", "bracket"])
        if stroke_type == "line":
            # Horizontal or diagonal emphasis line
            sx = random.uniform(80, CANVAS_W * 0.5)
            sy = random.uniform(100, CANVAS_H - 100)
            dx = random.uniform(200, CANVAS_W * 0.4)
            dy = random.uniform(-40, 40)
            pts = _gen_smooth_stroke(sx, sy, dx, dy, n_points=random.randint(18, 35))
        elif stroke_type == "arc":
            # Circle / ellipse (clinician circling a data point or region)
            cx = random.uniform(200, CANVAS_W - 200)
            cy = random.uniform(120, CANVAS_H - 120)
            rx = random.uniform(60, 160)
            ry = random.uniform(40, 100)
            pts = _gen_arc_stroke(cx, cy, rx, ry, n_points=random.randint(24, 40))
        else:
            # Bracket / brace — two short lines
            sx = random.uniform(100, CANVAS_W * 0.6)
            sy = random.uniform(80, CANVAS_H * 0.5)
            pts = _gen_smooth_stroke(sx, sy, 0, random.uniform(60, 140), n_points=12)
            pts += _gen_smooth_stroke(
                sx, sy + random.uniform(60, 140), random.uniform(30, 80), 0, n_points=8
            )

        strokes.append(
            {
                "id": _uid(),
                "color": color,
                "width": base_width,
                "tool": tool,
                "points": pts,
            }
        )

    return {
        "strokes": strokes,
        "canvasWidth": CANVAS_W,
        "canvasHeight": CANVAS_H,
    }


# ──────────────────────────────────────────────────────────────────────────────
# DB queries
# ──────────────────────────────────────────────────────────────────────────────


def fetch_patient_clinician_pairs(conn) -> list[dict]:
    """Return approved (patient_id, auth_user_id, clinician_id, clinic_id) tuples."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                p.patient_id,
                p.auth_user_id  AS patient_auth_id,
                p.first_name    AS patient_first,
                p.last_name     AS patient_last,
                ap.clinician_id,
                c.auth_user_id  AS clinician_auth_id,
                cc.clinic_id
            FROM access_permissions ap
            JOIN patients p       ON p.patient_id    = ap.patient_id
            JOIN clinicians c     ON c.clinician_id  = ap.clinician_id
            LEFT JOIN clinician_clinic cc ON cc.clinician_id = ap.clinician_id
            WHERE ap.status = 'APPROVED'
            ORDER BY p.patient_id, ap.clinician_id
            """
        )
        rows = cur.fetchall()

    pairs = []
    seen = set()
    for row in rows:
        key = (str(row[0]), str(row[4]))  # patient_id, clinician_id
        if key in seen:
            continue
        seen.add(key)
        pairs.append(
            {
                "patient_id": str(row[0]),
                "patient_auth_id": str(row[1]),
                "patient_name": f"{row[2]} {row[3]}",
                "clinician_id": str(row[4]),
                "clinician_auth_id": str(row[5]),
                "clinic_id": str(row[6]) if row[6] else None,
            }
        )
    return pairs


def visit_exists(
    conn, patient_id: str, clinician_id: str, start_time: datetime
) -> bool:
    """Idempotency guard: skip if a visit with same patient+clinician within 1 hour already exists."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM visits
            WHERE patient_id = %s
              AND clinician_id = %s
              AND ABS(EXTRACT(EPOCH FROM (start_time - %s))) < 3600
            LIMIT 1
            """,
            (patient_id, clinician_id, start_time),
        )
        return cur.fetchone() is not None


# ──────────────────────────────────────────────────────────────────────────────
# Insertion helpers
# ──────────────────────────────────────────────────────────────────────────────


def insert_visit(conn, pair: dict, start_time: datetime) -> dict | None:
    visit_type = random.choice(["FOLLOW_UP", "FOLLOW_UP", "CHECK_IN", "OTHER"])
    other_text = "Urgent glucose review" if visit_type == "OTHER" else None
    duration_mins = random.randint(20, 60)
    end_time = start_time + timedelta(minutes=duration_mins)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO visits (
                visit_id, patient_id, clinician_id, clinic_id,
                start_time, end_time,
                visit_type, visit_type_other_text, notes,
                created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::visit_type_enum, %s, %s, NOW(), NOW())
            RETURNING visit_id, patient_id, clinician_id, clinic_id, start_time, end_time
            """,
            (
                _uid(),
                pair["patient_id"],
                pair["clinician_id"],
                pair["clinic_id"],
                start_time,
                end_time,
                visit_type,
                other_text,
                random.choice(VISIT_NOTES),
            ),
        )
        row = cur.fetchone()

    if not row:
        return None
    return {
        "visit_id": str(row[0]),
        "patient_id": str(row[1]),
        "clinician_id": str(row[2]),
        "clinic_id": str(row[3]) if row[3] else None,
        "clinician_auth_id": pair["clinician_auth_id"],
        "patient_auth_id": pair["patient_auth_id"],
        "start_time": row[4],
        "end_time": row[5],
    }


def insert_visit_summary(conn, visit: dict) -> None:
    findings = random.choice(CLINICAL_FINDINGS)
    decision = random.choice(DECISIONS)
    follow_up = random.choice(FOLLOW_UP_PLANS)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO visit_summaries (
                summary_id, visit_id, created_by, created_at,
                clinical_findings, decisions, follow_up_plan
            )
            VALUES (%s, %s, %s, NOW(), %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                _uid(),
                visit["visit_id"],
                visit["clinician_auth_id"],
                findings,
                decision,
                follow_up,
            ),
        )


def insert_avs(conn, visit: dict) -> None:
    template = random.choice(AVS_CONTENT_TEMPLATES)
    content = template.format(
        date=visit["start_time"].strftime("%B %d, %Y")
        if visit.get("start_time")
        else "N/A",
        findings=random.choice(CLINICAL_FINDINGS),
        plan=random.choice(DECISIONS),
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO after_visit_summaries (
                avs_id, visit_id, created_at, generated_by, delivered_via, content
            )
            VALUES (%s, %s, NOW(), %s, %s::avs_channel, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                _uid(),
                visit["visit_id"],
                visit["clinician_auth_id"],
                random.choice(["EMAIL", "PRINT"]),
                content,
            ),
        )


def insert_visualization(conn, visit: dict, viz_type: str) -> str | None:
    """Insert a visualization and return its visualization_id."""
    title = random.choice(VIZ_TITLES[viz_type])
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO visualizations (
                visualization_id, patient_id, visit_id, type,
                title, config_json, created_at, created_by
            )
            VALUES (%s, %s, %s, %s::visualization_type, %s, '{}'::jsonb, NOW(), %s)
            RETURNING visualization_id
            """,
            (
                _uid(),
                visit["patient_id"],
                visit["visit_id"],
                viz_type,
                title,
                visit["clinician_auth_id"],
            ),
        )
        row = cur.fetchone()
    return str(row[0]) if row else None


def insert_annotation(conn, visit: dict, viz_id: str, ann_type: str) -> None:
    content = random.choice(ANNOTATION_CONTENT[ann_type])

    # Freehand: generate ink stroke data; other types get None
    stroke_data = None
    stroke_color = "#1a1a2e"
    stroke_width = 4.0

    if ann_type == "FREEHAND":
        sd = _gen_freehand_stroke_data()
        stroke_data = json.dumps(sd)
        first_stroke = sd["strokes"][0] if sd["strokes"] else None
        if first_stroke:
            stroke_color = first_stroke["color"]
            stroke_width = first_stroke["width"]

    # For HIGHLIGHT/MARKER attach a random timestamp window inside the visit
    time_start = None
    time_end = None
    if ann_type in ("HIGHLIGHT", "MARKER") and visit.get("start_time"):
        base = visit["start_time"] - timedelta(days=random.randint(1, 14))
        time_start = base
        if ann_type == "HIGHLIGHT":
            time_end = base + timedelta(hours=random.randint(1, 4))

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO annotations (
                annotation_id, visit_id, visualization_id, created_by,
                type, content, time_start, time_end,
                stroke_data, stroke_color, stroke_width,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s::annotation_type, %s, %s, %s, %s, %s, %s, NOW())
            """,
            (
                _uid(),
                visit["visit_id"],
                viz_id,
                visit["clinician_auth_id"],
                ann_type,
                content,
                time_start,
                time_end,
                stroke_data,
                stroke_color,
                stroke_width,
            ),
        )


def insert_action_items(conn, visit: dict, num: int) -> None:
    pool = random.sample(ACTION_DESCRIPTIONS, min(num, len(ACTION_DESCRIPTIONS)))
    for owner_type, description in pool:
        due_date = (
            visit["end_time"] + timedelta(days=random.randint(7, 60))
            if visit.get("end_time")
            else None
        )
        status = random.choices(
            ["OPEN", "IN_PROGRESS", "COMPLETED", "CANCELLED"],
            weights=[50, 20, 25, 5],
        )[0]
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO action_items (
                    action_id, visit_id, patient_id, description,
                    owner_type, status, due_date, created_at, created_by
                )
                VALUES (%s, %s, %s, %s, %s::stakeholder_type, %s::action_status, %s, NOW(), %s)
                """,
                (
                    _uid(),
                    visit["visit_id"],
                    visit["patient_id"],
                    description,
                    owner_type,
                    status,
                    due_date,
                    visit["clinician_auth_id"],
                ),
            )


# ──────────────────────────────────────────────────────────────────────────────
# Main seeder
# ──────────────────────────────────────────────────────────────────────────────


def seed(
    visits_per_patient: int = 3,
    dry_run: bool = False,
) -> None:
    with get_conn() as conn:
        pairs = fetch_patient_clinician_pairs(conn)

    if not pairs:
        logger.error(
            "No approved patient-clinician pairs found. Run 07_insert_data.py first."
        )
        return

    logger.info(f"Found {len(pairs)} approved patient-clinician pairs.")

    # Deduplicate to one pair per patient (pick first assigned clinician)
    seen_patients: dict[str, dict] = {}
    for p in pairs:
        if p["patient_id"] not in seen_patients:
            seen_patients[p["patient_id"]] = p

    patient_pairs = list(seen_patients.values())
    logger.info(
        f"Seeding up to {visits_per_patient} visit(s) each for "
        f"{len(patient_pairs)} patients."
    )

    if dry_run:
        logger.info("DRY RUN — no data will be written.")
        for pair in patient_pairs[:3]:
            logger.info(
                f"  Would create {visits_per_patient} visits for "
                f"{pair['patient_name']} with clinician {pair['clinician_id'][:8]}…"
            )
        return

    total_visits = total_vizs = total_anns = total_actions = 0
    errors = 0

    with get_conn() as conn:
        for pair in patient_pairs:
            # Spread visits evenly across last 12 months
            bucket_days = 365 // visits_per_patient
            for i in range(visits_per_patient):
                days_ago_max = 365 - i * bucket_days
                days_ago_min = max(0, days_ago_max - bucket_days)
                start_time = _rand_ts(days_ago_max, days_ago_min)

                # Idempotency guard
                if visit_exists(
                    conn, pair["patient_id"], pair["clinician_id"], start_time
                ):
                    logger.debug("Skipping duplicate visit")
                    continue

                try:
                    visit = insert_visit(conn, pair, start_time)
                    if not visit:
                        continue
                    total_visits += 1

                    # Visit summary (always)
                    insert_visit_summary(conn, visit)

                    # After-visit summary (60% chance)
                    if random.random() < 0.6:
                        insert_avs(conn, visit)

                    # 1–2 visualizations per visit
                    num_vizs = random.randint(1, 2)
                    viz_types = random.sample(VIZ_TYPES, num_vizs)
                    for viz_type in viz_types:
                        viz_id = insert_visualization(conn, visit, viz_type)
                        if not viz_id:
                            continue
                        total_vizs += 1

                        # 1–2 annotations per visualization
                        ann_types = random.choices(
                            ["TEXT", "HIGHLIGHT", "COMMENT", "MARKER", "FREEHAND"],
                            weights=[30, 15, 25, 10, 20],
                            k=random.randint(1, 3),
                        )
                        for ann_type in ann_types:
                            insert_annotation(conn, visit, viz_id, ann_type)
                            total_anns += 1

                    # 0–2 action items per visit
                    num_actions = random.randint(0, 2)
                    if num_actions:
                        insert_action_items(conn, visit, num_actions)
                        total_actions += num_actions

                except Exception:
                    logger.error(f"Error seeding visit for {pair['patient_name']}:")
                    traceback.print_exc()
                    errors += 1
                    conn.rollback()
                    continue

            logger.info(f"  ✓ {pair['patient_name']}")

    logger.info("=" * 60)
    logger.info(f"  Visits inserted      : {total_visits}")
    logger.info(f"  Visualizations       : {total_vizs}")
    logger.info(f"  Annotations          : {total_anns}")
    logger.info(f"  Action items         : {total_actions}")
    if errors:
        logger.warning(f"  Errors               : {errors}")
    logger.info("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed visits and annotations for HealthSYNC."
    )
    parser.add_argument(
        "--visits-per-patient",
        type=int,
        default=3,
        metavar="N",
        help="Number of visits to create per patient (default: 3).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing to the database.",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("  HealthSYNC — Visit & Annotation Seeder")
    logger.info("=" * 60)

    seed(
        visits_per_patient=args.visits_per_patient,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
