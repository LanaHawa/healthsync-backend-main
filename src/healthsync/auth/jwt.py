# backend/src/healthsync/auth/jwt.py

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError


# ----------------------------
# Security scheme
# ----------------------------
security = HTTPBearer(auto_error=True)


# ----------------------------
# Environment config
# ----------------------------
JWT_SECRET = os.getenv("JWT_SECRET", "dev_secret_change_me")
JWT_ALG = os.getenv("JWT_ALG", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "120"))


# ----------------------------
# Token creation
# ----------------------------
def create_access_token(
    payload: Dict[str, Any],
    expires_minutes: Optional[int] = None,
) -> str:
    """
    Creates a signed JWT access token.

    Required payload fields (recommended):
        - user_id
        - role
        - email
    """
    exp_minutes = expires_minutes if expires_minutes is not None else JWT_EXPIRE_MINUTES

    now = datetime.now(timezone.utc)
    to_encode = dict(payload)

    # Standard JWT claims
    to_encode["iat"] = int(now.timestamp())
    to_encode["exp"] = int((now + timedelta(minutes=exp_minutes)).timestamp())

    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALG)


# ----------------------------
# Token decoding
# ----------------------------
def decode_token(token: str) -> Dict[str, Any]:
    """
    Decodes and validates JWT.
    Raises 401 if invalid or expired.
    """
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


# ----------------------------
# Require authenticated user
# ----------------------------
def require_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict[str, Any]:
    """
    Dependency that:
        - Extracts Bearer token
        - Validates JWT
        - Ensures required claims exist
    """
    token = credentials.credentials
    data = decode_token(token)

    user_id = data.get("user_id")
    role = data.get("role")
    email = data.get("email")

    if not user_id or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    return {
        "user_id": str(user_id),
        "role": str(role),
        "email": email,
    }


# ----------------------------
# Require specific roles
# ----------------------------
def require_role(*roles: str):
    """
    Usage:
        Depends(require_role("PATIENT"))
        Depends(require_role("CLINICIAN", "ADMIN"))
    """
    allowed = {r.upper() for r in roles}

    def _dep(user: Dict[str, Any] = Depends(require_user)) -> Dict[str, Any]:
        user_role = (user.get("role") or "").upper()
        if user_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden",
            )
        return user

    return _dep
