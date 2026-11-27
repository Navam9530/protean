"""Workspace folders and small JSON file helpers (atomic writes, owner-only permissions)."""

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from protean import config
from protean.core.errors import CORRUPT_FILE, AppError


def ensure_workspace() -> None:
    config.HOME.mkdir(parents=True, exist_ok=True)
    config.FAMILIES_DIR.mkdir(exist_ok=True)
    config.IMPORTS_DIR.mkdir(exist_ok=True)
    config.DRAFTS_DIR.mkdir(exist_ok=True)
    config.KEYS_DIR.mkdir(mode=0o700, exist_ok=True)
    config.KEYS_DIR.chmod(0o700)  # enforce even if it already existed


def read_json(path: Path) -> dict[str, Any] | None:
    """Return the parsed file, or None if it does not exist."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AppError(
            500, CORRUPT_FILE, f"{path.name} is not valid JSON; fix or delete it."
        ) from exc
    if not isinstance(data, dict):
        raise AppError(500, CORRUPT_FILE, f"{path.name} must contain a JSON object.")
    return data


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    """Write JSON via a temp file + rename, so readers never see a partial file. Mode 0600."""
    write_text_atomic(path, json.dumps(data, indent=2))


def write_text_atomic(path: Path, text: str) -> None:
    """Write via a temp file + rename, so readers never see a partial file. Result is mode 0600."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=path.parent, prefix=f"{path.name}.", suffix=".tmp"
    )  # created 0600
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
