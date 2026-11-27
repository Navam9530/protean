"""Workspace checks: whether this machine can take the change (not whether the family is valid)."""

import shutil
from pathlib import Path

from protean.core.errors import NO_SPACE, AppError

MARGIN = 10_000_000  # keep some room beyond the family itself


def check_space(where: Path, needed: int) -> None:
    """Raises NO_SPACE when `where` has less free disk than `needed` bytes (plus a margin)."""
    free = shutil.disk_usage(where).free
    if free < needed + MARGIN:
        raise AppError(
            507,
            NO_SPACE,
            f"Not enough free disk space: {needed // 1_000_000 + 1} MB is needed "
            f"and {free // 1_000_000} MB is free.",
        )
