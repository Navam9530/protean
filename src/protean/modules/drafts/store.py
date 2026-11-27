"""Drafts: families being built, in drafts/<name>/. Autosaved, possibly incomplete, never deleted
automatically. Everything here is synchronous with no awaits, so on the event loop each call runs
to completion before the next starts and needs no locks."""

import shutil
from pathlib import Path

from protean import config
from protean.core.errors import ALREADY_EXISTS, CONFLICT, NOT_FOUND, AppError
from protean.core.storage import read_json, write_json_atomic, write_text_atomic
from protean.family import values
from protean.family.card import card_fields
from protean.family.folder import (
    build_folder,
    copy_family,
    family_json,
    read_prompts,
)
from protean.family.schemas import Agent, Family, read_family
from protean.family.validation import safety
from protean.identity import profile
from protean.modules.drafts.schemas import (
    Blank,
    DraftDoc,
    DraftEdit,
    DraftOut,
    DraftSource,
    DraftSummary,
    FromFamily,
    FromImport,
)


def _folder(name: str) -> Path:
    return config.DRAFTS_DIR / name


def _updated_at(folder: Path) -> int:
    """When the draft document last changed: its newest file (family.json or a prompt)."""
    files = [folder / "family.json", *(folder / "prompts").glob("*.md")]
    newest = max(p.stat().st_mtime_ns for p in files)
    return newest // 1_000_000


def _ensure_free(name: str) -> None:
    if _folder(name).exists() or (config.FAMILIES_DIR / name).exists():
        raise AppError(
            409, ALREADY_EXISTS, f"A family or draft named “{name}” already exists."
        )


def _blank() -> Family:
    root = Agent(
        id="lead",
        name="lead",
        description="Coordinates the family and delegates work to sub-agents.",
    )
    return Family(
        schema_url=config.SCHEMA_URL,
        schema_version=config.SCHEMA_VERSION,
        family_version="0.1.0",
        agents=root,
    )


def _write_blank(folder: Path, family: Family) -> None:
    folder.mkdir()
    (folder / "family.json").write_text(family_json(family), encoding="utf-8")


def list_drafts() -> list[DraftSummary]:
    out = []
    for folder in config.DRAFTS_DIR.iterdir():
        if folder.name.startswith(".") or not (folder / "family.json").is_file():
            continue  # a draft that is still being built
        family = read_json(folder / "family.json") or {}
        out.append(
            DraftSummary(
                **card_fields(folder, family, _updated_at(folder)),
                editing=(config.FAMILIES_DIR / folder.name).is_dir(),
            )
        )
    return sorted(out, key=lambda d: d.updated_at, reverse=True)


def read(name: str) -> DraftOut:
    folder = _folder(name)
    family = read_json(folder / "family.json")
    if family is None:
        raise AppError(404, NOT_FOUND, f"There is no draft named “{name}”.")
    prompts = read_prompts(folder)
    return DraftOut(
        name=name,
        family=family,
        prompts=prompts,
        secrets=values.read("draft", name),
        updated_at=_updated_at(folder),
    )


def _forget_values(name: str) -> None:
    """A new family starts without values: any left under its name are from an earlier one."""
    values.delete("draft", name)
    values.delete("family", name)


def create(source: DraftSource) -> tuple[DraftOut, bool]:
    """Returns the draft and whether it was made now (False: an edit copy already existed)."""
    match source:
        case Blank():
            name = f"{profile.get().owner}_{source.repo}"
            _ensure_free(name)
            _forget_values(name)
            family = _blank()
            build_folder(_folder(name), lambda tmp: _write_blank(tmp, family))
        case FromFamily():
            name = source.name
            saved = config.FAMILIES_DIR / name
            if not (saved / "family.json").is_file():
                raise AppError(404, NOT_FOUND, f"There is no family named “{name}”.")
            if _folder(name).exists():
                return read(name), False  # keep working on the existing edit
            family = read_family(saved)
            build_folder(_folder(name), lambda tmp: copy_family(saved, tmp, family))
            values.fork(name)
        case FromImport():
            name = f"{source.owner}_{source.repo}"
            imported = config.IMPORTS_DIR / source.import_id
            if not (imported / "family.json").is_file():
                raise AppError(404, NOT_FOUND, "That import is no longer available.")
            _ensure_free(name)
            _forget_values(name)
            # The name comes from the repo, never from the file: the file's name is replaced.
            family = read_family(imported)
            build_folder(_folder(name), lambda tmp: copy_family(imported, tmp, family))
            shutil.rmtree(imported, ignore_errors=True)
    return read(name), True


def write(name: str, doc: DraftEdit) -> int:
    """Autosave: replace family.json and the prompts, writing only what changed.

    Skills and MCP folders are left alone: they come in through their own uploads.
    """
    folder = _folder(name)
    if not (folder / "family.json").is_file():
        raise AppError(404, NOT_FOUND, f"There is no draft named “{name}”.")
    if doc.base_updated_at is not None and doc.base_updated_at != _updated_at(folder):
        raise AppError(
            409, CONFLICT, "This draft was changed elsewhere. Reload it to continue."
        )
    safety.check_draft(folder, doc.family, doc.prompts)
    updated = write_files(folder, doc)
    if doc.secrets is not None:
        values.write("draft", name, doc.family, doc.secrets)
    return updated


def write_files(folder: Path, doc: DraftDoc) -> int:
    """Write the document into the draft folder, only what changed. Checks nothing: the caller
    has already checked it (autosave in `write`, a merge on its own)."""
    prompts_dir = folder / "prompts"
    for agent_id, text in doc.prompts.items():
        path = prompts_dir / f"{agent_id}.md"
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            write_text_atomic(path, text)
    for old in prompts_dir.glob("*.md") if prompts_dir.is_dir() else []:
        if old.stem not in doc.prompts:
            old.unlink()
    if read_json(folder / "family.json") != doc.family:
        write_json_atomic(folder / "family.json", doc.family)
    return _updated_at(folder)


def discard(name: str) -> None:
    """Delete a draft. Fine when it is already gone. A saved family of the same name is untouched."""
    shutil.rmtree(_folder(name), ignore_errors=True)
    values.delete("draft", name)
