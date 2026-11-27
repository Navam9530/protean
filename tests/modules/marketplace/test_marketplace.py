import json
from pathlib import Path

import httpx
import pytest
import respx

from protean.modules.marketplace import service

API = "https://api.github.com"
SEARCH = f"{API}/search/repositories"
TREE = f"{API}/repos/me/code-crew/git/trees/HEAD"
README = f"{API}/repos/me/code-crew/readme"
ZIPBALL = f"{API}/repos/me/code-crew/zipball"
TAGS = f"{API}/repos/me/code-crew/tags"

ITEM = {
    "name": "code-crew",
    "description": "Reviews a diff.",
    "stargazers_count": 3,
    "license": {"spdx_id": "MIT"},
    "pushed_at": "2026-11-14T10:00:00Z",
    "owner": {"login": "me", "avatar_url": "https://avatars.example/me"},
}


@pytest.fixture(autouse=True)
def fresh_cache():
    service._cache.clear()


# ---- search --------------------------------------------------------------------
def test_search_maps_results_and_filters_by_topic(client) -> None:
    with respx.mock as m:
        route = m.get(SEARCH).respond(json={"total_count": 1, "items": [ITEM]})
        r = client.get("/api/marketplace/search", params={"q": "crew"})
    assert r.status_code == 200
    assert r.json() == {
        "total": 1,
        "page": 1,
        "items": [
            {
                "owner": "me",
                "repo": "code-crew",
                "description": "Reviews a diff.",
                "stars": 3,
                "license": "MIT",
                "pushedAt": 1794650400000,
                "avatarUrl": "https://avatars.example/me",
            }
        ],
    }
    q = route.calls.last.request.url.params["q"]
    assert "topic:agents-marketplace" in q and "archived:false" in q and "crew" in q


def test_search_without_license_and_empty_query(client) -> None:
    item = {**ITEM, "license": None, "description": None}
    with respx.mock as m:
        route = m.get(SEARCH).respond(json={"total_count": 1, "items": [item]})
        body = client.get("/api/marketplace/search").json()
    assert body["items"][0]["license"] is None
    assert body["items"][0]["description"] == ""
    assert "in:name" not in route.calls.last.request.url.params["q"]


def test_search_is_cached_for_a_minute(client) -> None:
    with respx.mock as m:
        route = m.get(SEARCH).respond(json={"total_count": 0, "items": []})
        client.get("/api/marketplace/search?q=a")
        client.get("/api/marketplace/search?q=a")
        client.get("/api/marketplace/search?q=b")
    assert route.call_count == 2


def test_search_rate_limit_is_reported(client) -> None:
    limited = httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, json={})
    with respx.mock as m:
        m.get(SEARCH).mock(return_value=limited)
        r = client.get("/api/marketplace/search")
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"
    assert "Signing in" in r.json()["error"]["message"]


def test_github_unreachable(client) -> None:
    with respx.mock as m:
        m.get(SEARCH).mock(side_effect=httpx.ConnectError("down"))
        r = client.get("/api/marketplace/search")
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "github_unreachable"


def test_search_page_is_validated(client) -> None:
    assert client.get("/api/marketplace/search?page=0").status_code == 422


# ---- the token ---------------------------------------------------------------------
def sign_in(home: Path, token: str = "gho_live") -> None:
    (home / "keys").mkdir(parents=True, exist_ok=True)
    (home / "keys" / "github.json").write_text(
        json.dumps({"access_token": token, "scope": "public_repo"})
    )
    (home / "profile.json").write_text(
        json.dumps({"source": "github", "github_login": "me"})
    )


def test_search_sends_the_token_when_signed_in(client, home) -> None:
    sign_in(home)
    with respx.mock as m:
        route = m.get(SEARCH).respond(json={"total_count": 0, "items": []})
        client.get("/api/marketplace/search")
    assert route.calls.last.request.headers["authorization"] == "Bearer gho_live"


def test_rejected_token_is_dropped_and_the_call_retried(client, home) -> None:
    sign_in(home, "gho_dead")
    ok = httpx.Response(200, json={"total_count": 0, "items": []})
    with respx.mock as m:
        route = m.get(SEARCH).mock(side_effect=[httpx.Response(401, json={}), ok])
        r = client.get("/api/marketplace/search")
    assert r.status_code == 200
    assert "authorization" not in route.calls.last.request.headers
    assert not (home / "keys" / "github.json").exists()
    assert client.get("/api/profile").json()["source"] == "hostname"


# ---- detail ------------------------------------------------------------------------
def tree(*paths: str) -> httpx.Response:
    return httpx.Response(200, json={"tree": [{"path": p} for p in paths]})


def test_detail_reports_files_and_readme(client) -> None:
    with respx.mock as m:
        m.get(TREE).mock(
            return_value=tree(
                "family.json", "LICENSE.md", "prompts/lead.md", "README.md"
            )
        )
        m.get(README).respond(text="# Hello")
        m.get(TAGS).respond(json=[])
        r = client.get("/api/marketplace/me/code-crew")
    assert r.json() == {
        "has": {"familyJson": True, "license": True, "prompts": True, "readme": True},
        "readme": "# Hello",
        "versions": [],
    }


def test_detail_flags_missing_files(client) -> None:
    with respx.mock as m:
        m.get(TREE).mock(
            return_value=tree("notes.txt", "docs/LICENSE")
        )  # nested LICENSE does not count
        m.get(README).respond(404, json={})
        m.get(TAGS).respond(json=[])
        r = client.get("/api/marketplace/me/code-crew")
    assert r.json() == {
        "has": {
            "familyJson": False,
            "license": False,
            "prompts": False,
            "readme": False,
        },
        "readme": None,
        "versions": [],
    }


def test_detail_of_unknown_repo_is_404(client) -> None:
    with respx.mock as m:
        m.get(TREE).respond(404, json={})
        m.get(README).respond(404, json={})
        m.get(TAGS).respond(404, json={})
        r = client.get("/api/marketplace/me/code-crew")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "repo_not_found"


def test_detail_lists_the_tags_and_reads_a_chosen_one(client) -> None:
    with respx.mock as m:
        m.get(TREE).mock(return_value=tree("family.json"))
        old_readme = m.get(README).mock(
            side_effect=lambda r: httpx.Response(
                200, text="old" if r.url.params.get("ref") == "v1.0.0" else "latest"
            )
        )
        m.get(TAGS).respond(json=[{"name": "v1.1.0"}, {"name": "release-2024"}])
        listing = client.get("/api/marketplace/me/code-crew").json()
        old_tree = m.get(f"{API}/repos/me/code-crew/git/trees/v1.0.0").mock(
            return_value=tree("family.json", "README.md")
        )
        old = client.get("/api/marketplace/me/code-crew", params={"version": "v1.0.0"})
    assert listing["versions"] == ["v1.1.0", "release-2024"]
    assert old.json()["readme"] == "old"
    assert old.json()["has"]["readme"] is True
    assert (
        old.json()["versions"] == []
    )  # the list is fetched once, with the default branch
    assert old_tree.called and old_readme.called


def test_detail_of_unknown_version_is_404(client) -> None:
    with respx.mock as m:
        m.get(f"{API}/repos/me/code-crew/git/trees/v9").respond(404, json={})
        m.get(README).respond(404, json={})
        r = client.get("/api/marketplace/me/code-crew", params={"version": "v9"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("version", ["../x", "-rf", "/x", "a b", "x" * 101])
def test_odd_versions_never_reach_github(client, version) -> None:
    r = client.get("/api/marketplace/me/code-crew", params={"version": version})
    assert r.status_code == 422
    r = client.post("/api/imports/github/me/code-crew", json={"version": version})
    assert r.status_code == 422


def test_odd_owner_or_repo_never_reaches_github(client) -> None:
    assert client.get("/api/marketplace/me/..").status_code in (404, 422)
    assert client.get("/api/marketplace/me%2Fx/code-crew").status_code in (404, 422)
