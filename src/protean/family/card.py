"""What a family card on the home screen shows. A saved family and a draft show the same things,
so both lists build their cards here."""

from pathlib import Path
from typing import Any

from protean.core.schemas import CamelModel
from protean.family.validation.safety import kept


class CardFields(CamelModel):
    """What a family or draft card shows. Times are ms since the epoch."""

    name: str
    family: dict[str, Any]  # family.json, for the minimap
    description: str  # the root agent's
    family_version: str
    agent_count: int
    size: int  # bytes the family keeps when saved
    chat_count: int  # phase 2
    updated_at: int  # modified
    accessed_at: int  # phase 2: for now the same as updated_at


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
