# OWNERSHIP: tooling
"""Runtime configuration.

Environment values are read by reference only (``os.getenv``). The hub ``.env``
file is optionally loaded if it exists — secret values are never copied into
this repository.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HUB_ENV = Path(r"C:\personal\naquuuu\.env")

MIN_DELAY_SECONDS = 2.0
JITTER_SECONDS = 1.0
REQUEST_TIMEOUT = 3.0
MAX_RETRIES = 2
FRESHNESS_HORIZON_DAYS = 60
FULL_START_DEFAULT = "2016-01-01"
MAX_PAGINATION_PAGES = 50


@dataclass(frozen=True)
class Settings:
    """Resolved local paths and politeness parameters."""

    project_root: Path
    data_dir: Path
    db_path: Path
    raw_dir: Path
    inbox_dir: Path
    exports_dir: Path
    min_delay: float = MIN_DELAY_SECONDS
    jitter: float = JITTER_SECONDS
    timeout: float = REQUEST_TIMEOUT
    max_retries: int = MAX_RETRIES
    horizon_days: int = FRESHNESS_HORIZON_DAYS
    max_pages: int = MAX_PAGINATION_PAGES


def load_hub_env_by_reference() -> Path | None:
    """Load the hub ``.env`` if present, without copying any values.

    Returns the path that was loaded, or ``None`` when absent/unavailable.
    """

    env_path = Path(os.getenv("BI_SCRAPER_HUB_ENV", str(DEFAULT_HUB_ENV))).expanduser()
    if not env_path.is_file():
        return None
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dotenv is a declared dependency
        return None
    load_dotenv(env_path, override=False)
    return env_path


def get_settings() -> Settings:
    """Build settings from environment variables with sensible defaults."""

    data_dir = Path(
        os.getenv("BI_SCRAPER_DATA_DIR", str(PROJECT_ROOT / "data"))
    ).expanduser()
    db_path = Path(
        os.getenv("BI_SCRAPER_DB", str(data_dir / "bi_study.db"))
    ).expanduser()
    exports_dir = Path(
        os.getenv("BI_SCRAPER_EXPORTS_DIR", str(PROJECT_ROOT / "exports"))
    ).expanduser()
    return Settings(
        project_root=PROJECT_ROOT,
        data_dir=data_dir,
        db_path=db_path,
        raw_dir=data_dir / "raw",
        inbox_dir=data_dir / "inbox",
        exports_dir=exports_dir,
    )


def today() -> date:
    """Current local date (freshness default end date)."""

    return date.today()
