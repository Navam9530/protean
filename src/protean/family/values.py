"""The values of MCP client headers and server environment variables, and of skill environment
variables.

family.json lists only the names. The values are in keys/<drafts|families>/<family-name>/, in the
layout of the family folder: `mcps/<agent-id>/<mcp-id>.json` holds
`{"clientHeaders": {...}, "serverEnv": {...}}` and `skills/<agent-id>/<skill-id>.json` holds
`{NAME: value, ...}`. The files are owner-only and outside the family and draft folders, so
publishing and exporting can never carry them.

A draft and the saved family of the same name each have their own values, so editing a draft
never changes what the saved family uses. Opening a saved family for editing copies its values
into the draft (`fork`); saving the draft replaces the family's values with the draft's
(`promote`).
"""

import shutil
import uuid
from pathlib import Path
from typing import Literal

from pydantic import Field

from protean import config
from protean.core.schemas import CamelModel
from protean.core.storage import read_json, write_json_atomic


class McpValues(CamelModel):
    """The values of one MCP server's client headers and environment variables, by name."""

    client_headers: dict[str, str] = Field(default_factory=dict)
    server_env: dict[str, str] = Field(default_factory=dict)


class Secrets(CamelModel):
    """Every value of a family: by agent id, then MCP id or skill id. A skill's values are its
    environment variables, name -> value."""

    mcps: dict[str, dict[str, McpValues]] = Field(default_factory=dict)
    skills: dict[str, dict[str, dict[str, str]]] = Field(default_factory=dict)


Scope = Literal["draft", "family"]
McpNames = dict[
    tuple[str, str], tuple[list[str], list[str]]
]  # (agent, mcp) -> (headers, env)
SkillNames = dict[tuple[str, str], list[str]]  # (agent, skill) -> env


def _folder(scope: Scope, name: str) -> Path:
    return config.KEYS_DIR / ("drafts" if scope == "draft" else "families") / name


def listed(family: dict) -> tuple[McpNames, SkillNames]:
    """The names family.json lists, for every MCP server and skill that lists any."""
    mcps: McpNames = {}
    skills: SkillNames = {}
    stack = [family.get("agents")]
    while stack:
        agent = stack.pop()
        if not isinstance(agent, dict):
            continue
        for mcp in agent.get("mcps") or []:
            if not isinstance(mcp, dict):
                continue
            headers = [n for n in mcp.get("clientHeaders") or [] if n]
            env = [n for n in mcp.get("serverEnv") or [] if n]
            if headers or env:
                mcps[(agent["id"], mcp["id"])] = (headers, env)
        for skill in agent.get("skills") or []:
            env = (
                [n for n in skill.get("env") or [] if n]
                if isinstance(skill, dict)
                else []
            )
            if env:
                skills[(agent["id"], skill["id"])] = env
        stack += agent.get("sub-agents") or []
    return mcps, skills


def read(scope: Scope, name: str) -> Secrets:
    out = Secrets()
    root = _folder(scope, name)
    for path in sorted((root / "mcps").glob("*/*.json")):
        data = read_json(path) or {}
        out.mcps.setdefault(path.parent.name, {})[path.stem] = McpValues.model_validate(
            data
        )
    for path in sorted((root / "skills").glob("*/*.json")):
        data = read_json(path) or {}
        out.skills.setdefault(path.parent.name, {})[path.stem] = {
            k: v for k, v in data.items() if isinstance(v, str)
        }
    return out


def _given(values: dict[str, str], names: list[str]) -> dict[str, str]:
    """The values for `names`; one that is empty counts as not set."""
    return {n: values[n] for n in names if values.get(n)}


def write(scope: Scope, name: str, family: dict, secrets: Secrets) -> None:
    """Make the keys folder match `secrets`, for the names `family` lists. Files of removed MCPs,
    skills and names are deleted."""
    root = _folder(scope, name)
    wanted: dict[Path, dict] = {}
    mcps, skills = listed(family)
    for (agent_id, mcp_id), (headers, env) in mcps.items():
        given = secrets.mcps.get(agent_id, {}).get(mcp_id, McpValues())
        data = {
            "clientHeaders": _given(given.client_headers, headers),
            "serverEnv": _given(given.server_env, env),
        }
        if data["clientHeaders"] or data["serverEnv"]:
            wanted[root / "mcps" / agent_id / f"{mcp_id}.json"] = data
    for (agent_id, skill_id), env in skills.items():
        data = _given(secrets.skills.get(agent_id, {}).get(skill_id, {}), env)
        if data:
            wanted[root / "skills" / agent_id / f"{skill_id}.json"] = data
    for path in [*root.glob("mcps/*/*.json"), *root.glob("skills/*/*.json")]:
        if path not in wanted:
            path.unlink()
    for path, data in wanted.items():
        if read_json(path) != data:
            write_json_atomic(path, data)
    _prune(root)


def _prune(root: Path) -> None:
    """Remove the folders that have no value files left."""
    if not root.is_dir():
        return
    for folder in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
        if not any(folder.iterdir()):
            folder.rmdir()
    if not any(root.iterdir()):
        root.rmdir()


def missing(scope: Scope, name: str, family: dict) -> list[str]:
    """What a family needs a value for and has none: "agent / MCP id: Name, Name"."""
    have = read(scope, name)
    mcps, skills = listed(family)
    out = []
    for (agent_id, mcp_id), (headers, env) in mcps.items():
        values = have.mcps.get(agent_id, {}).get(mcp_id, McpValues())
        lacking = [n for n in headers if not values.client_headers.get(n)]
        lacking += [n for n in env if not values.server_env.get(n)]
        if lacking:
            out.append(f"{agent_id} / MCP {mcp_id}: {', '.join(lacking)}")
    for (agent_id, skill_id), env in skills.items():
        values = have.skills.get(agent_id, {}).get(skill_id, {})
        if lacking := [n for n in env if not values.get(n)]:
            out.append(f"{agent_id} / skill {skill_id}: {', '.join(lacking)}")
    return out


def delete(scope: Scope, name: str) -> None:
    shutil.rmtree(_folder(scope, name), ignore_errors=True)


def fork(name: str) -> None:
    """A new draft of a saved family starts with the family's values."""
    delete("draft", name)
    if _folder("family", name).is_dir():
        shutil.copytree(_folder("family", name), _folder("draft", name))


def promote(name: str) -> None:
    """Saving: the draft's values become the family's, and the draft's folder is gone."""
    src, dst = _folder("draft", name), _folder("family", name)
    if not src.is_dir():
        delete("family", name)
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    aside = dst.with_name(f".{name}.old.{uuid.uuid4().hex}")
    if dst.exists():
        dst.rename(aside)
    src.rename(dst)
    shutil.rmtree(aside, ignore_errors=True)
