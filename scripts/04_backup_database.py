"""Backup HealthSYNC database to ensure data integrity"""

import sys
import logging
import argparse
import subprocess
import os
import traceback
from pathlib import Path
from datetime import datetime
from typing import List
from healthsync.db.connection import get_conn

# Paths
SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent
BACKUP_DIR = BACKEND_DIR / "backups"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BACKUP_DIR.mkdir(exist_ok=True)


def get_db_connection_params() -> dict:
    """Extract connection parameters from environment."""
    return {
        "host": os.getenv("DB_HOST", "db"),  # Default to 'db' for Docker service name
        "port": os.getenv("DB_PORT", "5432"),
        "database": os.getenv("DB_NAME", "healthsync"),
        "user": os.getenv("DB_USER", "health_sync"),  # Match docker-compose.yml
        "password": os.getenv(
            "DB_PASSWORD", "_healthsync_"
        ),  # Match docker-compose.yml
    }


def _run(cmd: List[str], env: dict):
    return subprocess.run(cmd, env=env, capture_output=True, text=True, check=True)


def create_full_backup(compress: bool = True) -> Path:
    """Create a full database backup using pg_dump."""
    logger.info("Starting full database backup...")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    params = get_db_connection_params()

    if compress:
        backup_file = BACKUP_DIR / f"healthsync_full_backup_{timestamp}.dump"
        format_flag = "-Fc"
    else:
        backup_file = BACKUP_DIR / f"healthsync_full_backup_{timestamp}.sql"
        format_flag = "-Fp"

    cmd = [
        "pg_dump",
        "-h",
        params["host"],
        "-p",
        str(params["port"]),
        "-U",
        params["user"],
        "-d",
        params["database"],
        format_flag,
        "-f",
        str(backup_file),
        "--verbose",
        "--clean",
        "--if-exists",
    ]

    env = os.environ.copy()
    env["PGPASSWORD"] = params["password"]

    try:
        logger.info(f"Running: {' '.join(cmd)}")
        _run(cmd, env)
        size_mb = backup_file.stat().st_size / (1024 * 1024)
        logger.info(f"Backup OK: {backup_file} ({size_mb:.2f} MB)")
        return backup_file
    except subprocess.CalledProcessError as e:
        logger.error(f"Backup failed:\nSTDERR:\n{e.stderr}")
        traceback.print_exc()
        raise


def create_schema_backup() -> Path:
    """Create a backup of the database schema only."""
    logger.info("Starting schema-only backup...")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    params = get_db_connection_params()
    backup_file = BACKUP_DIR / f"healthsync_schema_backup_{timestamp}.sql"

    cmd = [
        "pg_dump",
        "-h",
        params["host"],
        "-p",
        str(params["port"]),
        "-U",
        params["user"],
        "-d",
        params["database"],
        "-Fp",
        "--schema-only",
        "-f",
        str(backup_file),
        "--clean",
        "--if-exists",
    ]

    env = os.environ.copy()
    env["PGPASSWORD"] = params["password"]

    try:
        _run(cmd, env)
        size_kb = backup_file.stat().st_size / 1024
        logger.info(f"Schema backup OK: {backup_file} ({size_kb:.2f} KB)")
        return backup_file
    except subprocess.CalledProcessError as e:
        logger.error(f"Schema backup failed:\n{e.stderr}")
        traceback.print_exc()
        raise


def create_data_backup() -> Path:
    """Create data-only backup."""
    logger.info("Creating data-only backup...")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    params = get_db_connection_params()
    backup_file = BACKUP_DIR / f"healthsync_data_{timestamp}.dump"

    cmd = [
        "pg_dump",
        "-h",
        params["host"],
        "-p",
        str(params["port"]),
        "-U",
        params["user"],
        "-d",
        params["database"],
        "-Fc",
        "--data-only",
        "-f",
        str(backup_file),
    ]

    env = os.environ.copy()
    env["PGPASSWORD"] = params["password"]

    try:
        _run(cmd, env)
        size_mb = backup_file.stat().st_size / (1024 * 1024)
        logger.info(f"Data backup OK: {backup_file.name} ({size_mb:.2f} MB)")
        return backup_file
    except subprocess.CalledProcessError as e:
        logger.error(f"Data backup failed:\n{e.stderr}")
        raise


def create_table_backup(tables: List[str]) -> Path:
    """Create backup of specific tables only."""
    logger.info(f"Creating backup of tables: {', '.join(tables)}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    params = get_db_connection_params()
    tables_str = "_".join([t.replace(".", "_") for t in tables[:3]])
    backup_file = BACKUP_DIR / f"healthsync_tables_{tables_str}_{timestamp}.dump"

    cmd = [
        "pg_dump",
        "-h",
        params["host"],
        "-p",
        str(params["port"]),
        "-U",
        params["user"],
        "-d",
        params["database"],
        "-Fc",
        "-f",
        str(backup_file),
    ]
    for t in tables:
        cmd.extend(["-t", t])

    env = os.environ.copy()
    env["PGPASSWORD"] = params["password"]

    try:
        _run(cmd, env)
        size_mb = backup_file.stat().st_size / (1024 * 1024)
        logger.info(f"Table backup OK: {backup_file.name} ({size_mb:.2f} MB)")
        return backup_file
    except subprocess.CalledProcessError as e:
        logger.error(f"Table backup failed:\n{e.stderr}")
        raise


def restore_backup(backup_file: Path, drop_existing: bool = False):
    """Restore database from a backup file."""
    logger.info(f"Restoring from: {backup_file}")

    if not backup_file.is_absolute():
        backup_file = BACKUP_DIR / backup_file

    if not backup_file.exists():
        raise FileNotFoundError(f"Backup not found: {backup_file}")

    params = get_db_connection_params()
    env = os.environ.copy()
    env["PGPASSWORD"] = params["password"]

    is_custom_format = backup_file.suffix == ".dump"

    if drop_existing:
        confirmation = input("This will delete existing data. Type 'yes' to continue: ")
        if confirmation.lower() != "yes":
            logger.info("Restore cancelled.")
            return

    try:
        if is_custom_format:
            cmd = [
                "pg_restore",
                "-h",
                params["host"],
                "-p",
                str(params["port"]),
                "-U",
                params["user"],
                "-d",
                params["database"],
                "--verbose",
                "--clean",
                "--if-exists",
                str(backup_file),
            ]
        else:
            cmd = [
                "psql",
                "-h",
                params["host"],
                "-p",
                str(params["port"]),
                "-U",
                params["user"],
                "-d",
                params["database"],
                "-f",
                str(backup_file),
                "--echo-errors",
            ]

        logger.info(f"Running: {' '.join(cmd)}")
        subprocess.run(cmd, env=env, check=True)
        logger.info("Restore completed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Restore failed:\n{e.stderr}")
        traceback.print_exc()
        raise


def list_backups():
    """List available backups."""
    logger.info("Available backups:")
    backups = sorted(BACKUP_DIR.glob("healthsync_*.*"), reverse=True)

    if not backups:
        logger.info("No backup files found.")
        return

    for b in backups:
        size_mb = b.stat().st_size / (1024 * 1024)
        modified = datetime.fromtimestamp(b.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        logger.info(f"- {b.name} | {size_mb:.2f} MB | {modified}")


def cleanup_old_backups(keep_count: int = 10):
    """Keep only most recent backups."""
    backups = sorted(BACKUP_DIR.glob("healthsync_*.*"), reverse=True)
    if len(backups) <= keep_count:
        logger.info("No cleanup needed.")
        return

    for b in backups[keep_count:]:
        b.unlink()
        logger.info(f"Deleted: {b.name}")


def export_csv_backup():
    """Export key tables to CSV using COPY."""
    logger.info("Exporting tables to CSV...")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_dir = BACKUP_DIR / f"csv_backup_{timestamp}"
    csv_dir.mkdir(exist_ok=True)

    tables = [
        "patients",
        "clinicians",
        "clinics",
        "devices",
        "glucose_readings",
        "activity_data",
        "visits",
        "visit_summaries",
        "after_visit_summaries",
    ]

    with get_conn() as conn:
        with conn.cursor() as cur:
            for t in tables:
                out = csv_dir / f"{t}.csv"
                with open(out, "w", newline="") as f:
                    cur.copy_expert(f"COPY {t} TO STDOUT WITH CSV HEADER", f)
                size_mb = out.stat().st_size / (1024 * 1024)
                logger.info(f"Exported {t} -> {out.name} ({size_mb:.2f} MB)")

    logger.info(f"CSV export done: {csv_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Backup and restore HealthSYNC database"
    )

    parser.add_argument(
        "--type", choices=["full", "schema", "data", "tables", "csv"], default="full"
    )
    parser.add_argument(
        "--compress",
        action="store_true",
        help="Use compressed custom format for full backup",
    )
    parser.add_argument(
        "--tables", nargs="+", help="Tables to backup (only for --type tables)"
    )
    parser.add_argument(
        "--restore", type=Path, help="Restore from a backup file (name or path)"
    )
    parser.add_argument(
        "--drop-existing",
        action="store_true",
        help="Drop objects before restore (destructive)",
    )
    parser.add_argument("--list", action="store_true", help="List available backups")
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete old backups (keep 10 most recent)",
    )

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("HealthSYNC Database Backup Tool")
    logger.info("=" * 70)

    try:
        if args.list:
            list_backups()
            return

        if args.cleanup:
            cleanup_old_backups()
            return

        if args.restore:
            restore_backup(args.restore, args.drop_existing)
            return

        if args.type == "full":
            backup_file = create_full_backup(args.compress)
        elif args.type == "schema":
            backup_file = create_schema_backup()
        elif args.type == "data":
            backup_file = create_data_backup()
        elif args.type == "tables":
            if not args.tables:
                raise SystemExit("You must provide --tables for --type tables")
            backup_file = create_table_backup(args.tables)
        elif args.type == "csv":
            export_csv_backup()
            return
        else:
            raise SystemExit("Unknown backup type")

        logger.info(f"\nBackup created: {backup_file.name}")
        logger.info(f"Location: {BACKUP_DIR}")
        logger.info(
            f"Restore example:\n  python {Path(__file__).name} --restore {backup_file.name} --drop-existing"
        )

    except Exception as e:
        logger.error(f"Error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
