"""Paths and local database configuration. Credentials are never logged."""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
load_dotenv(ROOT / ".env", interpolate=False)


def database_url() -> str | URL:
    """Use URL.create so special characters in separate env fields remain safe."""
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    password = os.getenv("POSTGRES_PASSWORD")
    if not password:
        raise ValueError("Set POSTGRES_PASSWORD in .env; see .env.example")
    return URL.create(
        "postgresql+psycopg",
        username=os.getenv("POSTGRES_USER", "olist"),
        password=password,
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "olist"),
    )
