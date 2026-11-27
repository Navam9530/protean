"""The GitHub token lives in <home>/keys/github.json (mode 0600, inside a 0700 folder)."""

import contextlib

from protean import config
from protean.core.storage import read_json, write_json_atomic

_cache: dict | None = None  # the file is read once; save/delete keep it in step
_loaded = False


def reset_cache() -> None:
    global _cache, _loaded
    _cache, _loaded = None, False


def load_token() -> dict | None:
    """Returns {"access_token", "scope"}, or None when not signed in."""
    global _cache, _loaded
    if not _loaded:
        data = read_json(config.GITHUB_TOKEN_FILE)
        _cache = data if data and data.get("access_token") else None
        _loaded = True
    return _cache


def save_token(access_token: str, scope: str) -> None:
    global _cache, _loaded
    data = {"access_token": access_token, "scope": scope}
    write_json_atomic(config.GITHUB_TOKEN_FILE, data)
    _cache, _loaded = data, True


def delete_token() -> None:
    global _cache, _loaded
    with contextlib.suppress(FileNotFoundError):
        config.GITHUB_TOKEN_FILE.unlink()
    _cache, _loaded = None, True


def granted_scopes(token: dict) -> set[str]:
    return {s for s in token.get("scope", "").split(",") if s}
