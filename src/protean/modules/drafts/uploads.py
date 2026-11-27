"""Skills and MCP servers uploaded into a draft: one folder per item, at
drafts/<name>/<skills|mcps>/<agent-id>/<item-id>/.

Protean does not help write them; the user uploads a finished folder. An upload only writes
files. Listing the item in family.json is the UI's autosave, so a folder can exist for an item
that is not listed yet (it is left out when saved).
"""

import shutil
import uuid
from pathlib import Path
from typing import BinaryIO

from protean import config
from protean.core.errors import INVALID_DRAFT, NOT_FOUND, TOO_LARGE, AppError
from protean.core.storage import read_json
from protean.family.folder import Kind
from protean.family.validation import archive, safety


def _draft(name: str) -> Path:
    folder = config.DRAFTS_DIR / name
    if not (folder / "family.json").is_file():
        raise AppError(404, NOT_FOUND, f"There is no draft named “{name}”.")
    return folder


def _check_disk_cap(folder: Path, dest: Path) -> None:
    """Removed items stay in the draft until it is saved, so bound everything on disk."""
    every = [
        p
        for p in folder.rglob("*")
        if p.is_file() and not p.is_relative_to(dest) and not p.name.startswith(".")
    ]
    cap = config.DRAFT_DISK_FACTOR
    if (
        len(every) >= config.MAX_FILES * cap
        or sum(p.stat().st_size for p in every) >= config.MAX_UNZIPPED_BYTES * cap
    ):
        raise AppError(
            413,
            TOO_LARGE,
            "This draft holds too many removed items. Save it to clear them.",
        )


def put(
    name: str,
    agent_id: str,
    kind: Kind,
    item_id: str,
    files: list[tuple[str, BinaryIO]],
) -> int:
    """Store the uploaded folder as the item, replacing any earlier one. Returns the file count."""
    folder = _draft(name)
    dest = folder / kind / agent_id / item_id
    # The limits cover what the family keeps, except what is replaced. Removed items are not
    # listed any more: they stay on disk (so an undo can bring them back) and do not count.
    documents = [folder / "family.json", *(folder / "prompts").glob("*.md")]
    others = [
        p
        for p in [
            *safety.kept(folder, read_json(folder / "family.json") or {}),
            *documents,
        ]
        if p.is_file() and not p.is_relative_to(dest)
    ]
    already = (len(others), sum(p.stat().st_size for p in others))
    _check_disk_cap(folder, dest)
    tmp = dest.parent / f".{item_id}.{uuid.uuid4().hex}"
    try:
        count = archive.store_files(tmp, files, already) if files else 0
        if count == 0:
            raise AppError(422, INVALID_DRAFT, "The folder has no files.")
        if kind == "skills" and not (tmp / "SKILL.md").is_file():
            raise AppError(
                422, INVALID_DRAFT, "A skill folder needs a SKILL.md at its top."
            )
        shutil.rmtree(dest, ignore_errors=True)
        tmp.rename(dest)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return count
