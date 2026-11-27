"""Saved families, in families/<name>/. Written only by saving a draft (drafts/save.py); here
they are listed, read and deleted. Editing one means making a draft copy of it."""

import shutil
from pathlib import Path

from protean import config
from protean.core.errors import NOT_FOUND, AppError
from protean.core.storage import read_json
from protean.modules.families import published, values
from protean.modules.families.api_schemas import FamilyOut, FamilySummary
from protean.modules.families.validation.safety import kept


def _count_agents(agents: object) -> int:
    count, stack = 0, [agents]
    while stack:
        agent = stack.pop()
        if isinstance(agent, dict):
            count += 1
            stack += agent.get("sub-agents") or []
    return count


def _size(folder: Path, family: dict) -> int:
    """Bytes the family keeps: family.json, prompts, listed skills and MCP folders, LICENSE/README.
    A draft's removed items are not counted: they are dropped when it is saved."""
    files = [
        folder / "family.json",
        *folder.glob("prompts/*.md"),
        *kept(folder, family),
    ]
    return sum(p.stat().st_size for p in files if p.is_file())


def card_fields(folder: Path, family: dict, modified: int) -> dict:
    """What a family card and a draft card both show, from the folder, family.json and its
    modified time."""
    root = family.get("agents")
    root = root if isinstance(root, dict) else {}
    return {
        "name": folder.name,
        "family": family,
        "description": str(root.get("description", "")),
        "family_version": str(family.get("familyVersion", "")),
        "agent_count": _count_agents(root),
        "size": _size(folder, family),
        "chat_count": 0,  # phase 2
        "updated_at": modified,
        "accessed_at": modified,  # phase 2
    }


def list_families() -> list[FamilySummary]:
    out = []
    for folder in config.FAMILIES_DIR.iterdir():
        if folder.name.startswith(".") or not (folder / "family.json").is_file():
            continue  # a family that is being swapped in
        family = read_json(folder / "family.json") or {}
        out.append(
            FamilySummary(
                **card_fields(
                    folder, family, int((folder / "family.json").stat().st_mtime * 1000)
                ),
                published_family_version=published.version(folder.name),
                listed=published.listed(folder.name),
            )
        )
    return sorted(out, key=lambda f: f.updated_at, reverse=True)


def read(name: str) -> FamilyOut:
    folder = config.FAMILIES_DIR / name
    family = read_json(folder / "family.json")
    if family is None:
        raise AppError(404, NOT_FOUND, f"There is no family named “{name}”.")
    prompts = {
        p.stem: p.read_text(encoding="utf-8", errors="replace")
        for p in sorted((folder / "prompts").glob("*.md"))
    }
    return FamilyOut(
        name=name,
        family=family,
        prompts=prompts,
        secrets=values.read("family", name),
    )


def delete(name: str) -> None:
    """Delete the saved family from this machine. Fine when it is already gone. A draft of the
    same name is left alone (it becomes a family that has never been saved)."""
    shutil.rmtree(config.FAMILIES_DIR / name, ignore_errors=True)
    values.delete("family", name)
    published.forget(name)
