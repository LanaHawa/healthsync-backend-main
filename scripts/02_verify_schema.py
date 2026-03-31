"""Verify PostgreSQL + TimescaleDB schema for HealthSYNC."""

import sys
import logging
import argparse
import traceback
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Tuple, Dict, Any

# Add src to path
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR / "src"))

env_file = (
    BACKEND_DIR / ".env.local"
    if (BACKEND_DIR / ".env.local").exists()
    else BACKEND_DIR / ".env"
)
load_dotenv(env_file)

from healthsync.db.connection import get_conn

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def check_timescaledb_enabled() -> bool:
    """Check if TimescaleDB extension is enables in the database."""
    logger.info("Checking if TimescaleDB extension is enabled...")

    try:
        with get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                SELECT extname, extversion
                FROM pg_extension
                WHERE extname = 'timescaledb';
                """)
                result = cursor.fetchone()
                if result:
                    ext_name, ext_version = result
                    logger.info(
                        f"TimescaleDB extension is enabled: {ext_name} version {ext_version}"
                    )
                    return True
                else:
                    logger.error(
                        "TimescaleDB extension is not enabled in the database."
                    )
                    return False
    except Exception as e:
        logger.error(f"Error checking TimescaleDB extension: {e}")
        return False


def verify_tables() -> Tuple[bool, List[str]]:
    """Verify that all required tables exist in the database."""
    logger.info("Verifying required tables in the database...")

    required_tables = [
        # Auth & Users
        "auth_users",
        "user_preferences",
        "system_configs",
        # Clinical Entities
        "clinics",
        "clinicians",
        "patients",
        "clinician_clinic",
        # Medications
        "medications",
        "patient_medications",
        "allergies",
        "prescriptions",
        "prescription_items",
        # Devices & Health Apps
        "health_apps",
        "devices",
        # Time-Series Data
        "glucose_readings",
        "activity_data",
        # Visits & Summaries
        "visits",
        "visit_summaries",
        "after_visit_summaries",
        "action_items",
        "agenda_items",
        # Visualizations & Reports
        "visualizations",
        "annotations",
        "bookmarks",
        "reports",
        "report_visualizations",
        # Events & Audit
        "abnormal_events",
        "abnormal_event_readings",
        "audit_log_entries",
        "access_permissions",
        "patient_records",
    ]

    missing_tables = []

    with get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name;
            """)
            existing_tables = {row[0] for row in cursor.fetchall()}

    missing_tables = [
        table for table in required_tables if table not in existing_tables
    ]
    if missing_tables:
        logger.error(f"Missing {len(missing_tables)} required tables:")
        for table in missing_tables:
            logger.error(f" - {table}")
        return False, missing_tables

    logger.info("All required tables are present in the database.")
    logger.info(f"Total tables verified: {len(required_tables)}")

    return True, []


def verify_enums() -> Tuple[bool, List[str]]:
    """Verify that all required enums exist in the database."""
    logger.info("Verifying required enums in the database...")

    required_enums = [
        "user_role",
        "permission_status",
        "stakeholder_type",
        "action_status",
        "device_type",
        "device_status",
        "avs_channel",
        "annotation_type",
        "visualization_type",
        "abnormal_event_type",
        "report_type",
        "agenda_status",
        "glucose_unit",
    ]

    with get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT t.typname, string_agg(e.enumlabel, ', ' ORDER BY e.enumsortorder) as values
                FROM pg_type t
                JOIN pg_enum e ON t.oid = e.enumtypid
                WHERE t.typtype = 'e'
                GROUP BY t.typname
                ORDER BY t.typname;
            """)

            existing_enums = {row[0]: row[1] for row in cursor.fetchall()}

    missing_enums = [e for e in required_enums if e not in existing_enums]

    if missing_enums:
        logger.error(f"Missing {len(missing_enums)} required ENUM types:")
        for enum in missing_enums:
            logger.error(f" - {enum}")
        return False, missing_enums

    logger.info("All required ENUM types are present in the database.")

    if logger.level == logging.DEBUG:
        logger.debug("Existing ENUM types and their values:")
        for enum, values in existing_enums.items():
            logger.debug(f" - {enum}: {values}")

    return True, []


def verify_hypertables() -> Tuple[bool, List[Dict[str, Any]]]:
    """Verify that all required hypertables exist in the database."""
    logger.info("Verifying required hypertables in the database...")

    expected_hypertables = [
        "glucose_readings",
        "activity_data",
        "audit_log_entries",
    ]

    try:
        with get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        hypertable_name,
                        num_chunks,
                        num_dimensions,
                        compression_enabled
                    FROM timescaledb_information.hypertables
                    WHERE hypertable_schema = 'public'
                    ORDER BY hypertable_name;
                """)

                hypertables = cursor.fetchall()

        if not hypertables:
            logger.warning("No hypertables found in the database.")
            return False, []

        hypertables_info = []
        for name, chunks, dims, compressed in hypertables:
            hypertables_info.append(
                {
                    "name": name,
                    "num_chunks": chunks,
                    "num_dimensions": dims,
                    "compression_enabled": compressed,
                }
            )

        logger.info(f"Found {len(hypertables_info)} hypertables:")
        for info in hypertables_info:
            compress_status = (
                "Compressed" if info["compression_enabled"] else "○ Not Compressed"
            )
            logger.info(
                f"   - {info['name']}: {info['num_chunks']} chunks, {compress_status}"
            )

        # Check for missing hypertables
        existing_names = {info["name"] for info in hypertables_info}
        missing = [t for t in expected_hypertables if t not in existing_names]

        if missing:
            logger.warning(f"Missing {len(missing)} expected hypertables:")
            for t in missing:
                logger.warning(f"   - {t}")
            return False, hypertables_info

        return True, hypertables_info

    except Exception as e:
        logger.warning(f"Error verifying hypertables: {e}")
        return False, []


def verify_continuous_aggregates() -> Tuple[bool, List[str]]:
    """Verify all the continuous aggregates (materialized views) exist in the database."""
    logger.info("Verifying required continuous aggregates in the database...")

    expected_caggs = [
        "glucose_hourly",
        "glucose_daily",
        "glucose_weekly",
    ]

    try:
        with get_conn() as conn:
            with conn.cursor() as cursor:
                # Fix: Correct column names for TimescaleDB continuous aggregates
                cursor.execute("""
                    SELECT
                        view_name,
                        materialization_hypertable_name
                    FROM timescaledb_information.continuous_aggregates
                    WHERE view_schema = 'public'
                    ORDER BY view_name;
                """)

                caggs = cursor.fetchall()

        if not caggs:
            logger.warning("No continuous aggregates found in the database.")
            return False, []

        logger.info(f"✓ Found {len(caggs)} continuous aggregates:")
        existing_names = []
        for view_name, hypertable_name in caggs:
            existing_names.append(view_name)
            logger.info(f"   - {view_name}: materializes {hypertable_name}")

        missing_cas = [cagg for cagg in expected_caggs if cagg not in existing_names]

        if missing_cas:
            logger.error(f"Missing {len(missing_cas)} required continuous aggregates:")
            for cagg in missing_cas:
                logger.error(f"   - {cagg}")
            return False, missing_cas

        return True, existing_names

    except Exception as e:
        logger.warning(f"Error verifying continuous aggregates: {e}")
        return False, []


def verify_compression_policies() -> Tuple[bool, List[Dict[str, Any]]]:
    """Verify that compression policies are set up for hypertables."""
    logger.info("Verifying compression policies for hypertables...")

    try:
        with get_conn() as conn:
            with conn.cursor() as cursor:
                # Query compression policies from TimescaleDB
                cursor.execute("""
                    SELECT
                        format('%I.%I', ht.schema_name, ht.table_name)::regclass::text AS hypertable,
                        (config::jsonb->>'compress_after')::text AS compress_after,
                        schedule_interval
                    FROM timescaledb_information.jobs j
                    CROSS JOIN LATERAL (
                        SELECT schema_name, table_name
                        FROM _timescaledb_catalog.hypertable
                        WHERE id = (config::jsonb->>'hypertable_id')::integer
                    ) ht
                    WHERE proc_schema = '_timescaledb_functions'
                      AND proc_name = 'policy_compression'
                      AND ht.schema_name = 'public'
                    ORDER BY hypertable;
                """)

                policies = cursor.fetchall()

        if not policies:
            logger.warning("No compression policies found for hypertables.")
            return False, []

        logger.info(f"Found {len(policies)} compression policies:")
        policies_info = []
        for table, compress_after, interval in policies:
            policies_info.append(
                {
                    "table": table,
                    "compress_after": compress_after or "N/A",
                    "schedule": str(interval) if interval else "N/A",
                }
            )
            logger.info(
                f"   - {table}: compress after {compress_after}, runs every {interval}"
            )

        return True, policies_info

    except Exception as e:
        logger.warning(f"Error verifying compression policies: {e}")
        return False, []


def verify_indexes() -> Tuple[bool, int]:
    """Vetify critical indexes exist in the database."""
    logger.info("Verifying critical indexes in the database...")
    critical_indexes = [
        ("patients", "idx_patients_auth_user"),
        ("glucose_readings", "idx_glucose_patient_ts"),
        ("glucose_readings", "idx_glucose_device_ts"),
        ("activity_data", "idx_activity_patient_time"),
        ("devices", "idx_devices_patient"),
        ("visits", "idx_visits_patient"),
    ]

    try:
        with get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        schemaname,
                        tablename,
                        indexname,
                        indexdef
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                    ORDER BY tablename, indexname;
                """)

                all_indexes = cursor.fetchall()
                existing_index_names = {row[2] for row in all_indexes}

                missing_indexes = []
                for table, idx_name in critical_indexes:
                    if idx_name not in existing_index_names:
                        missing_indexes.append(f"{idx_name} on {table}")

                if missing_indexes:
                    logger.error(f"Missing {len(missing_indexes)} critical indexes:")
                    for idx in missing_indexes:
                        logger.error(f" - {idx}")
                    return False, len(missing_indexes)

                logger.info("All critical indexes are present in the database.")
                logger.info(f"Total indexes verified: {len(critical_indexes)}")
                return True, len(critical_indexes)
    except Exception as e:
        logger.warning(f"Error verifying indexes: {e}")
        return False, len(critical_indexes)


def verify_foreign_keys() -> Tuple[bool, int]:
    """Verify foreign key constraints exist in the database."""
    logger.info("Verifying foreign key constraints in the database...")

    with get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT
                    tc.table_name,
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                    AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_schema = 'public'
                ORDER BY tc.table_name, kcu.column_name;
            """)

            foreign_keys = cursor.fetchall()
            if not foreign_keys:
                logger.error("No foreign key constraints found in the database.")
                return False, 0

            logger.info(
                f"Found {len(foreign_keys)} foreign key constraints in the database."
            )

            if logger.level == logging.DEBUG:
                logger.debug("Foreign key constraints:")
                for table, column, foreign_table, foreign_column in foreign_keys[:10]:
                    logger.debug(
                        f" - {table}({column}) -> {foreign_table}({foreign_column})"
                    )
                if len(foreign_keys) > 10:
                    logger.debug(f"   ... and {len(foreign_keys) - 10} more")

            return True, len(foreign_keys)


def get_table_row_counts() -> Dict[str, int]:
    """Get row counts for all tables in the database."""
    logger.info("Checking row counts for all tables in the database...")

    with get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT schemaname, relname, n_live_tup AS row_count
                FROM pg_stat_user_tables
                WHERE schemaname = 'public'
                ORDER BY n_live_tup DESC;
            """)

            table_counts = cursor.fetchall()

    row_counts = {}
    total_rows = 0

    logger.info("Table row counts:")
    for schema, table, count in table_counts:
        row_counts[table] = count
        total_rows += count
        if count > 0:
            logger.info(f" - {table}: {count} rows")

    logger.info(f"Total rows across all tables: {total_rows}")
    return row_counts


def main():
    """Main function to run schema verification checks."""
    parser = argparse.ArgumentParser(description="Verify HealthSYNC database schema.")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output (show enum values, FK details)",
    )
    parser.add_argument(
        "--check-data",
        action="store_true",
        help="Check and report row counts for all tables",
    )

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    logger.info("=" * 70)
    logger.info("Starting HealthSYNC database schema verification...")
    logger.info("=" * 70)

    results = {}

    try:
        # 1. Check TimescaleDB
        results["timescaledb"] = check_timescaledb_enabled()

        # 2. Verify core schema
        results["tables"], missing_tables = verify_tables()
        results["enums"], missing_enums = verify_enums()
        results["indexes"], index_count = verify_indexes()
        results["foreign_keys"], fk_count = verify_foreign_keys()

        # 3. Verify TimescaleDB features (if enabled)
        if results["timescaledb"]:
            results["hypertables"], hypertable_info = verify_hypertables()
            results["continuous_aggregates"], cagg_names = (
                verify_continuous_aggregates()
            )
            results["compression"], compression_info = verify_compression_policies()
        else:
            logger.warning(
                "Skipping TimescaleDB-specific checks as the extension is not enabled."
            )
            results["hypertables"] = None
            results["continuous_aggregates"] = None
            results["compression"] = None

        # 4. Check the data
        if args.check_data:
            row_counts = get_table_row_counts()
            results["row_counts"] = row_counts

        logger.info("\n" + "=" * 70)
        logger.info("Schema Verification Summary:")
        logger.info("=" * 70)

        passed = 0
        failed = 0
        skipped = 0

        for check, result in results.items():
            if result is True:
                logger.info(f" - {check}: PASS")
                passed += 1
            elif result is False:
                logger.info(f" - {check}: FAIL")
                failed += 1
            elif result is None:
                logger.info(f" - {check}: SKIPPED")
                skipped += 1

        logger.info("=" * 70)
        logger.info(
            f"Total Checks: {passed + failed + skipped} | Passed: {passed} | Failed: {failed} | Skipped: {skipped}"
        )

        if failed > 0:
            logger.error("Schema verification completed with failures.")
            logger.info(
                "\n Note: Please refer to the detailed logs above for information on the failed checks."
            )
            logger.info("  2. Run: python scripts/01_setup_schema.py --drop-existing")
            logger.info("  3. Re-run: python scripts/02_verify_schema.py")
            sys.exit(1)

        else:
            logger.info(
                "Schema verification completed successfully. All checks passed."
            )
            logger.info("\nNext steps:")
            logger.info("  1. Run: python scripts/07_insert_data.py --dry-run")
            logger.info("  2. Run: python scripts/07_insert_data.py --bio-file bio.csv")
            sys.exit(0)

    except Exception as e:
        logger.error(f"An unexpected error occurred during schema verification: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
