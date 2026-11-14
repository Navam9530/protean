"""The GitHub token lives in <home>/keys/github.json (mode 0600, inside a 0700 folder)."""

import contextlib

from protean import config
from protean.core.storage import read_json, write_json_atomic


def load_token() -> dict | None:
    """Returns {"access_token", "scope"}, or None when not signed in."""
    data = read_json(config.GITHUB_TOKEN_FILE)
    return data if data and data.get("access_token") else None


def save_token(access_token: str, scope: str) -> None:
    write_json_atomic(
        config.GITHUB_TOKEN_FILE, {"access_token": access_token, "scope": scope}
    )


def delete_token() -> None:
    with contextlib.suppress(FileNotFoundError):
        config.GITHUB_TOKEN_FILE.unlink()


def granted_scopes(token: dict) -> set[str]:
    return {s for s in token.get("scope", "").split(",") if s}
