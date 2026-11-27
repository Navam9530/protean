"""The schema and agents checks of a family folder, as a stream of events.

Shared by importing (a downloaded or uploaded folder) and saving (a draft), so both show the
same stages, per-agent progress and warnings. Fails with an AppError after reporting everything.
"""

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from pathlib import Path

from protean.core.errors import INVALID_FAMILY, AppError
from protean.core.sse import Event
from protean.family.schemas import Family, read_family, walk_agents
from protean.family.validation import integrity


@dataclass
class Checked:
    """What `validate` found out, for the caller to use once the stream is over."""

    family: Family | None = None
    warnings: list[str] = field(default_factory=list)


async def validate(folder: Path, checked: Checked) -> AsyncGenerator[Event]:
    """Stages `schema` and `agents`."""
    stage = "schema"
    yield "stage", {"id": stage, "state": "running"}
    family = read_family(folder)
    checked.family = family
    warnings = checked.warnings
    for message in integrity.missing_extras(
        integrity.expected_files(integrity.folder_paths(folder))
    ):
        warnings.append(message)
        yield "warning", {"message": message}
    tree = family.agents.model_dump(by_alias=True, exclude_none=True, mode="json")
    yield "tree", {"agents": tree}
    state = "warning" if warnings else "done"
    yield (
        "stage",
        {"id": stage, "state": state, "note": f"version {family.family_version}"},
    )

    stage = "agents"
    yield "stage", {"id": stage, "state": "running"}
    missing: list[str] = []
    for agent in walk_agents(family.agents):
        yield "agent", {"id": agent.id, "state": "running"}
        problems: list[str] = []
        for check, paths in integrity.check_agent(folder, agent).items():
            result = {"id": agent.id, "check": check}
            if paths:
                result |= {"state": "error", "message": ", ".join(paths)}
            else:
                result["state"] = "ok"
            yield "check", result
            problems += paths
        if problems:
            state = {"state": "error", "message": f"Missing: {', '.join(problems)}"}
        else:
            state = {"state": "ok"}
        yield "agent", {"id": agent.id, **state}
        missing += problems
    if missing:
        shown = "; ".join(missing[:8]) + (" …" if len(missing) > 8 else "")
        raise AppError(
            422, INVALID_FAMILY, f"Files that family.json needs are missing: {shown}"
        )
    ignored = integrity.ignored(folder, family)
    for message in ignored:
        yield "warning", {"message": message}
    warnings += ignored
    end = {"id": stage, "state": "warning" if ignored else "done"}
    if ignored:
        end["note"] = f"{len(ignored)} warnings"
    yield "stage", end
