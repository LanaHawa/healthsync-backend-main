# backend/src/healthsync/db/connection.py

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import Dict, Generator, Optional

import psycopg2
import psycopg2.pool
from psycopg2 import OperationalError
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Environment
# -----------------------------------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is not set. "
        "Please configure it in .env (or your environment)."
    )

# -----------------------------------------------------------------------------
# SQLAlchemy engine (used for /db/health and any future SQLAlchemy usage)
# -----------------------------------------------------------------------------

engine: Engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
    connect_args={
        "connect_timeout": 10,
        "options": "-c timezone=utc",
    },
)


@event.listens_for(engine, "connect")
def _on_connect(dbapi_conn, connection_record):
    logger.debug("New SQLAlchemy DB connection established")


@event.listens_for(engine, "checkout")
def _on_checkout(dbapi_conn, connection_record, connection_proxy):
    logger.debug("SQLAlchemy connection checked out from pool")


# -----------------------------------------------------------------------------
# psycopg2 pool (used by repositories that use cursor-based SQL)
# -----------------------------------------------------------------------------

connection_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None

try:
    connection_pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=20,
        dsn=DATABASE_URL,
        connect_timeout=10,
    )
    logger.info("✓ psycopg2 connection pool initialized")
except Exception as e:
    logger.error(f"Failed to initialize psycopg2 connection pool: {e}")
    connection_pool = None


def _pool_stats() -> Dict[str, int]:
    """
    Best-effort pool stats. psycopg2 pool internals differ by version.
    We avoid hard dependency on private attributes but use them if present.
    """
    if not connection_pool:
        return {"minconn": 0, "maxconn": 0, "used": 0, "idle": 0}

    minconn = getattr(connection_pool, "minconn", 0)
    maxconn = getattr(connection_pool, "maxconn", 0)

    used_obj = getattr(connection_pool, "_used", None)
    idle_obj = getattr(connection_pool, "_pool", None)

    used = len(used_obj) if used_obj is not None else 0
    idle = len(idle_obj) if idle_obj is not None else 0

    return {
        "minconn": int(minconn),
        "maxconn": int(maxconn),
        "used": int(used),
        "idle": int(idle),
    }


# -----------------------------------------------------------------------------
# Connection context managers
# -----------------------------------------------------------------------------


@contextmanager
def get_conn(max_retries: int = 3, retry_delay: float = 0.5) -> Generator:
    """
    Yield a psycopg2 connection.
    - Commits on success
    - Rolls back on error
    - Returns connection to pool (or closes if no pool)
    - Retries OperationalError with exponential backoff
    """
    conn = None
    last_error: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            if connection_pool:
                conn = connection_pool.getconn()
            else:
                conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)

            # Enforce UTC at session level (Timescale-friendly)
            with conn.cursor() as cur:
                cur.execute("SET timezone TO 'UTC';")

            try:
                yield conn
                conn.commit()
                return
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise

        except OperationalError as e:
            last_error = e
            logger.warning(
                f"DB connection error (attempt {attempt}/{max_retries}): {e}"
            )

            # ensure this conn isn't reused
            if conn is not None:
                try:
                    if connection_pool:
                        connection_pool.putconn(conn, close=True)
                    else:
                        conn.close()
                except Exception:
                    pass
                conn = None

            if attempt < max_retries:
                time.sleep(retry_delay * (2 ** (attempt - 1)))
            else:
                break

        finally:
            # Return healthy connection to pool / close if standalone.
            if conn is not None:
                try:
                    if connection_pool:
                        connection_pool.putconn(conn)
                    else:
                        conn.close()
                except Exception as e:
                    logger.warning(f"Error returning/closing connection: {e}")
                conn = None

    raise OperationalError(
        f"Could not connect after {max_retries} attempts. Last error: {last_error}"
    )


@contextmanager
def get_dict_cursor(max_retries: int = 3, retry_delay: float = 0.5):
    """
    Yield a RealDictCursor for convenience.
    Use this when you want dict rows without manually passing cursor_factory.
    """
    with get_conn(max_retries=max_retries, retry_delay=retry_delay) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur


# -----------------------------------------------------------------------------
# Cleanup on shutdown
# -----------------------------------------------------------------------------


def close_all_connections() -> None:
    """Close psycopg2 pool and dispose SQLAlchemy engine."""
    logger.info("Closing all database connections...")

    if connection_pool:
        try:
            connection_pool.closeall()
            logger.info("✓ psycopg2 pool closed")
        except Exception as e:
            logger.error(f"Error closing psycopg2 pool: {e}")

    try:
        engine.dispose()
        logger.info("✓ SQLAlchemy engine disposed")
    except Exception as e:
        logger.error(f"Error disposing SQLAlchemy engine: {e}")


# -----------------------------------------------------------------------------
# Health checks
# -----------------------------------------------------------------------------


def check_database_health() -> dict:
    """
    Check DB connectivity and (if present) TimescaleDB extension/hypertables.
    Safe to call in an API route.
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT version();")
                pg_version_full = cursor.fetchone()[0]
                pg_version = (pg_version_full.split() or ["unknown", "unknown"])[1]

                # Timescale extension version (if installed)
                cursor.execute(
                    """
                    SELECT extversion
                    FROM pg_extension
                    WHERE extname = 'timescaledb';
                    """
                )
                ts_row = cursor.fetchone()
                timescale_version = ts_row[0] if ts_row else None

                hypertable_count = 0
                if timescale_version:
                    try:
                        cursor.execute(
                            """
                            SELECT COUNT(*)
                            FROM timescaledb_information.hypertables
                            WHERE hypertable_schema = 'public';
                            """
                        )
                        hypertable_count = int(cursor.fetchone()[0])
                    except Exception:
                        hypertable_count = 0

                stats = _pool_stats()

                return {
                    "status": "healthy",
                    "postgresql_version": pg_version,
                    "timescaledb_version": timescale_version or "not installed",
                    "hypertable_count": hypertable_count,
                    "pool": stats,
                }

    except Exception as e:
        logger.error(f"Database health check failed: {e}", exc_info=True)
        return {"status": "unhealthy", "error": str(e)}


def test_connection() -> bool:
    """
    Quick CLI-friendly test.
    Returns True if healthy, False otherwise.
    """
    health = check_database_health()
    if health.get("status") != "healthy":
        logger.error(f"Database unhealthy: {health.get('error')}")
        return False

    logger.info("Database connection successful")
    logger.info(f"  PostgreSQL: {health.get('postgresql_version')}")
    logger.info(f"  TimescaleDB: {health.get('timescaledb_version')}")
    logger.info(f"  Hypertables: {health.get('hypertable_count')}")
    logger.info(f"  Pool: {health.get('pool')}")
    return True
