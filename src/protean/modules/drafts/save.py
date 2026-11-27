"""Save a draft as a family: check it completely, then promote it into families/<name>/.

A stream (stages schema, agents, workspace, promote, then `done` or `error`). The draft is
checked the same way an import is, plus the workspace check. Promoting copies exactly what
family.json lists, bumps the version if the family changed, swaps the folder in, and deletes the
draft. A draft that fails stays as it is, so nothing is lost.
"""

import shutil
import uuid
from collections.abc import AsyncGenerator

from protean import config
from protean.core.errors import INTERNAL, INVALID_FAMILY, NOT_FOUND, AppError
from protean.core.sse import Event
from protean.core.storage import read_json
from protean.modules.families import values, version
from protean.modules.families.files import (
    copy_family,
    differs,
    family_json,
    replace_folder,
)
from protean.modules.families.schemas import read_family, walk_agents
from protean.modules.families.validation import integrity, workspace
from protean.modules.families.validation.stream import Checked, validate


def _size(folder) -> int:
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())


def _saved_version(saved) -> str | None:
    """The version of the saved family, or None when there is none (or it cannot be read)."""
    try:
        return read_family(saved).family_version
    except AppError:
        return None


def _promote(name: str, kind: version.Bump) -> dict:
    """Copy the draft into families/. Synchronous with no awaits, like every draft operation.

    The draft may have been edited since it was checked, so what is promoted is checked again.
    """
    draft, saved = config.DRAFTS_DIR / name, config.FAMILIES_DIR / name
    family = read_family(draft)
    missing = [
        path
        for agent in walk_agents(family.agents)
        for paths in integrity.check_agent(draft, agent).values()
        for path in paths
    ]
    if missing:
        raise AppError(
            422,
            INVALID_FAMILY,
            f"Files that family.json needs are missing: {', '.join(missing[:8])}",
        )
    before = _saved_version(saved)
    tmp = config.FAMILIES_DIR / f".{name}.{uuid.uuid4().hex}"
    try:
        copy_family(draft, tmp, family)
        changed = before is None or differs(tmp, saved)
        bumped = before is not None and changed
        if bumped:  # an edit of a saved family: its version goes up, from the saved one
            assert before is not None
            family = family.model_copy(
                update={"family_version": version.bump(before, kind)}
            )
            (tmp / "family.json").write_text(family_json(family), encoding="utf-8")
        if changed:
            replace_folder(saved, tmp)
        elif before is not None:
            family = family.model_copy(
                update={"family_version": before}
            )  # nothing to save
    except OSError as exc:
        reason = exc.strerror or type(exc).__name__
        raise AppError(500, INTERNAL, f"Could not save the family: {reason}.") from exc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)  # gone already when it was swapped in
    values.promote(name)  # values are settings: they follow every save, changed or not
    shutil.rmtree(draft, ignore_errors=True)
    return {
        "name": name,
        "familyVersion": family.family_version,
        "bumped": bumped,
        "changed": changed,
    }


async def save(name: str, kind: version.Bump) -> AsyncGenerator[Event]:
    draft = config.DRAFTS_DIR / name
    if not (draft / "family.json").is_file():
        raise AppError(404, NOT_FOUND, f"There is no draft named “{name}”.")
    stage = ""
    try:
        checked = Checked()
        async for event, data in validate(draft, checked):
            if event == "stage" and data["state"] == "running":
                stage = data["id"]
            yield event, data

        stage = "keys"
        yield "stage", {"id": stage, "state": "running"}
        lacking = values.missing("draft", name, read_json(draft / "family.json") or {})
        if lacking:
            raise AppError(
                422,
                INVALID_FAMILY,
                "These values are not set: "
                + "; ".join(lacking)
                + ". Set them on the agent’s MCPs or Skills tab, or remove the names you don’t need.",
            )
        yield "stage", {"id": stage, "state": "done"}

        stage = "workspace"
        yield "stage", {"id": stage, "state": "running"}
        config.FAMILIES_DIR.mkdir(parents=True, exist_ok=True)
        workspace.check_space(config.FAMILIES_DIR, _size(draft))
        yield "stage", {"id": stage, "state": "done"}

        stage = "promote"
        yield "stage", {"id": stage, "state": "running"}
        result = _promote(name, kind)
        note = (
            "no changes"
            if not result["changed"]
            else f"version {result['familyVersion']}"
        )
        yield "stage", {"id": stage, "state": "done", "note": note}
        yield "done", result
    except AppError:
        if stage:
            yield "stage", {"id": stage, "state": "error"}
        raise
