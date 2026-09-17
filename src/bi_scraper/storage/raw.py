# OWNERSHIP: tooling
"""Raw HTML snapshot writer: ``data/raw/{chapter}/``."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug_from_url(url: str, default_suffix: str = ".html") -> str:
    path = urlparse(url).path
    name = path.rstrip("/").rsplit("/", 1)[-1] or "index"
    if default_suffix and not name.lower().endswith(default_suffix.lower()):
        name = f"{name}{default_suffix}"
    return _SAFE_RE.sub("_", name)[:120] or f"index{default_suffix}"


def save_raw(
    raw_dir: Path,
    chapter: int,
    url: str,
    body: bytes,
    fetched_at: str | None = None,
    default_suffix: str = ".html",
    filename: str | None = None,
) -> Path:
    """Write a raw snapshot and return its path.

    ``filename`` overrides the slug derived from ``url`` (used for local
    file ingests); ``default_suffix`` controls the extension for
    extension-less URLs (``.pdf`` for PDF snapshots, ``.html`` otherwise).
    """

    stamp = (
        fetched_at
        or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ).replace(":", "").replace("-", "")
    chapter_dir = Path(raw_dir) / f"ch{chapter}"
    chapter_dir.mkdir(parents=True, exist_ok=True)
    if filename:
        safe_name = _SAFE_RE.sub("_", filename)[:120] or "file"
        target = chapter_dir / f"{stamp}_{safe_name}"
    else:
        target = chapter_dir / f"{stamp}_{_slug_from_url(url, default_suffix)}"
    target.write_bytes(body)
    return target
