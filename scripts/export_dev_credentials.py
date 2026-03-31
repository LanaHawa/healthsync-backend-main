"""
Export login credentials for all users by resetting passwords.

WARNING: This will reset ALL user passwords in the database!
Only use in development environments.
"""

import sys
import csv
import secrets
import string
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR / "src"))

from healthsync.db.connection import get_conn
import bcrypt


def generate_password(length: int = 12) -> str:
    """Generate a secure random password."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def reset_and_export_credentials():
    """Reset all user passwords and export to CSV."""
    credentials = []

    print("\n" + "=" * 70)
    print("🔄 RESETTING ALL USER PASSWORDS")
    print("=" * 70)
    print("⚠️  WARNING: This will change passwords for ALL users!")
    print()

    confirm = input("Type 'RESET ALL PASSWORDS' to confirm: ")
    if confirm != "RESET ALL PASSWORDS":
        print("❌ Operation cancelled.")
        return

    print("\n🔄 Processing users...\n")

    with get_conn() as conn:
        with conn.cursor() as cursor:
            # Get all users with their profile information
            cursor.execute("""
                SELECT
                    u.user_id,
                    u.email,
                    u.role,
                    COALESCE(c.first_name, p.first_name) as first_name,
                    COALESCE(c.last_name, p.last_name) as last_name
                FROM auth_users u
                LEFT JOIN clinicians c ON u.user_id = c.auth_user_id
                LEFT JOIN patients p ON u.user_id = p.auth_user_id
                ORDER BY u.role, first_name, last_name
            """)

            users = cursor.fetchall()

            if not users:
                print("❌ No users found in database.")
                return

            print(f"Found {len(users)} users\n")

            # Process each user
            for user in users:
                user_id, email, role, first_name, last_name = user

                # Generate new password
                new_password = generate_password(12)
                password_hash = hash_password(new_password)

                # Update password in database
                cursor.execute(
                    "UPDATE auth_users SET password_hash = %s WHERE user_id = %s",
                    (password_hash, user_id),
                )

                # Store credential
                credentials.append(
                    {
                        "role": role,
                        "first_name": first_name or "",
                        "last_name": last_name or "",
                        "email": email,
                        "password": new_password,
                    }
                )

                # Print credential
                name = f"{first_name} {last_name}".strip() or "Unknown"
                print(f"✓ {role:10} | {name:30} | {email:45} | {new_password}")

            # Commit changes
            conn.commit()
            print(f"\n✅ Successfully reset {len(credentials)} passwords")

    # Export to CSV
    credentials_file = BACKEND_DIR / "data" / "dev_credentials.csv"
    credentials_file.parent.mkdir(parents=True, exist_ok=True)

    with open(credentials_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["role", "first_name", "last_name", "email", "password"]
        )
        writer.writeheader()
        writer.writerows(credentials)

    print(f"\n📄 Credentials exported to: {credentials_file}")
    print(f"   Total credentials: {len(credentials)}")
    print("\n💡 All users can now login with these new passwords!")
    print("⚠️  Keep this file secure - do NOT commit to Git!")
    print("\n" + "=" * 70)


if __name__ == "__main__":
    try:
        reset_and_export_credentials()
    except KeyboardInterrupt:
        print("\n\n❌ Operation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
