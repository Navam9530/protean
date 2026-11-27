"""Safety checks for autosaved drafts. A draft may be incomplete, but it must never be able to
write outside its own folder, so ids (which become file and folder names) and sizes are checked.
Everything else waits for the full validation at save."""

from pathlib import Path
from typing import Any

from protean.core.errors import INVALID_DRAFT, AppError
from protean.family.folder import EXTRA_FILES
from protean.family.schemas import check_id
from protean.family.validation.limits import check_limits


def _bad(message: str) -> AppError:
    return AppError(422, INVALID_DRAFT, message)


def _check_id(value: Any, where: str) -> str:
    try:
        return check_id(value)
    except (TypeError, ValueError) as exc:
        raise _bad(f"{where}: ids use lowercase letters, digits and hyphens.") from exc


def kept(folder: Path, family: dict[str, Any]) -> list[Path]:
    """The files of skills and MCP servers that save would keep, plus LICENSE and README: what the
    family lists. Folders that are not listed (removed items) stay on disk until save and do not
    count. `family` must have passed the id checks."""
    dirs: list[Path] = []
    stack = [family.get("agents")]
    while stack:
        agent = stack.pop()
        if not isinstance(agent, dict):
            continue
        for skill in agent.get("skills") or []:
            dirs.append(folder / "skills" / agent["id"] / skill["id"])
        for mcp in agent.get("mcps") or []:
            if isinstance(mcp, dict) and mcp.get("managedBy") == "harness":
                dirs.append(folder / "mcps" / agent["id"] / mcp["id"])
        stack += agent.get("sub-agents") or []
    files = [p for d in dirs for p in d.rglob("*") if p.is_file()]
    if folder.is_dir():
        files += [
            p
            for p in folder.iterdir()
            if p.is_file() and p.name.upper().startswith(EXTRA_FILES)
        ]
    return files


def check_draft(
    folder: Path,
    family: dict[str, Any],
    prompts: dict[str, str],
    extra: tuple[int, int] = (0, 0),
) -> None:
    """Raises INVALID_DRAFT (or TOO_LARGE) when the document could not be stored safely.

    `extra` is the (file count, bytes) of files about to be added to the folder (a merge).
    """
    stack = [family.get("agents")]
    while stack:
        agent = stack.pop()
        if not isinstance(agent, dict):
            raise _bad("agents: each agent must be an object.")
        agent_id = _check_id(agent.get("id"), "agents.id")
        for skill in agent.get("skills") or []:
            _check_id(
                skill.get("id") if isinstance(skill, dict) else None,
                f"{agent_id}.skills",
            )
        for mcp in agent.get("mcps") or []:
            _check_id(
                mcp.get("id") if isinstance(mcp, dict) else None, f"{agent_id}.mcps"
            )
        stack += agent.get("sub-agents") or []
    for agent_id in prompts:
        _check_id(agent_id, "prompts")

    # The size limits apply to what the family keeps as it will be after this write.
    files = kept(folder, family)
    size = sum(p.stat().st_size for p in files)
    size += len(repr(family).encode()) + sum(len(t.encode()) for t in prompts.values())
    check_limits(len(files) + 1 + len(prompts) + extra[0], size + extra[1])
