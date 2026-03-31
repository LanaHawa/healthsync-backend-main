"""Create PostgreSQL + TimescaleDB schema for HealthSYNC application."""
import sys
import logging
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Add src to path
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

env_file = BACKEND_DIR / ".env.local" if (BACKEND_DIR / ".env.local").exists() else BACKEND_DIR / ".env"
load_dotenv(env_file)

from src.healthsync.db.connection import get_conn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

SQL_FILE = SCRIPT_DIR / "01_setup_schema.sql"


def enable_timescaledb():
    """Enable TimescaleDB extension in the database."""
    logger.info("Enabling TimescaleDB extension...")
    try:
        with get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
        logger.info("TimescaleDB extension enabled successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to enable TimescaleDB extension: {e}")
        logger.warning("Continuing without TimescaleDB extension.")
        return False


def drop_all_objects():
    """Drop all existing tables, types, and TimescaleDB hypertables."""
    logger.warning("Dropping all existing database objects...")

    with get_conn() as conn:
        with conn.cursor() as cursor:
            # Drop materialized views first
            cursor.execute("""
                DROP MATERIALIZED VIEW IF EXISTS glucose_hourly CASCADE;
                DROP MATERIALIZED VIEW IF EXISTS glucose_daily CASCADE;
                DROP MATERIALIZED VIEW IF EXISTS glucose_weekly CASCADE;
            """)

            # Drop tables
            cursor.execute("""
                DROP TABLE IF EXISTS activity_data CASCADE;
                DROP TABLE IF EXISTS abnormal_event_readings CASCADE;
                DROP TABLE IF EXISTS abnormal_events CASCADE;
                DROP TABLE IF EXISTS report_visualizations CASCADE;
                DROP TABLE IF EXISTS reports CASCADE;
                DROP TABLE IF EXISTS action_items CASCADE;
                DROP TABLE IF EXISTS agenda_items CASCADE;
                DROP TABLE IF EXISTS bookmarks CASCADE;
                DROP TABLE IF EXISTS annotations CASCADE;
                DROP TABLE IF EXISTS visualizations CASCADE;
                DROP TABLE IF EXISTS after_visit_summaries CASCADE;
                DROP TABLE IF EXISTS visit_summaries CASCADE;
                DROP TABLE IF EXISTS visits CASCADE;
                DROP TABLE IF EXISTS patient_records CASCADE;
                DROP TABLE IF EXISTS glucose_readings CASCADE;
                DROP TABLE IF EXISTS meal_data CASCADE;
                DROP TABLE IF EXISTS devices CASCADE;
                DROP TABLE IF EXISTS health_apps CASCADE;
                DROP TABLE IF EXISTS audit_log_entries CASCADE;
                DROP TABLE IF EXISTS access_permissions CASCADE;
                DROP TABLE IF EXISTS clinician_clinic CASCADE;
                DROP TABLE IF EXISTS prescription_items CASCADE;
                DROP TABLE IF EXISTS prescriptions CASCADE;
                DROP TABLE IF EXISTS allergies CASCADE;
                DROP TABLE IF EXISTS patient_medications CASCADE;
                DROP TABLE IF EXISTS medications CASCADE;
                DROP TABLE IF EXISTS patients CASCADE;
                DROP TABLE IF EXISTS clinicians CASCADE;
                DROP TABLE IF EXISTS clinics CASCADE;
                DROP TABLE IF EXISTS system_configs CASCADE;
                DROP TABLE IF EXISTS user_preferences CASCADE;
                DROP TABLE IF EXISTS auth_users CASCADE;
            """)

            # Drop types
            cursor.execute("""
                DROP TYPE IF EXISTS glucose_unit CASCADE;
                DROP TYPE IF EXISTS agenda_status CASCADE;
                DROP TYPE IF EXISTS report_type CASCADE;
                DROP TYPE IF EXISTS abnormal_event_type CASCADE;
                DROP TYPE IF EXISTS visualization_type CASCADE;
                DROP TYPE IF EXISTS annotation_type CASCADE;
                DROP TYPE IF EXISTS avs_channel CASCADE;
                DROP TYPE IF EXISTS device_status CASCADE;
                DROP TYPE IF EXISTS device_type CASCADE;
                DROP TYPE IF EXISTS action_status CASCADE;
                DROP TYPE IF EXISTS stakeholder_type CASCADE;
                DROP TYPE IF EXISTS permission_status CASCADE;
                DROP TYPE IF EXISTS user_role CASCADE;
            """)

    logger.info("All existing database objects dropped.")


def execute_sql_file():
    """Execute SQL commands from a file."""
    logger.info(f"Executing SQL file: {SQL_FILE.name}")

    if not SQL_FILE.exists():
        logger.error(f"SQL file was not found: {SQL_FILE}")
        sys.exit(1)

    # Read the SQL file
    with open(SQL_FILE, 'r', encoding='utf-8') as file:
        sql_commands = file.read()

    # Execute the SQL commands
    with get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql_commands)

    logger.info("SQL file executed successfully.")


def create_hypertables():
    """Convert time-series data tables into TimescaleDB hypertables."""
    logger.info("Converting to TimescaleDB hypertables...")

    hypertable_configs = [
        {
            "table": "glucose_readings",
            "time_column": "timestamp",
            "chunk_interval": "1 day",
        },
        {
            "table": "activity_data",
            "time_column": "timestamp",
            "chunk_interval": "1 day",
        },
        {
            "table": "audit_log_entries",
            "time_column": "timestamp",
            "chunk_interval": "30 days",
        }
    ]

    for config in hypertable_configs:
            table = config["table"]
            time_col = config["time_column"]
            chunk_interval = config["chunk_interval"]

            try:
                with get_conn() as conn:
                    with conn.cursor() as cursor:
                        # Check if already a hypertable
                        cursor.execute("""
                            SELECT 1 FROM timescaledb_information.hypertables
                            WHERE hypertable_name = %s AND hypertable_schema = 'public'
                        """, (table,))

                        if cursor.fetchone():
                            logger.info(f"✓ Hypertable '{table}' already exists, skipping...")
                            continue

                        # Create hypertable with explicit partitioning column
                        cursor.execute(f"""
                            SELECT create_hypertable(
                                '{table}',
                                '{time_col}',
                                chunk_time_interval => INTERVAL '{chunk_interval}',
                                if_not_exists => TRUE,
                                migrate_data => TRUE
                            );
                        """)

                        logger.info(f"✓ Hypertable created for '{table}' on '{time_col}' (chunk: {chunk_interval})")

            except Exception as e:
                logger.warning(f"Failed to create hypertable for '{table}': {e}")
                # Continue to next table
                continue

    logger.info("Hypertable creation completed.")


def create_continuous_aggregates():
    """Create continuous aggregate views for glucose readings."""
    logger.info("Creating continuous aggregate views...")

    # Hourly Statistics
    try:
        with get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE MATERIALIZED VIEW IF NOT EXISTS glucose_hourly
                    WITH (timescaledb.continuous) AS
                    SELECT
                        patient_id,
                        time_bucket('1 hour', timestamp) AS bucket,
                        AVG(value) AS avg_glucose,
                        MIN(value) AS min_glucose,
                        MAX(value) AS max_glucose,
                        STDDEV(value) AS stddev_glucose,
                        COUNT(*) AS reading_count
                    FROM glucose_readings
                    GROUP BY bucket, patient_id
                    WITH NO DATA;
                """)

                cursor.execute("""
                    SELECT add_continuous_aggregate_policy('glucose_hourly',
                        start_offset => INTERVAL '2 days',
                        end_offset => INTERVAL '1 hour',
                        schedule_interval => INTERVAL '30 minutes',
                        if_not_exists => TRUE
                    );
                """)
                logger.info("✓ Glucose hourly view created (refreshes every 30 mins)")
    except Exception as e:
        logger.warning(f"Glucose hourly view creation failed: {e}")

    # Daily Statistics
    try:
        with get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE MATERIALIZED VIEW IF NOT EXISTS glucose_daily
                    WITH (timescaledb.continuous) AS
                    SELECT
                        patient_id,
                        time_bucket('1 day', timestamp) AS bucket,
                        AVG(value) AS avg_glucose,
                        MIN(value) AS min_glucose,
                        MAX(value) AS max_glucose,
                        STDDEV(value) AS stddev_glucose,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY value) AS median_glucose,
                        COUNT(*) AS reading_count
                    FROM glucose_readings
                    GROUP BY bucket, patient_id
                    WITH NO DATA;
                """)

                cursor.execute("""
                    SELECT add_continuous_aggregate_policy('glucose_daily',
                        start_offset => INTERVAL '7 days',
                        end_offset => INTERVAL '1 day',
                        schedule_interval => INTERVAL '2 hours',
                        if_not_exists => TRUE
                    );
                """)
                logger.info("✓ Glucose daily view created (refreshes every 2 hours)")
    except Exception as e:
        logger.warning(f"Glucose daily view creation failed: {e}")

    # Weekly Statistics
    try:
        with get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE MATERIALIZED VIEW IF NOT EXISTS glucose_weekly
                    WITH (timescaledb.continuous) AS
                    SELECT
                        patient_id,
                        time_bucket('7 days', timestamp) AS bucket,
                        AVG(value) AS avg_glucose,
                        MIN(value) AS min_glucose,
                        MAX(value) AS max_glucose,
                        STDDEV(value) AS stddev_glucose,
                        COUNT(*) AS reading_count
                    FROM glucose_readings
                    GROUP BY patient_id, bucket
                    WITH NO DATA;
                """)

                cursor.execute("""
                    SELECT add_continuous_aggregate_policy('glucose_weekly',
                        start_offset => INTERVAL '30 days',
                        end_offset => INTERVAL '7 days',
                        schedule_interval => INTERVAL '6 hours',
                        if_not_exists => TRUE
                    );
                """)
                logger.info("✓ Glucose weekly view created (refreshes every 6 hours)")
    except Exception as e:
        logger.warning(f"Glucose weekly view creation failed: {e}")

    logger.info("All continuous aggregate views created.")


def setup_compression():
    """Enable compression on older time-series data."""
    logger.info("Setting up compression policies...")

    compression_configs = [
        {
            "table": "glucose_readings",
            "time_column": "timestamp",
            "compress_after": "30 days"
        },
        {
            "table": "activity_data",
            "time_column": "timestamp",
            "compress_after": "30 days"
        },
        {
            "table": "audit_log_entries",
            "time_column": "timestamp",
            "compress_after": "90 days"
        },
    ]

    with get_conn() as conn:
        with conn.cursor() as cursor:
            for config in compression_configs:
                table = config["table"]
                time_column = config["time_column"]
                compress_after = config["compress_after"]

                try:
                    # Enable compression
                    cursor.execute(f"""
                        ALTER TABLE {table} SET (
                            timescaledb.compress,
                            timescaledb.compress_orderby = '{time_column}',
                            timescaledb.compress_segmentby = 'patient_id'
                        );
                    """)

                    # Add compression policy
                    cursor.execute(f"""
                        SELECT add_compression_policy('{table}',
                            INTERVAL '{compress_after}',
                            if_not_exists => TRUE
                        );
                    """)
                    logger.info(f"✓ Compression enabled for '{table}' (compress after {compress_after})")
                except Exception as e:
                    logger.warning(f"Failed to set up compression for '{table}': {e}")

    logger.info("Compression policies set up successfully.")


def create_timescale_indexes():
    """Create indexes optimized for TimescaleDB hypertables."""
    logger.info("Creating TimescaleDB-optimized indexes...")

    with get_conn() as conn:
        with conn.cursor() as cursor:
            additional_indexes = [
                # Composite index for common dashboard queries
                """CREATE INDEX IF NOT EXISTS idx_glucose_patient_device_value_time
                ON glucose_readings(patient_id, device_id, value, "timestamp" DESC)""",

                # Partial index for abnormal glucose events
                """CREATE INDEX IF NOT EXISTS idx_glucose_abnormal_events
                ON glucose_readings("timestamp" DESC, patient_id, value)
                WHERE value < 70 OR value > 180""",

                # Composite index for activity correlation queries
                """CREATE INDEX IF NOT EXISTS idx_activity_patient_hr_calories
                ON activity_data(patient_id, "timestamp" DESC, heart_rate, calories_burned)
                WHERE heart_rate IS NOT NULL""",


                # Index for device-specific queries
                """CREATE INDEX IF NOT EXISTS idx_glucose_device_type_time
                ON glucose_readings(device_type, "timestamp" DESC, patient_id)""",
            ]

            for index_sql in additional_indexes:
                try:
                    cursor.execute(index_sql)
                    index_name = index_sql.split('IF NOT EXISTS')[1].split('\n')[0].strip()
                    logger.info(f"✓ Index created: {index_name}")
                except Exception as e:
                    logger.warning(f"Failed to create index: {e}")

    logger.info("All TimescaleDB-optimized indexes created.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Setup HealthSYNC database schema")
    parser.add_argument(
        "--drop-existing",
        action="store_true",
        help="Drop existing tables and types (DESTRUCTIVE)"
    )
    parser.add_argument(
        "--skip-timescale",
        action="store_true",
        help="Skip TimescaleDB setup (PostgreSQL mode only)"
    )

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("HealthSYNC Schema Setup (PostgreSQL + TimescaleDB)")
    logger.info("=" * 70)

    try:
        # 1. Drop existing objects if requested
        if args.drop_existing:
            confirmation = input("Drop all database objects? This is DESTRUCTIVE. (yes/no): ")
            if confirmation.lower() == "yes":
                drop_all_objects()
            else:
                logger.info("Operation cancelled by user.")
                sys.exit(0)

        # 2. Enable TimescaleDB extension
        timescale_enabled = False
        if not args.skip_timescale:
            timescale_enabled = enable_timescaledb()

        # 3. Execute schema SQL file
        execute_sql_file()

        # 4. Setup TimescaleDB features if enabled
        if timescale_enabled:
            create_hypertables()
            create_continuous_aggregates()
            setup_compression()
            create_timescale_indexes()

        logger.info("=" * 70)
        logger.info("HealthSYNC database schema setup completed successfully.")
        logger.info("=" * 70)
        logger.info("\nNext steps:")
        logger.info("  1. Run: python scripts/02_verify_schema.py")
        logger.info("  2. Run: python scripts/05_generate_synthetic_data.py --export-csv")
        logger.info("  3. Run: python scripts/07_insert_data.py --bio-file bio.csv --dry-run")
        logger.info("  4. Run: python scripts/07_insert_data.py --bio-file bio.csv")

        if timescale_enabled:
            logger.info("\nTimescaleDB Features Enabled:")
            logger.info("  • Hypertables (automatic time-based partitioning)")
            logger.info("  • Continuous aggregates (hourly/daily/weekly glucose stats)")
            logger.info("  • Compression (30-180 days retention)")
            logger.info("  • Optimized indexes for time-series queries")

    except Exception as e:
        logger.error(f"Schema setup failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()