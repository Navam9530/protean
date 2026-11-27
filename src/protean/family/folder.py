"""Family folders on disk. families/<name>/ and drafts/<name>/ share one layout:

    family.json
    prompts/<agent-id>.md
    skills/<agent-id>/<skill-id>/...
    mcps/<agent-id>/<mcp-id>/...        (harness-managed MCP servers only)
    LICENSE*, README*                   (kept as they are)

Names are <owner>_<repo>. Only names made of these parts ever reach the file system.
"""

import filecmp
import json
import shutil
import uuid
from pathlib import Path
from typing import Literal

from protean.core.errors import INTERNAL, AppError
from protean.family.schemas import Family, walk_agents

EXTRA_FILES = ("LICENSE", "LICENCE", "COPYING", "README")

Kind = Literal[
    "skills", "mcps"
]  # what a folder under an agent holds: skills/<agent>/<id>/


def read_prompts(folder: Path) -> dict[str, str]:
    """Every prompts/<agent-id>.md in the folder, by agent id."""
    return {
        p.stem: p.read_text(encoding="utf-8", errors="replace")
        for p in sorted((folder / "prompts").glob("*.md"))
    }


def family_json(family: Family) -> str:
    return json.dumps(
        family.model_dump(by_alias=True, exclude_none=True, mode="json"), indent=2
    )


def copy_family(src: Path, dst: Path, family: Family) -> None:
    """Copy what `family` lists, plus LICENSE and README, from `src` into the new folder `dst`.

    family.json is written from `family` itself (so the caller can set the name); anything in
    `src` that family.json does not list is left behind. Listed files that are missing are
    skipped: checking that they exist is the integrity check's job.
    """
    dst.mkdir(parents=True)
    (dst / "family.json").write_text(family_json(family), encoding="utf-8")
    for agent in walk_agents(family.agents):
        prompt = src / "prompts" / f"{agent.id}.md"
        if prompt.is_file():
            (dst / "prompts").mkdir(exist_ok=True)
            shutil.copy2(prompt, dst / "prompts" / prompt.name)
        listed = [("skills", skill.id) for skill in agent.skills] + [
            ("mcps", mcp.id) for mcp in agent.mcps if mcp.managed_by == "harness"
        ]
        for kind, item in listed:
            item_dir = src / kind / agent.id / item
            if item_dir.is_dir():
                shutil.copytree(item_dir, dst / kind / agent.id / item, symlinks=True)
    for entry in src.iterdir():
        if entry.is_file() and entry.name.upper().startswith(EXTRA_FILES):
            shutil.copy2(entry, dst / entry.name)


def build_folder(final: Path, fill) -> None:
    """Create `final` by filling a hidden temp folder and renaming it, so it is never half-made."""
    tmp = final.parent / f".{final.name}.{uuid.uuid4().hex}"
    try:
        fill(tmp)
        tmp.rename(final)
    except BaseException as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        if isinstance(exc, OSError):  # full disk, permissions, ...
            reason = exc.strerror or type(exc).__name__
            raise AppError(
                500, INTERNAL, f"Could not write the family folder: {reason}."
            ) from exc
        raise


def _files(folder: Path) -> list[Path]:
    return sorted(p.relative_to(folder) for p in folder.rglob("*") if p.is_file())


def differs(new: Path, old: Path) -> bool:
    """Whether two family folders differ in any file. family.json is compared without its
    version, because a changed version is the result of a save, not an edit."""
    names = _files(new)
    if names != _files(old):
        return True
    for name in names:
        if name.as_posix() == "family.json":
            a, b = (json.loads((f / name).read_text("utf-8")) for f in (new, old))
            a.pop("familyVersion", None)
            b.pop("familyVersion", None)
            if a != b:
                return True
        elif not filecmp.cmp(new / name, old / name, shallow=False):
            return True
    return False


def replace_folder(final: Path, new: Path) -> None:
    """Put the finished folder `new` in place of `final`, so `final` is never half-written:
    the old one is moved aside first and put back if the swap fails."""
    aside = final.parent / f".{final.name}.old.{uuid.uuid4().hex}"
    if final.exists():
        final.rename(aside)
    try:
        new.rename(final)
    except BaseException:
        if aside.exists():
            aside.rename(final)
        raise
    shutil.rmtree(aside, ignore_errors=True)
