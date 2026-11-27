"""Show a family, draft, skill or MCP server folder in the system file manager.

The server runs on the user's own machine, so it can open the folder for them. The path is built
from validated names under the workspace and must already exist; the client never sends a path.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from protean import config
from protean.core.errors import INTERNAL, NOT_FOUND, AppError


def folder(
    scope: str, name: str, kind: str | None, agent_id: str | None, item_id: str | None
) -> Path:
    base = (config.FAMILIES_DIR if scope == "family" else config.DRAFTS_DIR) / name
    path = base / kind / agent_id / item_id if kind and agent_id and item_id else base
    if not path.is_dir():
        raise AppError(404, NOT_FOUND, "That folder does not exist on this device yet.")
    return path


def open_folder(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)
        return
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    if not shutil.which(opener):
        raise AppError(
            500, INTERNAL, f"This device has no “{opener}” to open folders with."
        )
    try:
        subprocess.run([opener, str(path)], check=True, timeout=10, capture_output=True)
    except (subprocess.SubprocessError, OSError) as e:
        raise AppError(500, INTERNAL, f"Could not open the folder: {e}") from e
