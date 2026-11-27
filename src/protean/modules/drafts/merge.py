"""Add an import to a draft, under the agent the user chose (`parentId`). Two ways:

append: the import's root becomes a new sub-agent of `parentId`, with its whole tree below it.
Nothing is combined, so nothing can clash.

merge: the import's root is merged into `parentId` itself (which keeps its id and place), and
the rest of the import's tree is added below it. The ids of the two need not match. Anything the
import adds without clashing is added by itself. What clashes is reported, and the user settles
each item: fields (keep the old, take the new, or write your own), and skills or MCP servers
with the same id (drop the imported one, or keep both under another id).

Either way, an added agent keeps its id unless the draft already uses it; then it gets a free
one ("lead-2"), and its prompt, skills and MCP folders follow it.
"""

import filecmp
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from protean import config
from protean.core.errors import (
    INTERNAL,
    INVALID_DRAFT,
    INVALID_REQUEST,
    NOT_FOUND,
    UNRESOLVED,
    AppError,
)
from protean.modules.drafts import store
from protean.modules.drafts.schemas import (
    AgentConflict,
    AgentResolution,
    Alias,
    DraftDoc,
    DraftOut,
    FieldConflict,
    MergePreview,
    MergeRequest,
    MergeTarget,
)
from protean.modules.families.schemas import read_family
from protean.modules.families.validation import integrity, safety

FIELDS = (
    "name",
    "description",
    "model",
)  # agent fields that can clash (the prompt is separate)


@dataclass
class _Merge:
    """What one merge works on. `family` and `prompts` are edited in place."""

    # Inputs
    draft_dir: Path  # drafts/<name>/
    import_dir: Path  # imports/<importId>/
    family: dict[str, Any]  # the draft's family.json; the merge edits it
    prompts: dict[str, str]  # the draft's prompts by agent id; the merge edits them
    import_prompts: dict[str, str]  # the import's prompts by (imported) agent id
    resolutions: dict[str, AgentResolution]  # the user's answers, by draft agent id
    agents: dict[str, dict[str, Any]]  # every agent in `family` by id
    merge_root: (
        str | None
    )  # merge mode: the import's root id, which merges into the parent
    # imported id -> the id it gets in the draft, only where the draft already uses the id
    renames: dict[str, str]

    # Results, filled in while walking the import
    copies: list[tuple[Path, Path]] = field(
        default_factory=list
    )  # (from import, to draft)
    added: list[str] = field(default_factory=list)  # ids of agents that were added
    merged: list[str] = field(default_factory=list)  # ids of draft agents merged into
    conflicts: list[AgentConflict] = field(default_factory=list)  # still unanswered


def _agents(root: Any) -> dict[str, dict[str, Any]]:
    """Every agent in a tree of dicts by id. Raises if two share an id (the merge could not
    tell which one is meant). Autosave does not check that, so a draft can have the problem."""
    found, stack = {}, [root]
    while stack:
        agent = stack.pop()
        if isinstance(agent, dict):
            if agent.get("id") in found:
                raise AppError(
                    422,
                    INVALID_DRAFT,
                    f"Two agents in the draft share the id “{agent.get('id')}”. "
                    "Rename one before adding an import.",
                )
            found[agent.get("id")] = agent
            stack += agent.get("sub-agents") or []
    return found


def _same_folder(a: Path, b: Path) -> bool:
    """Whether two folders hold the same files with the same bytes."""
    names = sorted(p.relative_to(a) for p in a.rglob("*") if p.is_file())
    if names != sorted(p.relative_to(b) for p in b.rglob("*") if p.is_file()):
        return False
    return all(filecmp.cmp(a / n, b / n, shallow=False) for n in names)


def _blank(value: Any) -> bool:
    """Nothing there yet (a missing or empty field), so there is nothing to clash with."""
    return value is None or value == ""


def _decide(
    res: AgentResolution, conflict: AgentConflict, name: str, old: Any, new: Any
) -> Any:
    """The value to keep. A clash with no answer yet is recorded in `conflict`."""
    if _blank(new) or old == new:  # nothing to add, or both sides agree
        return old
    if _blank(old):  # the draft has nothing: take the import's, no question to ask
        return new
    choice = res.fields.get(name)
    if choice is None:
        conflict.fields.append(FieldConflict(field=name, old=old, new=new))
        return (
            old  # the preview shows the clash; the merge refuses until it is answered
        )
    if choice in ("old", "new"):
        return old if choice == "old" else new
    if name == "model":
        raise AppError(422, INVALID_REQUEST, "The model can only be kept or replaced.")
    return choice.custom  # the user's own text


def _alias(fix: Alias, taken: set[str], agent_id: str) -> str:
    """The id the user chose for the imported item, which must not be in use on the agent."""
    if fix.alias in taken:
        raise AppError(
            422,
            INVALID_REQUEST,
            f"“{fix.alias}” is already used on {agent_id}. Pick another id.",
        )
    return fix.alias


def _merge_lists(
    m: _Merge, old: dict, new: dict, res: AgentResolution, conflict: AgentConflict
) -> None:
    """Skills and MCP servers the import brings to an agent that already exists.

    `old` is the draft agent and `new` the imported one. Their folders are named after their own
    agent ids, so files are read from the import's id and written under the draft's id.
    """
    agent_id, source_id = old["id"], new["id"]
    skills = old.setdefault("skills", [])
    for entry in new.get("skills") or []:
        skill = entry["id"]
        src = m.import_dir / "skills" / source_id / skill
        dst = m.draft_dir / "skills" / agent_id / skill
        mine = next((e for e in skills if e.get("id") == skill), None)
        if mine is None:  # new to this agent: just add it
            skills.append(entry)
            m.copies.append((src, dst))
        elif not dst.is_dir() or _same_folder(src, dst):
            # The same skill. Its environment names are combined; a folder that was listed but
            # never uploaded is taken from the import.
            names = [*(mine.get("env") or []), *(entry.get("env") or [])]
            if names:
                mine["env"] = list(dict.fromkeys(names))
            if not dst.is_dir():
                m.copies.append((src, dst))
        else:  # same id, different files: the user decides
            fix = res.skills.get(skill)
            if fix is None:
                conflict.skills.append(skill)
            elif isinstance(fix, Alias):  # keep both; a drop needs nothing done
                alias = _alias(fix, {e["id"] for e in skills}, agent_id)
                skills.append({**entry, "id": alias})
                m.copies.append((src, m.draft_dir / "skills" / agent_id / alias))

    # MCP servers work the same way, but an entry is a settings object, not just an id, and only
    # harness-managed ones have a folder.
    mcps = old.setdefault("mcps", [])
    for entry in new.get("mcps") or []:
        mcp = entry["id"]
        harness = entry.get("managedBy") == "harness"
        src = m.import_dir / "mcps" / source_id / mcp
        dst = m.draft_dir / "mcps" / agent_id / mcp
        mine = next(
            (e for e in mcps if isinstance(e, dict) and e.get("id") == mcp), None
        )
        if mine is None:
            mcps.append(entry)
            if harness:
                m.copies.append((src, dst))
            continue
        # The same server if the settings and (when it has one) its folder are identical.
        same = {k: v for k, v in mine.items() if v is not None} == entry
        if same and (not harness or not dst.is_dir() or _same_folder(src, dst)):
            if harness and not dst.is_dir():
                m.copies.append((src, dst))
            continue
        fix = res.mcps.get(mcp)
        if fix is None:
            conflict.mcps.append(mcp)
        elif isinstance(fix, Alias):
            taken = {e.get("id") for e in mcps if isinstance(e, dict)}
            alias = _alias(fix, taken, agent_id)
            mcps.append({**entry, "id": alias})
            if harness:
                m.copies.append((src, m.draft_dir / "mcps" / agent_id / alias))


def _merge_into(m: _Merge, old: dict, new: dict) -> None:
    """Fold the imported agent `new` into the draft agent `old`. `old` keeps its id and place."""
    agent_id, source_id = old["id"], new["id"]
    res = m.resolutions.get(agent_id, AgentResolution())
    conflict = AgentConflict(agent_id=agent_id, imported_id=source_id)
    for name in FIELDS:
        value = _decide(res, conflict, name, old.get(name), new.get(name))
        if value is not None:  # do not add an empty `model` key to the draft agent
            old[name] = value
    prompt = _decide(
        res, conflict, "prompt", m.prompts.get(agent_id), m.import_prompts[source_id]
    )
    if prompt:
        m.prompts[agent_id] = prompt
    _merge_lists(m, old, new, res, conflict)
    m.merged.append(agent_id)
    # Only agents with something to settle are listed.
    if conflict.fields or conflict.skills or conflict.mcps:
        m.conflicts.append(conflict)


def _add(m: _Merge, new: dict, parent: dict) -> dict:
    """Add an agent that does not exist yet, as the last sub-agent of `parent`."""
    source_id = new["id"]  # the id in the import; its files are named after it
    agent_id = m.renames.get(source_id, source_id)  # the id it has in the draft
    siblings = parent.setdefault("sub-agents", [])
    # Copy the agent without its children (they are added one by one, with their own checks).
    agent = {k: v for k, v in new.items() if k != "sub-agents"} | {"id": agent_id}
    agent["sub-agents"] = []
    siblings.append(agent)
    m.agents[agent_id] = agent
    m.added.append(agent_id)
    m.prompts[agent_id] = m.import_prompts[source_id]
    # Queue its skill and (harness-managed) MCP folders; nothing is copied until the merge is
    # settled and checked.
    items = [("skills", skill["id"]) for skill in new.get("skills") or []] + [
        ("mcps", mcp["id"])
        for mcp in new.get("mcps") or []
        if mcp.get("managedBy") == "harness"
    ]
    for kind, item in items:
        src = m.import_dir / kind / source_id / item
        m.copies.append((src, m.draft_dir / kind / agent_id / item))
    return agent


def _place(m: _Merge, new: dict, parent: dict) -> None:
    """Put `new` into the draft under `parent`, then do the same for everything below it.

    `here` is the draft agent that now stands for `new`: the parent itself when `new` is the root
    being merged, otherwise a freshly added agent. Parents are handled before their children.
    """
    if new["id"] == m.merge_root:  # combine it with the parent; nothing new to add
        here = parent
        _merge_into(m, here, new)
    else:
        here = _add(m, new, parent)
    for child in new.get("sub-agents") or []:
        _place(m, child, here)


def name_clashes(root: Any) -> list[str]:
    """Agents with two sub-agents of one name (ignoring case): a parent could not tell its tools apart."""
    found, stack = [], [root]
    while stack:
        agent = stack.pop()
        if not isinstance(agent, dict):  # a draft can be half-typed
            continue
        children = [c for c in agent.get("sub-agents") or [] if isinstance(c, dict)]
        seen: set[str] = set()
        for child in children:
            name = str(child.get("name", ""))
            if name.strip().casefold() in seen:
                found.append(
                    f"“{agent.get('name')}” has two sub-agents named “{name}”."
                )
            seen.add(name.strip().casefold())
        stack += children
    return found


def _renames(taken: set[str], tree: dict, merged: str | None) -> dict[str, str]:
    """A free id ("lead-2", "lead-3", ...) for each new agent whose id the draft already uses.

    `taken` is the draft's ids; `merged` is the root being merged into the parent, which becomes
    no agent of its own and keeps no id.
    """
    ids = list(_agents(tree))
    used = taken | set(ids)  # a new id must not collide with either side
    renames = {}
    for agent_id in ids:
        if agent_id in taken and agent_id != merged:
            n = 2
            while f"{agent_id}-{n}" in used:
                n += 1
            renames[agent_id] = f"{agent_id}-{n}"
            used.add(renames[agent_id])
    return renames


def _plan(name: str, target: MergeTarget, resolutions: dict) -> _Merge:
    """Work out the merge in memory: the new family.json and prompts, the files to copy, what was
    added or merged, and what clashes. Writes nothing, so the preview and the merge share it."""
    draft = store.read(name)
    import_dir = config.IMPORTS_DIR / target.import_id
    if not (import_dir / "family.json").is_file():
        raise AppError(404, NOT_FOUND, "That import is no longer available.")
    imported = read_family(import_dir)
    agents = _agents(draft.family.get("agents"))
    parent = agents.get(target.parent_id)
    if parent is None:
        raise AppError(404, NOT_FOUND, f"The draft has no agent “{target.parent_id}”.")
    m = _Merge(
        draft_dir=config.DRAFTS_DIR / name,
        import_dir=import_dir,
        family=draft.family,
        prompts=draft.prompts,
        import_prompts=integrity.read_prompts(import_dir, imported),
        resolutions=resolutions,
        agents=agents,
        merge_root=None,
        renames={},
    )
    # The import as plain dicts shaped like the draft's, so the two can be combined directly.
    tree = imported.agents.model_dump(by_alias=True, exclude_none=True, mode="json")
    if target.mode == "merge":
        m.merge_root = tree["id"]
    m.renames = _renames(set(agents), tree, m.merge_root)
    _place(m, tree, parent)  # walks the whole imported tree
    return m


def preview(name: str, target: MergeTarget) -> MergePreview:
    """What merging would add and what clashes. Changes nothing."""
    m = _plan(name, target, {})
    return MergePreview(
        added=m.added,
        merged=m.merged,
        conflicts=m.conflicts,
        renamed=m.renames,
        warnings=name_clashes(m.family.get("agents")),
    )


def merge(name: str, request: MergeRequest) -> DraftOut:
    """Add the import to the draft with the user's answers, then delete the import folder."""
    m = _plan(name, request, request.resolutions)
    if m.conflicts:  # nothing has been written yet, so refusing here changes nothing
        shown = ", ".join(c.agent_id for c in m.conflicts)
        raise AppError(409, UNRESOLVED, f"Settle the conflicts first: {shown}.")
    # Check the limits (and ids) of the merged result before touching the disk.
    files = [p for src, _ in m.copies for p in src.rglob("*") if p.is_file()]
    extra = (len(files), sum(p.stat().st_size for p in files))
    safety.check_draft(m.draft_dir, m.family, m.prompts, extra)
    try:
        for src, dst in m.copies:
            shutil.rmtree(dst, ignore_errors=True)  # a leftover from a removed item
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dst, symlinks=True)
    except OSError as exc:
        reason = exc.strerror or type(exc).__name__
        raise AppError(500, INTERNAL, f"Could not copy the files: {reason}.") from exc
    # family.json and the prompts go last: if copying failed above, the draft still lists nothing
    # new (the copied folders would only be unlisted leftovers).
    store.write_files(m.draft_dir, DraftDoc(family=m.family, prompts=m.prompts))
    shutil.rmtree(m.import_dir, ignore_errors=True)  # used up
    return store.read(name)
