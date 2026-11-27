"""What Protean last published for each family: {name: {version, commit, listed, description}}, in published.json.

It lives outside families/<name>/ because saving swaps that whole folder. The UI compares the
version here with the saved one to tell whether there is anything new to publish. It is only a
hint: publishing itself always asks GitHub.
"""

from protean import config
from protean.core.storage import read_json, write_json_atomic


def version(name: str) -> str | None:
    """The familyVersion last published for this family, or None."""
    entry = (read_json(config.PUBLISHED_FILE) or {}).get(name)
    return entry.get("version") if isinstance(entry, dict) else None


def listed(name: str) -> bool:
    """Whether the repo carried the marketplace topic when last seen."""
    entry = (read_json(config.PUBLISHED_FILE) or {}).get(name)
    return bool(entry.get("listed")) if isinstance(entry, dict) else False


def description(name: str) -> str:
    """The About text last sent to GitHub for this family ("" when none)."""
    entry = (read_json(config.PUBLISHED_FILE) or {}).get(name)
    return str(entry.get("description", "")) if isinstance(entry, dict) else ""


def record(
    name: str,
    family_version: str,
    commit: str,
    is_listed: bool,
    about: str | None = None,
) -> None:
    """Remember a publish. `about` is the description the user sent; None keeps the last one."""
    data = read_json(config.PUBLISHED_FILE) or {}
    data[name] = {
        "version": family_version,
        "commit": commit,
        "listed": is_listed,
        "description": description(name) if about is None else about,
    }
    write_json_atomic(config.PUBLISHED_FILE, data)


def set_listed(name: str, is_listed: bool) -> None:
    """After a list or unpublish. A family that was never published from here has no entry."""
    data = read_json(config.PUBLISHED_FILE) or {}
    if isinstance(data.get(name), dict):
        data[name]["listed"] = is_listed
        write_json_atomic(config.PUBLISHED_FILE, data)


def forget(name: str) -> None:
    """When the family is deleted, so a later family of the same name starts unpublished."""
    data = read_json(config.PUBLISHED_FILE) or {}
    if data.pop(name, None) is not None:
        write_json_atomic(config.PUBLISHED_FILE, data)
