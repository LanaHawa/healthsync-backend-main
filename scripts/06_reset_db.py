"""Reset the HealthSYNC database to a clean state"""

import sys
import logging
import argparse
import traceback
import subprocess
from pathlib import Path

# Add src to path
SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR / "src"))

from healthsync.db.connection import get_conn

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def create_backup_before_reset() -> bool:
    """Create a backup of the current database before resetting."""
    logger.info("Creating backup before reset...")
    try:
        backup_script = SCRIPT_DIR / "04_backup_database.py"
        if not backup_script.exists():
            logger.error(f"Backup script not found: {backup_script}")
            return False

        subprocess.run(
            [sys.executable, str(backup_script), "--type", "full", "--compress"],
            capture_output=True,
            text=True,
            check=True,
        )
        logger.info("Backup created successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Backup failed:\n{e.stderr}")
        logger.warning("Continuing without backup (use --skip-backup to suppress).")
        return False


def drop_timescale_objects():
    """Drop TimescaleDB-specific objects."""
    logger.info("Dropping TimescaleDB objects (if any)...")
    try:
        with get_conn() as conn:
            with conn.cursor() as cursor:
                # continuous aggregates
                try:
                    cursor.execute("""
                        SELECT view_name
                        FROM timescaledb_information.continuous_aggregates
                        WHERE view_schema = 'public';
                    """)
                    for (view_name,) in cursor.fetchall():
                        logger.info(f"Dropping continuous aggregate: {view_name}")
                        cursor.execute(f'DROP MATERIALIZED VIEW IF EXISTS "{view_name}" CASCADE;')
                except Exception:
                    logger.info("No Timescale continuous aggregates info available (ok).")

                # compression policies
                try:
                    cursor.execute("""
                        SELECT format('SELECT remove_compression_policy(%L);', hypertable_name)
                        FROM timescaledb_information.hypertables
                        WHERE hypertable_schema = 'public';
                    """)
                    for (sql,) in cursor.fetchall():
                        try:
                            cursor.execute(sql)
                        except Exception:
                            pass
                except Exception:
                    logger.info("No Timescale hypertables info available (ok).")

        logger.info("Timescale objects drop step completed.")
    except Exception as e:
        logger.warning(f"Failed to drop Timescale objects: {e} (continuing)")


def drop_all_tables(keep_auth_users: bool = False):
    """Drop all tables in a safe order."""
    logger.info("Dropping tables...")

    tables_to_drop = [
        "report_visualizations",
        "abnormal_event_readings",
        "prescription_items",
        "patient_medications",
        "clinician_clinic",
        "notifications",

        "activity_data",
        "prescriptions",
        "allergies",
        "abnormal_events",
        "reports",
        "action_items",
        "agenda_items",
        "bookmarks",
        "annotations",
        "visualizations",
        "after_visit_summaries",
        "visit_summaries",
        "visits",
        "glucose_readings",
        "devices",
        "health_apps",
        "patient_records",
        "audit_log_entries",
        "access_permissions",
        "patients",
        "clinicians",
        "clinics",
        "medications",
        "system_configs",
        "user_preferences",
    ]

    if not keep_auth_users:
        tables_to_drop.append("auth_users")

    with get_conn() as conn:
        with conn.cursor() as cursor:
            for t in tables_to_drop:
                cursor.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE;')
                logger.info(f"Dropped: {t}")


def drop_all_enums():
    """Drop custom ENUM types."""
    logger.info("Dropping enum types...")
    enums = [
        "glucose_unit",
        "agenda_status",
        "report_type",
        "abnormal_event_type",
        "visualization_type",
        "annotation_type",
        "avs_channel",
        "device_status",
        "device_type",
        "action_status",
        "stakeholder_type",
        "permission_status",
        "user_role",
        "notification_type",
        "visit_type_enum",
    ]

    with get_conn() as conn:
        with conn.cursor() as cursor:
            for e in enums:
                cursor.execute(f'DROP TYPE IF EXISTS "{e}" CASCADE;')
                logger.info(f"Dropped enum: {e}")


def drop_extensions():
    logger.info("Dropping extensions (optional)...")
    with get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute('DROP EXTENSION IF EXISTS "timescaledb" CASCADE;')
            cursor.execute('DROP EXTENSION IF EXISTS "uuid-ossp" CASCADE;')
            cursor.execute('DROP EXTENSION IF EXISTS "pgcrypto" CASCADE;')
    logger.info("Extensions drop done.")


def recreate_schema_from_sql(sql_file: Path) -> bool:
    """Recreate schema using psql -f file."""
    if not sql_file.exists():
        logger.error(f"Schema file not found: {sql_file}")
        return False

    try:
        subprocess.run(["psql", "-f", str(sql_file)], check=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Schema recreate failed: {e}")
        return False


def seed_synthetic_data():
    """Seed DB with synthetic files (your generator + inserter)."""
    gen = SCRIPT_DIR / "05_generate_synthetic_data.py"
    ins = SCRIPT_DIR / "07_insert_data.py"

    if not gen.exists():
        logger.error(f"Missing: {gen}")
        return False
    if not ins.exists():
        logger.error(f"Missing: {ins}")
        return False

    try:
        subprocess.run([sys.executable, str(gen), "--quick", "--export-csv"], check=True)
        subprocess.run([sys.executable, str(ins)], check=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Seeding failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Reset HealthSYNC database (DESTRUCTIVE)")
    parser.add_argument("--confirm", action="store_true", required=True)
    parser.add_argument("--keep-users", action="store_true", help="Preserve auth_users table")
    parser.add_argument("--skip-backup", action="store_true")
    parser.add_argument("--drop-extensions", action="store_true")
    parser.add_argument("--recreate-schema", action="store_true")
    parser.add_argument("--schema-file", type=str, default="01_setup_schema.sql")
    parser.add_argument("--seed-synthetic", action="store_true")

    args = parser.parse_args()

    print("=" * 70)
    print("WARNING: This will DELETE ALL DATA in the database!")
    print("=" * 70)
    confirmation = input("Type 'DELETE ALL DATA' to confirm: ")
    if confirmation != "DELETE ALL DATA":
        print("Cancelled.")
        return

    try:
        if not args.skip_backup:
            create_backup_before_reset()

        drop_timescale_objects()
        drop_all_tables(keep_auth_users=args.keep_users)
        drop_all_enums()

        if args.drop_extensions:
            drop_extensions()

        if args.recreate_schema:
            schema_path = SCRIPT_DIR / args.schema_file
            ok = recreate_schema_from_sql(schema_path)
            if not ok:
                raise SystemExit("Schema recreate failed.")

            if args.seed_synthetic:
                ok = seed_synthetic_data()
                if not ok:
                    raise SystemExit("Seeding failed.")

        logger.info("Reset completed successfully.")

    except Exception as e:
        logger.error(f"Reset failed: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
