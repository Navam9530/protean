"""Integrity checks: a family folder must contain everything its family.json lists.

family.json is the single source of truth. Each check returns what is wrong and leaves it to
the caller to raise or to report it, so a stream can show every problem instead of the first.
"""

from collections.abc import Iterable
from pathlib import Path

from protean.modules.families.schemas import Agent, Family, walk_agents


def folder_paths(folder: Path) -> list[str]:
    """Every file under `folder`, as paths relative to it ("prompts/lead.md")."""
    return [p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()]


def expected_files(paths: Iterable[str]) -> dict[str, bool]:
    """Which of the files a family repo should have are present, given its file paths.

    One definition for the marketplace detail view (paths from the GitHub tree) and for an
    imported folder (paths from disk). LICENSE and README are looked for at the root only.
    """
    paths = list(paths)
    root = [p for p in paths if "/" not in p]
    return {
        "family_json": "family.json" in paths,
        "license": any(
            f.upper().startswith(("LICENSE", "LICENCE", "COPYING")) for f in root
        ),
        "readme": any(f.upper().startswith("README") for f in root),
        "prompts": any(p.startswith("prompts/") for p in paths),
    }


def missing_extras(has: dict[str, bool]) -> list[str]:
    """Warnings for the files that are nice to have: a LICENSE and a README."""
    warnings = []
    if not has["license"]:
        warnings.append(
            "No LICENSE file: the terms for reusing this family are unclear."
        )
    if not has["readme"]:
        warnings.append(
            "No README file: there is no description of what this family does."
        )
    return warnings


def check_agent(folder: Path, agent: Agent) -> dict[str, list[str]]:
    """Missing files for one agent, by check: {"prompt": [...], "skills": [...], "mcps": [...]}."""
    prompt = f"prompts/{agent.id}.md"
    return {
        "prompt": [] if (folder / prompt).is_file() else [prompt],
        "skills": [
            f"skills/{agent.id}/{skill.id}/"
            for skill in agent.skills
            if not (folder / "skills" / agent.id / skill.id).is_dir()
        ],
        "mcps": [
            f"mcps/{agent.id}/{mcp.id}/"
            for mcp in agent.mcps
            if mcp.managed_by == "harness"
            and not (folder / "mcps" / agent.id / mcp.id).is_dir()
        ],
    }


def read_prompts(folder: Path, family: Family) -> dict[str, str]:
    """Each agent's prompt text by agent id. Call after check_agent found no missing prompt."""
    return {
        agent.id: (folder / "prompts" / f"{agent.id}.md").read_text(
            encoding="utf-8", errors="replace"
        )
        for agent in walk_agents(family.agents)
    }


def ignored(folder: Path, family: Family) -> list[str]:
    """Warnings for files that no entry in family.json refers to. They are left out when saving."""
    agents = {a.id: a for a in walk_agents(family.agents)}
    extra: list[str] = []
    if (folder / "prompts").is_dir():
        extra += [
            f"prompts/{f.name}"
            for f in sorted((folder / "prompts").iterdir())
            if f.name.removesuffix(".md") not in agents or not f.name.endswith(".md")
        ]
    for kind in ("skills", "mcps"):
        if not (folder / kind).is_dir():
            continue
        for agent_dir in sorted(p for p in (folder / kind).iterdir() if p.is_dir()):
            agent = agents.get(agent_dir.name)
            if agent is None:
                extra.append(f"{kind}/{agent_dir.name}/")
                continue
            listed = (
                {s.id for s in agent.skills}
                if kind == "skills"
                else {m.id for m in agent.mcps}
            )
            extra += [
                f"{kind}/{agent_dir.name}/{c.name}/"
                for c in sorted(agent_dir.iterdir())
                if c.name not in listed
            ]
    return [f"Ignored, not listed in family.json: {path}" for path in extra]
