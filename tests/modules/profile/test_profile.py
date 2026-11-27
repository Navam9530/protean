import stat
from pathlib import Path

import pytest

from protean.identity.hostname import sanitize_owner


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("fedora", "fedora"),
        ("Navas-MacBook-Pro.local", "navas-macbook-pro"),
        ("DESKTOP-AB12CD3", "desktop-ab12cd3"),
        ("my_laptop", "my-laptop"),  # underscore separates owner from family name
        ("  Weird  Name!! ", "weird-name"),
        ("---", "local-user"),
        ("", "local-user"),
        ("a" * 80, "a" * 39),
    ],
)
def test_sanitize_owner(raw: str, expected: str) -> None:
    assert sanitize_owner(raw) == expected


def test_fresh_profile_has_no_source_yet(client) -> None:
    body = client.get("/api/profile").json()
    assert body["source"] is None
    assert body["owner"]
    assert body["avatarUrl"] is None


def test_skip_github_persists_and_is_idempotent(client, home: Path) -> None:
    first = client.post("/api/profile/skip-github").json()
    assert first["source"] == "hostname"
    assert client.post("/api/profile/skip-github").json() == first
    assert client.get("/api/profile").json() == first
    assert (home / "profile.json").exists()


def test_workspace_layout_and_permissions(client, home: Path) -> None:
    assert (home / "families").is_dir()
    assert stat.S_IMODE((home / "keys").stat().st_mode) == 0o700
