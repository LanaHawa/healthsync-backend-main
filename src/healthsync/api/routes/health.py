# backend/src/healthsync/routes/health.py

from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from healthsync.db.connection import engine


router = APIRouter(tags=["Health"])


@router.get("/health")
def api_health():
    """
    API-level health check.
    """
    return {
        "status": "ok",
        "service": "healthsync-backend",
    }


@router.get("/db/health")
def db_health():
    """
    Database connectivity + TimescaleDB check.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

            result = conn.execute(
                text(
                    """
                    SELECT extname
                    FROM pg_extension
                    WHERE extname = 'timescaledb'
                    """
                )
            ).fetchone()

        return {
            "db": "ok",
            "timescaledb_installed": bool(result),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
