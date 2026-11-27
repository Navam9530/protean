"""A saved family as a zip, for sharing without GitHub. The zip has one top folder named after
the family, like a GitHub zipball, so it unpacks into a folder of its own."""

import os
import tempfile
import zipfile
from pathlib import Path

from protean import config
from protean.core.errors import NOT_FOUND, AppError


def build(name: str) -> Path:
    """Zip the whole saved family folder into a temporary file; the caller deletes it."""
    folder = config.FAMILIES_DIR / name
    if not (folder / "family.json").is_file():
        raise AppError(404, NOT_FOUND, f"There is no family named “{name}”.")
    fd, tmp = tempfile.mkstemp(prefix="protean-export-", suffix=".zip")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(folder.rglob("*")):
                if p.is_file() and not p.is_symlink():
                    z.write(p, f"{name}/{p.relative_to(folder).as_posix()}")
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return Path(tmp)
