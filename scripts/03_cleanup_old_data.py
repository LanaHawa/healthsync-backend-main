"""Clean up old data from HealthSYNC database based on Canadian healthcare retention policies."""

import sys
import logging
import argparse
import json
import traceback
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional


#Add src to path
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
ARCHIVE_DIR = BACKEND_DIR/ "archives"
sys.path.insert(0, str(BACKEND_DIR / "src"))

from healthsync.db.connection import get_conn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

# Ensure archive directory exists
# if it doesn't exist, create it
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

RETENTION_POLICIES_CANADA = {
    "patient_health_records": timedelta(days=365 * 10),  # 10 years FROM last entry
    "glucose_readings": timedelta(days=365 * 10),        # 10 years FROM last entry
    "activity_data": timedelta(days=365 * 10),           # 10 years FROM last entry
    "audit_logs_entries": timedelta(days=365 * 10),      # 10 years (compliance/legal requirement)
    "prescriptions": timedelta(days=365 * 10),           # 10 years FROM last entry
    "clinical_visits": timedelta(days=365 * 10),         # 10 years
    "soft_deleted_patients": timedelta(days=365 * 2),    # 2 years
    "temporary_session_data": timedelta(days=90),        # 90 days
    "annonymized_data": timedelta(days=365 * 20),        # 20 years
}


PROVINCIAL_POLICIES = {
    "ONTARIO":{
        "patient_health_records": timedelta(days=365 * 10),  # 10 years minimum
        "minor_patient_records": timedelta(days=365 * 20),         # 20 years minimum
    }

    ,"ALBERTA":{
        "patient_health_records": timedelta(days=365 * 10),  # 10 years from last service
        "diagnostic_imaging": timedelta(days=365 * 10),         # 10 years from last service
    }

    ,"BRITISH_COLUMBIA":{
        "patient_health_records": -1,  # Permanent archival
        "requires_archival": True,         # Permanent archival
    }

    ,"QUEBEC":{
        "patient_health_records": timedelta(days=365 * 10),  # 10 years minimum
        "professional_records": timedelta(days=365 * 15),         # 15 years minimum
    }

    ,"SASKATCHEWAN":{
        "patient_health_records": timedelta(days=365 * 10),  # 10 years standard
    }

    ,"MANITOBA":{
        "patient_health_records": timedelta(days=365 * 10),  # 10 years standard
    },

    "NOVA_SCOTIA":{
        "patient_health_records": timedelta(days=365 * 10),  # 10 years standard
    },
}

def get_retention_policy(data_type: str, province: Optional[str] = None) -> int:
    """Get retention policy in days for a data type, considering provincial rules."""
    if province and province.lower() in PROVINCIAL_POLICIES:
        provincial_policy = PROVINCIAL_POLICIES[province.lower()]

        # Check for provincial override
        if data_type in provincial_policy:
            policy_days = provincial_policy[data_type]

            # -1 means permanent retention (BC)
            if policy_days == -1:
                logger.warning(f"Data type '{data_type}' in province '{province}' requires permanent archival.")
                logger.warning("   Data must be archived, not deleted. Use --export-archive first.")
                return -1

            return policy_days

    # Fall back to federal/standard policy
    return RETENTION_POLICIES_CANADA.get(data_type, 3650)


def check_minor_patient_special_rules(patient_id: str, province: str) -> int:
    """
    Check if patient was a minor and apply extended retention rules.
    Ontario: Records for minors must be kept for 10 years OR until age 25 (whichever is longer).
    """
    if province.lower() != 'ontario':
        return RETENTION_POLICIES_CANADA['patient_health_records']

    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date_of_birth, deleted_at
            FROM patients
            WHERE patient_id = %s;
        """, (patient_id,))

        result = cursor.fetchone()
        if not result:
            return 3650  # Default 10 years

        dob, deleted_at = result

        # Calculate age at last service (or deletion)
        last_service_date = deleted_at if deleted_at else datetime.now()
        age_at_last_service = (last_service_date.date() - dob).days / 365.25

        if age_at_last_service < 18:
            # Minor: keep until age 25 or 10 years, whichever is longer
            days_until_age_25 = int((25 - age_at_last_service) * 365.25)
            retention_days = max(days_until_age_25, 3650)

            logger.info(f"Patient was minor (age {age_at_last_service:.1f}). "
                       f"Extended retention: {retention_days} days")
            return retention_days

    return 3650  # Standard 10 years

def get_retention_stats(province: Optional[str] = None) -> Dict[str, Any]:
    """Get statistics about data age and retention status (Canadian context)."""
    logger.info("Analyzing data retention status (Canadian healthcare standards)...")

    if province:
        logger.info(f"Using retention policies for: {province.upper()}")

    with get_conn() as conn:
        cursor = conn.cursor()

        stats = {}

        # 1. Glucose readings age distribution (10 years)
        retention_days = get_retention_policy('glucose_readings', province)
        cursor.execute(f"""
            SELECT
                COUNT(*) as total_records,
                MIN("timestamp") as oldest_record,
                MAX("timestamp") as newest_record,
                COUNT(*) FILTER (WHERE "timestamp" < NOW() - INTERVAL '{retention_days} days') as beyond_retention,
                COUNT(*) FILTER (WHERE "timestamp" < NOW() - INTERVAL '30 days') as compressed_eligible,
                pg_size_pretty(pg_total_relation_size('glucose_readings')) as table_size
            FROM glucose_readings;
        """
        )
        result = cursor.fetchone()
        stats['glucose_readings'] = {
            'total': result[0],
            'oldest': result[1],
            'newest': result[2],
            'beyond_retention': result[3],
            'compressed_eligible': result[4],
            'size': result[5],
            'retention_days': retention_days
        }

        # 2. Activity data age (10 years)
        retention_days = get_retention_policy('activity_data', province)
        cursor.execute(f"""
            SELECT
                COUNT(*) as total_records,
                MIN("timestamp") as oldest_record,
                MAX("timestamp") as newest_record,
                COUNT(*) FILTER (WHERE "timestamp" < NOW() - INTERVAL '{retention_days} days') as beyond_retention
            FROM activity_data;
        """)

        result = cursor.fetchone()
        stats['activity_data'] = {
            'total': result[0],
            'oldest': result[1],
            'newest': result[2],
            'beyond_retention': result[3],
            'retention_days': retention_days
        }

        # 3. Soft-deleted patients (2 years for legal disputes)
        retention_days = get_retention_policy('soft_deleted_patients', province)
        cursor.execute(f"""
            SELECT
                COUNT(*) as total_deleted,
                COUNT(*) FILTER (WHERE deleted_at < NOW() - INTERVAL '{retention_days} days') as cleanup_eligible,
                MIN(deleted_at) as oldest_deletion,
                MAX(deleted_at) as newest_deletion
            FROM patients
            WHERE deleted_at IS NOT NULL;
        """)

        result = cursor.fetchone()
        stats['soft_deleted'] = {
            'total': result[0],
            'cleanup_eligible': result[1],
            'oldest': result[2],
            'newest': result[3],
            'retention_days': retention_days
        }

        # 4. Audit log age (10 years for compliance)
        retention_days = get_retention_policy('audit_log_entries', province)
        cursor.execute(f"""
            SELECT
                COUNT(*) as total_records,
                MIN("timestamp") as oldest_record,
                MAX("timestamp") as newest_record,
                COUNT(*) FILTER (WHERE "timestamp" < NOW() - INTERVAL '{retention_days} days') as beyond_retention,
                pg_size_pretty(pg_total_relation_size('audit_log_entries')) as table_size
            FROM audit_log_entries;
        """)

        result = cursor.fetchone()
        stats['audit_log'] = {
            'total': result[0],
            'oldest': result[1],
            'newest': result[2],
            'beyond_retention': result[3],
            'size': result[4],
            'retention_days': retention_days
        }

        # 5. Clinical visits age (10 years)
        retention_days = get_retention_policy('clinical_visits', province)
        cursor.execute(f"""
            SELECT
                COUNT(*) as total_visits,
                MIN(start_time) as oldest_visit,
                MAX(start_time) as newest_visit,
                COUNT(*) FILTER (WHERE start_time < NOW() - INTERVAL '{retention_days} days') as beyond_retention
            FROM visits;
        """)

        result = cursor.fetchone()
        stats['visits'] = {
            'total': result[0],
            'oldest': result[1],
            'newest': result[2],
            'beyond_retention': result[3],
            'retention_days': retention_days
        }

    # Log summary with Canadian context
    logger.info("\nRetention Status Summary (Canadian Healthcare Standards):")
    logger.info(f" Standard Retention Period: 10 years from last entry")
    logger.info(f" Legal Compliance: PIPEDA, PHIPA, Provincial Health Acts")

    logger.info(f"\n  Glucose Readings:")
    logger.info(f"    - Total: {stats['glucose_readings']['total']:,} records")
    logger.info(f"    - Beyond {stats['glucose_readings']['retention_days']/365:.1f}-year retention: "
                f"{stats['glucose_readings']['beyond_retention']:,}")
    logger.info(f"    - Size: {stats['glucose_readings']['size']}")

    logger.info(f"  Activity Data:")
    logger.info(f"    - Total: {stats['activity_data']['total']:,} records")
    logger.info(f"    - Beyond {stats['activity_data']['retention_days']/365:.1f}-year retention: "
                f"{stats['activity_data']['beyond_retention']:,}")

    logger.info(f"  Soft-Deleted Patients:")
    logger.info(f"    - Total: {stats['soft_deleted']['total']:,}")
    logger.info(f"    - Eligible for cleanup (>{stats['soft_deleted']['retention_days']} days): "
                f"{stats['soft_deleted']['cleanup_eligible']:,}")

    logger.info(f"  Clinical Visits:")
    logger.info(f"    - Total: {stats['visits']['total']:,} visits")
    logger.info(f"    - Beyond {stats['visits']['retention_days']/365:.1f}-year retention: "
                f"{stats['visits']['beyond_retention']:,}")

    logger.info(f"  Audit Logs:")
    logger.info(f"    - Total: {stats['audit_log']['total']:,} records")
    logger.info(f"    - Beyond {stats['audit_log']['retention_days']/365:.1f}-year retention: "
                f"{stats['audit_log']['beyond_retention']:,}")
    logger.info(f"    - Size: {stats['audit_log']['size']}")

    if province and province.lower() == 'british_columbia':
        logger.warning("\nBRITISH COLUMBIA NOTICE:")
        logger.warning("  BC requires PERMANENT retention of patient health records.")
        logger.warning("  You must ARCHIVE data before deletion using --export-archive.")

    if province and province.lower() == 'ontario':
        logger.info("\nONTARIO SPECIAL RULES:")
        logger.info("  Minor patient records: Keep 10 years OR until age 25 (whichever is longer)")

    return stats

def export_archival_data(older_than_days: int) -> Path:
    """
    Export data to permanent archive (required for BC and recommended for all provinces).
    Creates JSON archive with metadata for legal/compliance purposes.
    """
    logger.info(f"Exporting archival data (older than {older_than_days} days)...")

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    cutoff_date = datetime.now() - timedelta(days=older_than_days)
    archive_file = ARCHIVE_DIR / f"healthsync_archive_{timestamp}.json"

    archive_data = {
        'export_date': datetime.now().isoformat(),
        'cutoff_date': cutoff_date.isoformat(),
        'retention_period_days': older_than_days,
        'compliance': 'Canadian Healthcare Data Retention Standards',
        'data': {}
    }

    with get_conn() as conn:
        cursor = conn.cursor()

        # Export glucose readings
        cursor.execute("""
            SELECT
                reading_id, patient_id, device_id, "timestamp", value, unit,
                device_type, heart_rate, calories_burned
            FROM glucose_readings
            WHERE "timestamp" < %s
            ORDER BY "timestamp";
        """, (cutoff_date,))

        glucose_records = []
        for row in cursor.fetchall():
            glucose_records.append({
                'reading_id': str(row[0]),
                'patient_id': str(row[1]),
                'device_id': str(row[2]),
                'timestamp': row[3].isoformat(),
                'value': float(row[4]),
                'unit': row[5],
                'device_type': row[6],
                'heart_rate': row[7],
                'calories_burned': float(row[8]) if row[8] else None
            })

        archive_data['data']['glucose_readings'] = glucose_records
        logger.info(f"Exported {len(glucose_records):,} glucose readings")

        # Export activity data
        cursor.execute("""
            SELECT
                activity_id, patient_id, "timestamp", heart_rate, calories_burned
            FROM activity_data
            WHERE "timestamp" < %s
            ORDER BY "timestamp";
        """, (cutoff_date,))

        activity_records = []
        for row in cursor.fetchall():
            activity_records.append({
                'activity_id': str(row[0]),
                'patient_id': str(row[1]),
                'timestamp': row[2].isoformat(),
                'heart_rate': row[3],
                'calories_burned': float(row[4]) if row[4] else None
            })

        archive_data['data']['activity_data'] = activity_records
        logger.info(f"Exported {len(activity_records):,} activity records")

        # Export visits
        cursor.execute("""
            SELECT
                visit_id, patient_id, clinician_id, start_time, end_time,
                visit_type, status, notes
            FROM visits
            WHERE start_time < %s
            ORDER BY start_time;
        """, (cutoff_date,))

        visit_records = []
        for row in cursor.fetchall():
            visit_records.append({
                'visit_id': str(row[0]),
                'patient_id': str(row[1]),
                'clinician_id': str(row[2]),
                'start_time': row[3].isoformat(),
                'end_time': row[4].isoformat() if row[4] else None,
                'visit_type': row[5],
                'status': row[6],
                'notes': row[7]
            })

        archive_data['data']['visits'] = visit_records
        logger.info(f"Exported {len(visit_records):,} clinical visits")

    # Write archive file
    with open(archive_file, 'w', encoding='utf-8') as f:
        json.dump(archive_data, f, indent=2, ensure_ascii=False)

    file_size = archive_file.stat().st_size / (1024 * 1024)  # MB
    logger.info(f"Archive exported: {archive_file.name} ({file_size:.2f} MB)")
    logger.info(f"Archive location: {archive_file}")

    return archive_file

def cleanup_glucose_readings(older_than_days: int, dry_run: bool = True, province: Optional[str] = None) -> int:
    """Delete glucose readings older than specified days (Canadian 10-year standard)."""

    # Check BC permanent retention rule
    if province and province.lower() == 'british_columbia':
        logger.error("Cannot delete patient health records in British Columbia (permanent retention)")
        logger.info("Use --export-archive to create permanent archive instead")
        return 0

    logger.info(f"Cleaning glucose readings older than {older_than_days} days "
                f"({older_than_days/365:.1f} years)...")

    cutoff_date = datetime.now() - timedelta(days=older_than_days)

    with get_conn() as conn:
        cursor = conn.cursor()

        # Count records to be deleted
        cursor.execute("""
            SELECT COUNT(*)
            FROM glucose_readings
            WHERE "timestamp" < %s;
        """, (cutoff_date,))

        count = cursor.fetchone()[0]

        if count == 0:
            logger.info("No records to delete")
            return 0

        if dry_run:
            logger.info(f"[DRY RUN] Would delete {count:,} glucose readings")
            logger.info(f"Retention standard: {older_than_days/365:.1f} years (Canadian healthcare)")
            return count

        # Create audit log entry before deletion (compliance requirement)
        cursor.execute("""
            INSERT INTO audit_log_entries (log_id, "timestamp", action, table_name, record_count, metadata)
            VALUES (uuid_generate_v4(), NOW(), 'DATA_RETENTION_CLEANUP', 'glucose_readings', %s, %s);
        """, (count, json.dumps({
            'cutoff_date': cutoff_date.isoformat(),
            'retention_days': older_than_days,
            'compliance': 'Canadian Healthcare Data Retention'
        })))

        # Delete in batches to avoid locking
        batch_size = 10000
        total_deleted = 0

        while True:
            cursor.execute("""
                DELETE FROM glucose_readings
                WHERE reading_id IN (
                    SELECT reading_id
                    FROM glucose_readings
                    WHERE "timestamp" < %s
                    LIMIT %s
                );
            """, (cutoff_date, batch_size))

            deleted = cursor.rowcount
            total_deleted += deleted

            logger.info(f"Deleted batch: {deleted:,} records (total: {total_deleted:,})")

            if deleted < batch_size:
                break

        logger.info(f"Deleted {total_deleted:,} glucose readings (compliance: {older_than_days/365:.1f}-year retention)")
        return total_deleted

def cleanup_activity_data(older_than_days: int, dry_run: bool = True, province: Optional[str] = None) -> int:
    """Delete activity data older than specified days (Canadian 10-year standard)."""

    if province and province.lower() == 'british_columbia':
        logger.error("Cannot delete patient health records in British Columbia (permanent retention)")
        return 0

    logger.info(f"Cleaning activity data older than {older_than_days} days...")

    cutoff_date = datetime.now() - timedelta(days=older_than_days)

    with get_conn() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*)
            FROM activity_data
            WHERE "timestamp" < %s;
        """, (cutoff_date,))

        count = cursor.fetchone()[0]

        if count == 0:
            logger.info("  ✓ No records to delete")
            return 0

        if dry_run:
            logger.info(f"[DRY RUN] Would delete {count:,} activity records")
            return count

        # Audit log
        cursor.execute("""
            INSERT INTO audit_log_entries (log_id, "timestamp", action, table_name, record_count, metadata)
            VALUES (uuid_generate_v4(), NOW(), 'DATA_RETENTION_CLEANUP', 'activity_data', %s, %s);
        """, (count, json.dumps({
            'cutoff_date': cutoff_date.isoformat(),
            'retention_days': older_than_days
        })))

        # Delete in batches
        batch_size = 10000
        total_deleted = 0

        while True:
            cursor.execute("""
                DELETE FROM activity_data
                WHERE activity_id IN (
                    SELECT activity_id
                    FROM activity_data
                    WHERE "timestamp" < %s
                    LIMIT %s
                );
            """, (cutoff_date, batch_size))

            deleted = cursor.rowcount
            total_deleted += deleted

            logger.info(f"Deleted batch: {deleted:,} records (total: {total_deleted:,})")

            if deleted < batch_size:
                break

        logger.info(f"Deleted {total_deleted:,} activity records")
        return total_deleted

def cleanup_audit_logs(older_than_days: int, dry_run: bool = True) -> int:
    """Delete audit logs older than specified days (10 years for compliance)."""
    logger.info(f"Cleaning audit logs older than {older_than_days} days...")

    cutoff_date = datetime.now() - timedelta(days=older_than_days)

    with get_conn() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*)
            FROM audit_log_entries
            WHERE "timestamp" < %s;
        """, (cutoff_date,))

        count = cursor.fetchone()[0]

        if count == 0:
            logger.info("No records to delete")
            return 0

        if dry_run:
            logger.info(f"[DRY RUN] Would delete {count:,} audit log entries")
            return count

        # Delete in batches
        batch_size = 5000
        total_deleted = 0

        while True:
            cursor.execute("""
                DELETE FROM audit_log_entries
                WHERE log_id IN (
                    SELECT log_id
                    FROM audit_log_entries
                    WHERE "timestamp" < %s
                    LIMIT %s
                );
            """, (cutoff_date, batch_size))

            deleted = cursor.rowcount
            total_deleted += deleted

            logger.info(f"Deleted batch: {deleted:,} records (total: {total_deleted:,})")

            if deleted < batch_size:
                break

        logger.info(f"Deleted {total_deleted:,} audit log entries")
        return total_deleted


def cleanup_soft_deleted_patients(older_than_days: int, dry_run: bool = True, province: Optional[str] = None) -> int:
    """
    Permanently delete soft-deleted patients after 2-year retention period.
    Allows for legal disputes and access requests (PIPEDA compliance).
    """
    logger.info(f"Cleaning soft-deleted patients (deleted >{older_than_days} days ago)...")

    cutoff_date = datetime.now() - timedelta(days=older_than_days)

    with get_conn() as conn:
        cursor = conn.cursor()

        # Find eligible patients (considering minor rules for Ontario)
        cursor.execute("""
            SELECT patient_id, first_name, last_name, deleted_at, date_of_birth
            FROM patients
            WHERE deleted_at IS NOT NULL
            AND deleted_at < %s;
        """, (cutoff_date,))

        patients = cursor.fetchall()

        if not patients:
            logger.info("  ✓ No soft-deleted patients to clean up")
            return 0

        # Filter patients based on provincial rules
        eligible_patients = []
        for patient_id, first_name, last_name, deleted_at, dob in patients:
            if province and province.lower() == 'ontario':
                # Check minor rules
                age_at_deletion = (deleted_at.date() - dob).days / 365.25
                if age_at_deletion < 18:
                    # Minor: check if 10 years OR age 25 has passed
                    days_since_deletion = (datetime.now().date() - deleted_at.date()).days
                    current_age = (datetime.now().date() - dob).days / 365.25

                    if days_since_deletion >= 3650 or current_age >= 25:
                        eligible_patients.append((patient_id, first_name, last_name, deleted_at))
                    else:
                        logger.info(f"Skipping minor patient: {first_name} {last_name} "
                                  f"(must wait until age 25 or 10 years)")
                        continue
                else:
                    eligible_patients.append((patient_id, first_name, last_name, deleted_at))
            else:
                eligible_patients.append((patient_id, first_name, last_name, deleted_at))

        if not eligible_patients:
            logger.info("  ✓ No eligible patients to delete (minor rules applied)")
            return 0

        if dry_run:
            logger.info(f"[DRY RUN] Would permanently delete {len(eligible_patients)} patients:")
            for patient_id, first_name, last_name, deleted_at in eligible_patients[:5]:
                logger.info(f"    - {first_name} {last_name} (deleted: {deleted_at.date()})")
            if len(eligible_patients) > 5:
                logger.info(f"... and {len(eligible_patients) - 5} more")
            return len(eligible_patients)

        # Audit log before deletion
        cursor.execute("""
            INSERT INTO audit_log_entries (log_id, "timestamp", action, table_name, record_count, metadata)
            VALUES (uuid_generate_v4(), NOW(), 'PERMANENT_PATIENT_DELETION', 'patients', %s, %s);
        """, (len(eligible_patients), json.dumps({
            'cutoff_date': cutoff_date.isoformat(),
            'retention_days': older_than_days,
            'province': province
        })))

        # Delete patients and cascade to related records
        deleted_count = 0
        for patient_id, first_name, last_name, deleted_at in eligible_patients:
            cursor.execute("""
                DELETE FROM patients WHERE patient_id = %s;
            """, (patient_id,))

            deleted_count += 1
            logger.info(f"Deleted patient: {first_name} {last_name} (deleted: {deleted_at.date()})")

        logger.info(f"Permanently deleted {deleted_count} soft-deleted patients (2-year retention)")
        return deleted_count


def vacuum_and_analyze():
    """Run VACUUM and ANALYZE to reclaim space and update statistics."""
    logger.info("Running VACUUM and ANALYZE...")

    with get_conn() as conn:
        # Must be outside transaction
        conn.autocommit = True
        cursor = conn.cursor()

        tables = ['glucose_readings', 'activity_data', 'audit_log_entries', 'patients', 'visits']

        for table in tables:
            logger.info(f"Vacuuming {table}...")
            cursor.execute(f"VACUUM ANALYZE {table};")
            logger.info(f"{table} vacuumed")

    logger.info("VACUUM complete - disk space reclaimed")

def main():
    """Main cleanup workflow with error handling."""
    parser = argparse.ArgumentParser(
        description="Clean up old data from HealthSYNC database"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without deleting any data"
    )

    parser.add_argument(
        "--type",
        choices=["glucose", "activity", "audit", "visits", "soft_deleted_patients", "all"],
        default="all",
        help="Type of data to clean up"
    )

    parser.add_argument(
        "--older-than",
        type=int,
        help = "Delete data older than specified days (default varies by data type)"
    )

    parser.add_argument(
        "--province",
        choices=[p.lower() for p in PROVINCIAL_POLICIES.keys()],
        help="Apply provincial data retention rules"
    )

    parser.add_argument(
        "--soft-deleted-only",
        action="store_true",
        help="Only clean up soft-deleted patients"

    )

    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Only show retention statistics, don't delete anything"
    )

    parser.add_argument(
        "--export-archive",
        action="store_true",
        help="Export data to permanent archive (required for BC, recommended for all)"
    )

    parser.add_argument(
        "--vacuum",
        action="store_true",
        help="Run VACUUM after cleanup to reclaim disk space"
    )

    args = parser.parse_args()

    # Normalize province name
    province = args.province.lower() if args.province else None

    logger.info("=" * 70)
    logger.info("HealthSYNC Data Cleanup - Canadian Healthcare Compliance")
    logger.info("=" * 70)


    logger.info(f"Province: {province.upper() if province else 'Federal/Standard'}")
    logger.info(f"Dry Run: {'Yes' if args.dry_run else 'No'}")

    try:
        # Get retention stats
        stats = get_retention_stats(province)
        if args.stats_only:
            logger.info("\nStatistics displayed. Exiting.")
            return

        # Export archival data if requested
        if args.export_archive:
            older_than = args.older_than or get_retention_policy('patient_health_records', province)
            archive_file = export_archival_data(older_than)
            logger.info("\n Archive created. Exiting...")
            return

        if province and province.lower() == 'british_columbia':
            logger.error("Cannot delete patient health records in British Columbia due to permanent retention policy.")
            logger.error("British Columbia requires permanent retention of patient health records.")
            logger.error("Use --export-archive to create permanent archive before deletion.")
            logger.error("\nRun: python backend/scripts/03_cleanup_old_data.py --export-archive --province british_columbia")
            sys.exit(1)

        total_deleted = 0

        if args.soft_deleted_only:
            # Only clean soft-deleted patients (2 years)
            older_than = args.older_than or get_retention_policy('soft_deleted_patients', province)
            deleted = cleanup_soft_deleted_patients(older_than, args.dry_run, province)
            total_deleted += deleted

        elif args.type == 'glucose':
            older_than = args.older_than or get_retention_policy('glucose_readings', province)
            deleted = cleanup_glucose_readings(older_than, args.dry_run, province)
            total_deleted += deleted

        elif args.type == 'activity':
            older_than = args.older_than or get_retention_policy('activity_data', province)
            deleted = cleanup_activity_data(older_than, args.dry_run, province)
            total_deleted += deleted

        elif args.type == 'audit':
            older_than = args.older_than or get_retention_policy('audit_log_entries', province)
            deleted = cleanup_audit_logs(older_than, args.dry_run)
            total_deleted += deleted

        elif args.type == 'soft-deleted':
            older_than = args.older_than or get_retention_policy('soft_deleted_patients', province)
            deleted = cleanup_soft_deleted_patients(older_than, args.dry_run, province)
            total_deleted += deleted

        elif args.type == 'all':
            # Clean all data types (respecting Canadian 10-year standard)
            deleted = cleanup_glucose_readings(
                get_retention_policy('glucose_readings', province), args.dry_run, province
            )
            total_deleted += deleted

            deleted = cleanup_activity_data(
                get_retention_policy('activity_data', province), args.dry_run, province
            )
            total_deleted += deleted

            deleted = cleanup_audit_logs(
                get_retention_policy('audit_log_entries', province), args.dry_run
            )
            total_deleted += deleted

            deleted = cleanup_soft_deleted_patients(
                get_retention_policy('soft_deleted_patients', province), args.dry_run, province
            )
            total_deleted += deleted

        if args.vacuum and not args.dry_run:
            vacuum_and_analyze()

        logger.info("\n" + "=" * 70)
        if args.dry_run:
            logger.info(f"[DRY RUN] Total records that would be deleted: {total_deleted:,}")
            logger.info("\nTo actually delete data, rerun without --dry-run")

        else:
            logger.info(f"Total records deleted: {total_deleted:,}")
            logger.info("Data cleanup complete.")

            if args.vacuum:
                logger.info("VACUUM operation completed.")

    except KeyboardInterrupt:
        logger.warning("Cleanup process interrupted by user.")
        traceback.print_exc()
        sys.exit(1)


