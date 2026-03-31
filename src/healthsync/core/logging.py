# backend/src/healthsync/core/logging.py

"""
Centralized logging configuration for HealthSYNC backend.
"""

import logging
import os


def setup_logging() -> None:
    """
    Configures application-wide logging.

    Environment variables:
        LOG_LEVEL=DEBUG | INFO | WARNING | ERROR | CRITICAL
    """

    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Reduce noisy third-party logs (optional but recommended)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
