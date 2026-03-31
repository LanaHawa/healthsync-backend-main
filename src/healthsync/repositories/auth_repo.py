# backend/src/healthsync/repositories/auth_repo.py

from typing import Optional, Dict, Any
from psycopg2.extras import RealDictCursor


ALLOWED_ROLES = {"PATIENT", "CLINICIAN", "ADMIN"}


class AuthRepository:
    # ---------------------------------------------------------
    # Create User
    # ---------------------------------------------------------
    def create_user(
        self,
        conn,
        email: str,
        password_hash: str,
        role: str,
    ) -> Dict[str, Any]:
        role = (role or "").upper()
        if role not in ALLOWED_ROLES:
            raise ValueError(f"Invalid role: {role}")

        normalized_email = email.strip().lower()

        sql = """
        INSERT INTO auth_users (email, password_hash, role)
        VALUES (%s, %s, %s)
        RETURNING
            user_id,
            email,
            role,
            mfa_enabled,
            identity_provider,
            last_login_at;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (normalized_email, password_hash, role))
            return cur.fetchone()

    # ---------------------------------------------------------
    # Get User by Email
    # ---------------------------------------------------------
    def get_user_by_email(
        self,
        conn,
        email: str,
    ) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT
            user_id,
            email,
            password_hash,
            role,
            mfa_enabled,
            identity_provider,
            last_login_at
        FROM auth_users
        WHERE email = %s
        LIMIT 1;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (email.strip().lower(),))
            return cur.fetchone()

    # ---------------------------------------------------------
    # Get User by ID
    # ---------------------------------------------------------
    def get_user_by_id(
        self,
        conn,
        user_id: str,
    ) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT
            user_id,
            email,
            role,
            mfa_enabled,
            identity_provider,
            last_login_at
        FROM auth_users
        WHERE user_id = %s
        LIMIT 1;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (user_id,))
            return cur.fetchone()

    # ---------------------------------------------------------
    # Update Last Login Timestamp
    # ---------------------------------------------------------
    def update_last_login(
        self,
        conn,
        user_id: str,
    ) -> None:
        sql = """
        UPDATE auth_users
        SET last_login_at = NOW()
        WHERE user_id = %s;
        """
        with conn.cursor() as cur:
            cur.execute(sql, (user_id,))

    # ---------------------------------------------------------
    # Get password hash by user_id (for change-password flow)
    # ---------------------------------------------------------
    def get_password_hash(
        self,
        conn,
        user_id: str,
    ) -> Optional[str]:
        sql = "SELECT password_hash FROM auth_users WHERE user_id = %s LIMIT 1;"
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (user_id,))
            row = cur.fetchone()
            return row["password_hash"] if row else None

    # ---------------------------------------------------------
    # Update Password Hash
    # ---------------------------------------------------------
    def update_password(
        self,
        conn,
        user_id: str,
        new_password_hash: str,
    ) -> None:
        sql = """
        UPDATE auth_users
        SET password_hash = %s
        WHERE user_id = %s;
        """
        with conn.cursor() as cur:
            cur.execute(sql, (new_password_hash, user_id))
