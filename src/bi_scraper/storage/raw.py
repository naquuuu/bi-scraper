# OWNERSHIP: tooling
"""Raw HTML snapshot writer: ``data/raw/{chapter}/``."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug_from_url(url: str) -> str:
    path = urlparse(url).path
    name = path.rstrip("/").rsplit("/", 1)[-1] or "index"
    if not name.lower().endswith(".html"):
        name = f"{name}.html"
    return _SAFE_RE.sub("_", name)[:120] or "index.html"


def save_raw(
    raw_dir: Path,
    chapter: int,
    url: str,
    body: bytes,
    fetched_at: str | None = None,
) -> Path:
    """Write a raw snapshot and return its path."""

    stamp = (
        fetched_at
        or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ).replace(":", "").replace("-", "")
    chapter_dir = Path(raw_dir) / f"ch{chapter}"
    chapter_dir.mkdir(parents=True, exist_ok=True)
    target = chapter_dir / f"{stamp}_{_slug_from_url(url)}"
    target.write_bytes(body)
    return target
