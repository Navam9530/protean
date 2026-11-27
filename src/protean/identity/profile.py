"""The user's profile, kept in <home>/profile.json (not secret).

Stored as a plain dict with only what cannot be derived:
  source        None until the user chooses, then "hostname" or "github"
  github_login  set while source == "github"
  avatar_url    set while source == "github"
The hostname owner is not stored; it is read from the OS whenever needed.
"""

from typing import Literal

from protean import config
from protean.core.errors import ALREADY_SIGNED_IN, AppError
from protean.core.schemas import CamelModel
from protean.core.storage import read_json, write_json_atomic
from protean.identity.hostname import read_hostname_owner


class Profile(CamelModel):
    # None until the user makes the first-run choice (so there is no separate "onboarded" flag).
    source: Literal["hostname", "github"] | None
    owner: str  # id prefix: the sanitized hostname or the GitHub login, depending on `source`
    avatar_url: str | None = None


_cache: dict | None = None  # the file is read once; every write goes through _save


def reset_cache() -> None:
    global _cache
    _cache = None


def _load() -> dict:
    global _cache
    if _cache is None:
        _cache = read_json(config.PROFILE_FILE) or {}
    return _cache


def _save(profile: dict) -> None:
    global _cache
    write_json_atomic(config.PROFILE_FILE, profile)
    _cache = profile


def get() -> Profile:
    p = _load()
    source = p.get("source")
    owner = p["github_login"] if source == "github" else read_hostname_owner()
    return Profile(source=source, owner=owner, avatar_url=p.get("avatar_url"))


def is_github() -> bool:
    return _load().get("source") == "github"


def skip_github() -> Profile:
    """First-run choice: use the OS hostname as the owner."""
    if is_github():
        raise AppError(409, ALREADY_SIGNED_IN, "Already signed in with GitHub.")
    _save({"source": "hostname"})
    return get()


def set_github(login: str, avatar_url: str | None) -> Profile:
    _save({"source": "github", "github_login": login, "avatar_url": avatar_url})
    return get()


def clear_github() -> Profile:
    """Logout: back to the local profile. Existing families keep their ids."""
    if is_github():
        _save({"source": "hostname"})
    return get()
