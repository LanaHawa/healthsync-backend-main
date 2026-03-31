"""Quick script to update existing clinics with clinic_code from CSV."""

import sys
import csv
import logging
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent
SYNTHETIC_DIR = BACKEND_DIR / "data" / "synthetic_data"
sys.path.insert(0, str(BACKEND_DIR / "src"))

from healthsync.db.connection import get_conn

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def update_clinic_codes():
    """Update existing clinics with clinic_code from CSV."""
    csv_path = SYNTHETIC_DIR / "clinics.csv"

    if not csv_path.exists():
        logger.error(f"CSV file not found: {csv_path}")
        return False

    try:
        with get_conn() as conn:
            with conn.cursor() as cursor:
                # Read CSV
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    clinics = list(reader)

                logger.info(f"Found {len(clinics)} clinics in CSV")

                # Get existing clinics from DB
                cursor.execute("SELECT clinic_id, name FROM clinics ORDER BY name")
                db_clinics = cursor.fetchall()

                logger.info(f"Found {len(db_clinics)} clinics in database")

                # Match by position (assuming same order)
                if len(clinics) != len(db_clinics):
                    logger.warning(f"Mismatch: CSV has {len(clinics)} clinics, DB has {len(db_clinics)}")

                updated = 0
                for i, (clinic_id, db_name) in enumerate(db_clinics):
                    if i < len(clinics):
                        csv_row = clinics[i]
                        clinic_code = csv_row.get('clinic_code', '').strip()

                        if clinic_code:
                            cursor.execute(
                                "UPDATE clinics SET clinic_code = %s WHERE clinic_id = %s",
                                (clinic_code, str(clinic_id))
                            )
                            logger.info(f"Updated {db_name} with code {clinic_code}")
                            updated += 1

                conn.commit()
                logger.info(f"Successfully updated {updated} clinics with clinic codes")
                return True

    except Exception as e:
        logger.error(f"Error updating clinic codes: {e}")
        return False


if __name__ == "__main__":
    success = update_clinic_codes()
    sys.exit(0 if success else 1)
