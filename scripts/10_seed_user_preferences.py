"""
Script 10: Seed default user_preferences rows for all existing auth_users.

Inserts a preferences row with defaults for every auth_user that doesn't
already have one. Safe to re-run (uses INSERT ... ON CONFLICT DO NOTHING).

Default glucose unit: mmol/L (Canada standard / SI unit)
Users can change their preference in the Settings/Preferences UI.

Usage (from the backend/ directory):
    python scripts/10_seed_user_preferences.py
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR / "src"))

from dotenv import load_dotenv

load_dotenv(BACKEND_DIR / ".env")

from healthsync.db.connection import get_conn


def seed_preferences() -> None:
    sql_fetch = "SELECT user_id FROM auth_users ORDER BY user_id;"
    sql_insert = """
        INSERT INTO user_preferences (auth_user_id)
        VALUES (%s)
        ON CONFLICT (auth_user_id) DO NOTHING;
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_fetch)
            users = cur.fetchall()

        inserted = 0
        skipped = 0
        with conn.cursor() as cur:
            for (user_id,) in users:
                cur.execute(
                    """SELECT 1 FROM user_preferences WHERE auth_user_id = %s LIMIT 1;""",
                    (str(user_id),),
                )
                if cur.fetchone():
                    skipped += 1
                else:
                    cur.execute(sql_insert, (str(user_id),))
                    inserted += 1

    print(f"Done. Inserted: {inserted}  |  Already existed (skipped): {skipped}")


if __name__ == "__main__":
    seed_preferences()
