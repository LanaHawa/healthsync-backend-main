# backend/src/healthsync/core/config.py

"""
Central application configuration.

Loads environment variables from:
    - repo-root/.env  (preferred)
    - fallback to default load_dotenv()

Also exposes strongly-typed configuration values.
"""

import os
from pathlib import Path
from dotenv import load_dotenv


# --------------------------------------------------
# Locate repository root (look for docker-compose.yml)
# --------------------------------------------------
def _find_repo_root() -> Path:
    p = Path(__file__).resolve()

    for parent in p.parents:
        if (parent / "docker-compose.yml").exists():
            return parent

    # fallback (shouldn't normally happen)
    return Path.cwd()


REPO_ROOT = _find_repo_root()


# --------------------------------------------------
# Load .env file
# --------------------------------------------------
ENV_PATH = REPO_ROOT / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()


# --------------------------------------------------
# Database configuration
# --------------------------------------------------
DATABASE_URL: str | None = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. "
        "Make sure your .env file exists at the project root "
        "or the environment variable is defined."
    )


# --------------------------------------------------
# JWT configuration
# --------------------------------------------------
JWT_SECRET: str = os.getenv("JWT_SECRET", "dev_secret_change_me")
JWT_ALG: str = os.getenv("JWT_ALG", "HS256")
JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "120"))


# --------------------------------------------------
# App environment
# --------------------------------------------------
ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
DEBUG: bool = ENVIRONMENT.lower() == "development"
