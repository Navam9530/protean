import asyncio
import io
import json
import stat
import zipfile
from pathlib import Path

import httpx
import pytest
import respx
from helpers import Events, family, good_files, make_zip, parse_events

from protean import config
from protean.modules.marketplace import github, importer
from protean.modules.profile import store

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
    github._cache.clear()


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
    r = client.post("/api/marketplace/me/code-crew/import", json={"version": version})
    assert r.status_code == 422


def test_odd_owner_or_repo_never_reaches_github(client) -> None:
    assert client.get("/api/marketplace/me/..").status_code in (404, 422)
    assert client.get("/api/marketplace/me%2Fx/code-crew").status_code in (404, 422)


# ---- import ------------------------------------------------------------------------
def do_import(
    client, files: dict[str, str | bytes] | bytes, top: str = "me-code-crew-abc123"
) -> Events:
    """Run an import and return its events."""
    content = files if isinstance(files, bytes) else make_zip(files, top)
    with respx.mock as m:
        m.get(ZIPBALL).mock(return_value=httpx.Response(200, content=content))
        r = client.post("/api/marketplace/me/code-crew/import")
    assert r.status_code == 200, r.text
    return parse_events(r.text)


def test_import_downloads_the_chosen_version(client) -> None:
    content = make_zip(good_files(), "me-code-crew-abc123")
    with respx.mock as m:
        route = m.get(f"{ZIPBALL}/v1.0.0").mock(
            return_value=httpx.Response(200, content=content)
        )
        r = client.post(
            "/api/marketplace/me/code-crew/import", json={"version": "v1.0.0"}
        )
    assert route.called
    assert done(parse_events(r.text))["owner"] == "me"


def test_import_of_unknown_version_fails_with_not_found(client, home) -> None:
    with respx.mock as m:
        m.get(f"{ZIPBALL}/v9").respond(404, json={})
        r = client.post("/api/marketplace/me/code-crew/import", json={"version": "v9"})
    events = parse_events(r.text)
    assert events[-1][0] == "error" and events[-1][1]["code"] == "not_found"
    assert not any((home / "imports").iterdir())


def done(events: Events) -> dict:
    assert events[-1][0] == "done", events[-3:]
    return events[-1][1]


def failed(events: Events) -> dict:
    assert events[-1][0] == "error", events[-3:]
    return events[-1][1]


def test_import_returns_the_family_and_keeps_a_draft(client, home) -> None:
    body = done(do_import(client, good_files()))
    assert (body["owner"], body["repo"], body["familyVersion"]) == (
        "me",
        "code-crew",
        "0.1.0",
    )
    assert body["warnings"] == []
    assert body["prompts"] == {"lead": "You lead.", "reviewer": "You review."}
    assert "prompt" not in body["agents"]
    assert "model" not in body["agents"]["sub-agents"][0]  # unset fields are omitted
    folder = home / "imports" / body["importId"]
    assert (folder / "family.json").is_file() and (
        folder / "prompts" / "lead.md"
    ).is_file()
    assert [p.name for p in (home / "imports").iterdir()] == [
        body["importId"]
    ]  # no stray zip


def test_import_streams_stages_then_agents_then_done(client) -> None:
    events = do_import(client, good_files())
    stages = [(d["id"], d["state"]) for e, d in events if e == "stage"]
    assert stages == [
        ("download", "running"),
        ("download", "done"),
        ("extract", "running"),
        ("extract", "done"),
        ("schema", "running"),
        ("schema", "done"),
        ("agents", "running"),
        ("agents", "done"),
    ]
    names = [e for e, _ in events]
    assert names.index("tree") < names.index("agent")  # the tree arrives first
    assert names.count("done") == 1 and names[-1] == "done"
    checks = [(d["id"], d["check"], d["state"]) for e, d in events if e == "check"]
    assert ("lead", "prompt", "ok") in checks and ("reviewer", "mcps", "ok") in checks
    assert len(checks) == 6  # 2 agents x prompt, skills, mcps
    agents = [(d["id"], d["state"]) for e, d in events if e == "agent"]
    assert agents == [
        ("lead", "running"),
        ("lead", "ok"),
        ("reviewer", "running"),
        ("reviewer", "ok"),
    ]


def test_missing_license_and_readme_are_warnings(client) -> None:
    files = good_files()
    del files["LICENSE"], files["README.md"]
    warnings = done(do_import(client, files))["warnings"]
    assert any("No LICENSE" in w for w in warnings)
    assert any("No README" in w for w in warnings)


def test_discarding_an_import_deletes_its_folder(client, home) -> None:
    import_id = done(do_import(client, good_files()))["importId"]
    assert (home / "imports" / import_id).is_dir()
    assert client.delete(f"/api/imports/{import_id}").status_code == 204
    assert not (home / "imports" / import_id).exists()
    assert client.delete(f"/api/imports/{import_id}").status_code == 204  # idempotent


def test_discard_refuses_ids_that_are_not_import_ids(client, home) -> None:
    (home / "families").mkdir(parents=True, exist_ok=True)
    assert client.delete("/api/imports/..%2Ffamilies").status_code in (404, 405, 422)
    assert client.delete("/api/imports/not-an-id").status_code == 422
    assert (home / "families").is_dir()


def test_every_failing_agent_is_reported_before_the_error(client) -> None:
    files = good_files()
    del files["prompts/lead.md"], files["prompts/reviewer.md"]
    events = do_import(client, files)
    failing = [d["id"] for e, d in events if e == "agent" and d["state"] == "error"]
    assert failing == ["lead", "reviewer"]
    stages = [(d["id"], d["state"]) for e, d in events if e == "stage"]
    assert ("agents", "error") in stages
    assert failed(events)["code"] == "invalid_family"


def test_warnings_are_streamed_and_end_the_agents_stage_with_a_warning(client) -> None:
    events = do_import(client, good_files(**{"prompts/ghost.md": "x"}))
    assert [e for e, _ in events].count("warning") == 1
    assert [d for e, d in events if e == "stage"][-1]["state"] == "warning"


def test_a_client_that_goes_away_leaves_no_folder(client, home) -> None:
    async def abandon() -> None:
        content = make_zip(good_files())
        with respx.mock as m:
            m.get(ZIPBALL).mock(return_value=httpx.Response(200, content=content))
            events = importer.import_repo("me", "code-crew")
            async for event, data in events:
                if (event, data.get("id"), data.get("state")) == (
                    "stage",
                    "extract",
                    "done",
                ):
                    break
            assert any((home / "imports").iterdir())  # the folder exists mid-import
            await events.aclose()  # what a disconnect does

    asyncio.run(abandon())
    assert list((home / "imports").iterdir()) == []


def test_import_rejects_missing_prompt_skill_and_mcp_folders(client) -> None:
    fam = family()
    fam["agents"]["skills"] = [{"id": "pr-review"}]
    fam["agents"]["mcps"] = [
        {"id": "files", "managedBy": "harness", "transport": "stdio"}
    ]
    files: dict[str, str | bytes] = {
        "family.json": json.dumps(fam),
        "prompts/lead.md": "x",
    }
    error = failed(do_import(client, files))
    assert error["code"] == "invalid_family"
    message = error["message"]
    for path in ("prompts/reviewer.md", "skills/lead/pr-review/", "mcps/lead/files/"):
        assert path in message


def test_external_mcp_needs_no_folder(client) -> None:
    fam = family()
    fam["agents"]["mcps"] = [
        {"id": "github", "managedBy": "external", "url": "https://x/mcp"}
    ]
    files = good_files()
    files["family.json"] = json.dumps(fam)
    done(do_import(client, files))


def test_files_not_listed_in_family_json_are_reported_and_ignored(client) -> None:
    files = good_files(
        **{
            "prompts/ghost.md": "x",
            "skills/lead/stray/SKILL.md": "x",
            "mcps/reviewer/stray/server.py": "x",
            "skills/nobody/x/SKILL.md": "x",
        }
    )
    warnings = done(do_import(client, files))["warnings"]
    for path in (
        "prompts/ghost.md",
        "skills/lead/stray/",
        "mcps/reviewer/stray/",
        "skills/nobody/",
    ):
        assert any(path in w for w in warnings), path


def test_prompt_key_in_family_json_is_rejected(client) -> None:
    fam = family()
    fam["agents"]["prompt"] = "inline prompt"
    files = good_files()
    files["family.json"] = json.dumps(fam)
    invalid(client, files, "agents.prompt")


@pytest.mark.parametrize(
    ("agent_changes", "message"),
    [
        ({"skills": [{"id": "a"}, {"id": "a"}]}, "same skill twice"),
        ({"skills": [{"id": "../escape"}]}, "lowercase letters"),
        (
            {"mcps": [{"id": "m", "managedBy": "external", "url": "u"}] * 2},
            "same MCP server twice",
        ),
        (
            {"mcps": [{"id": "../m", "managedBy": "external", "url": "u"}]},
            "lowercase letters",
        ),
    ],
)
def test_import_rejects_unsafe_or_duplicate_skill_and_mcp_ids(
    client, agent_changes, message
) -> None:
    fam = family()
    fam["agents"].update(agent_changes)
    files = good_files()
    files["family.json"] = json.dumps(fam)
    invalid(client, files, message)


def test_tool_aliases_are_accepted_but_plain_aliases_are_not(client) -> None:
    def with_field(field: str) -> dict[str, str | bytes]:
        fam = family()
        fam["agents"]["mcps"] = [
            {
                "id": "gh",
                "managedBy": "external",
                "url": "u",
                "disabledTools": ["x"],
                field: {"a": "b"},
            }
        ]
        files = good_files()
        files["family.json"] = json.dumps(fam)
        return files

    done(do_import(client, with_field("toolAliases")))
    invalid(client, with_field("aliases"), "aliases")


def test_import_accepts_present_skill_and_mcp_folders(client) -> None:
    fam = family()
    fam["agents"]["skills"] = [{"id": "pr-review"}]
    fam["agents"]["mcps"] = [
        {"id": "files", "managedBy": "harness", "transport": "stdio"}
    ]
    files = good_files(
        **{"skills/lead/pr-review/SKILL.md": "s", "mcps/lead/files/server.py": "m"}
    )
    files["family.json"] = json.dumps(fam)
    assert done(do_import(client, files))["warnings"] == []


def invalid(client, files, message: str) -> None:
    error = failed(do_import(client, files))
    assert error["code"] == "invalid_family"
    assert message in error["message"]


def test_import_rejects_a_repo_without_family_json(client) -> None:
    invalid(client, {"README.md": "hi"}, "family.json was not found")


def test_import_rejects_broken_json(client) -> None:
    invalid(client, {"family.json": "{nope"}, "not valid JSON")


def test_import_rejects_duplicate_agent_ids(client) -> None:
    fam = family()
    twin = {**fam["agents"]["sub-agents"][0], "name": "another reviewer"}
    fam["agents"]["sub-agents"].append(twin)  # a new name, the same id
    invalid(client, {"family.json": json.dumps(fam)}, "share the id “reviewer”")


def test_import_rejects_sub_agents_that_share_a_name(client) -> None:
    fam = family()
    twin = {**fam["agents"]["sub-agents"][0], "id": "reviewer-2", "name": "Reviewer "}
    fam["agents"]["sub-agents"].append(twin)  # same name apart from case and spaces
    invalid(client, {"family.json": json.dumps(fam)}, "two sub-agents are named")


@pytest.mark.parametrize("old_key", ["name", "description", "version"])
def test_import_rejects_the_fields_a_family_no_longer_has(client, old_key) -> None:
    fam = family()
    fam[old_key] = "x"
    invalid(client, {"family.json": json.dumps(fam)}, old_key)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"familyVersion": "1.2"}, "must look like 1.2.3"),
        ({"schemaVersion": 2}, "Update Protean"),
        ({"schemaVersion": 0}, "schemaVersion"),
        ({"schemaVersion": "1"}, "schemaVersion"),
        ({"surprise": True}, "surprise"),
    ],
)
def test_import_rejects_schema_violations(client, changes, message) -> None:
    invalid(client, {"family.json": json.dumps(family(**changes))}, message)


def test_import_rejects_canvas_positions(client) -> None:
    """Positions are not part of a family: the UI lays the tree out itself."""
    fam = family()
    fam["agents"]["position"] = {"x": 0, "y": 0}
    invalid(client, {"family.json": json.dumps(fam)}, "position")


def test_import_rejects_a_bad_agent_id(client) -> None:
    fam = family()
    fam["agents"]["id"] = "Lead Agent"
    invalid(client, {"family.json": json.dumps(fam)}, "lowercase letters")


@pytest.mark.parametrize(
    ("mcp", "message"),
    [
        ({"id": "a", "managedBy": "external"}, "need a url"),
        (
            {
                "id": "a",
                "managedBy": "external",
                "url": "https://x",
                "transport": "http",
            },
            "cannot set transport",
        ),
        ({"id": "a", "managedBy": "harness"}, "need a transport"),
        (
            {
                "id": "a",
                "managedBy": "harness",
                "transport": "stdio",
                "url": "http://x",
            },
            "cannot set url",
        ),
        ({"id": "a", "managedBy": "harness", "transport": "http"}, "need a url"),
    ],
)
def test_import_rejects_mcp_rule_violations(client, mcp, message) -> None:
    fam = family()
    fam["agents"]["mcps"] = [mcp]
    invalid(client, {"family.json": json.dumps(fam)}, message)


def test_failed_import_leaves_no_draft(client, home) -> None:
    do_import(client, {"README.md": "hi"})
    assert list((home / "imports").iterdir()) == []


def test_import_rejects_path_escape(client) -> None:
    invalid(client, make_zip({"../evil.txt": "x", **good_files()}), "unsafe path")


def test_import_rejects_symlinks(client) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        link = zipfile.ZipInfo("top/link")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(link, "/etc/passwd")
        z.writestr("top/family.json", json.dumps(family()))
    invalid(client, buf.getvalue(), "symlink")


def test_import_rejects_too_many_files(client, monkeypatch) -> None:
    monkeypatch.setattr(config, "MAX_FILES", 3)
    events = do_import(client, good_files(**{"a.txt": "1", "b.txt": "2"}))
    assert failed(events)["code"] == "too_large"


def test_import_rejects_oversized_contents(client, monkeypatch) -> None:
    monkeypatch.setattr(config, "MAX_UNZIPPED_BYTES", 1000)
    events = do_import(client, good_files(**{"big.bin": b"x" * 5000}))
    assert failed(events)["code"] == "too_large"


def test_import_rejects_oversized_download(client, monkeypatch) -> None:
    monkeypatch.setattr(config, "MAX_ZIP_BYTES", 100)
    error = failed(do_import(client, good_files()))
    assert error["code"] == "too_large"
    assert "download" in error["message"]


def test_import_of_unknown_repo(client) -> None:
    with respx.mock as m:
        m.get(ZIPBALL).respond(404, json={})
        r = client.post("/api/marketplace/me/code-crew/import")
    assert failed(parse_events(r.text))["code"] == "repo_not_found"


def test_import_rejects_a_broken_archive(client) -> None:
    assert failed(do_import(client, b"this is not a zip"))["code"] == "github_error"


def test_import_needs_a_local_origin(client) -> None:
    r = client.post(
        "/api/marketplace/me/code-crew/import",
        headers={"Origin": "https://evil.example"},
    )
    assert r.status_code == 403


# ---- upload of a local folder ----------------------------------------------------------
def do_upload(client, files: dict[str, str | bytes], top="code-crew"):
    parts = [
        (
            "files",
            (
                f"{top}/{path}",
                content if isinstance(content, bytes) else content.encode(),
            ),
        )
        for path, content in files.items()
    ]
    r = client.post("/api/imports/upload", files=parts)
    assert r.status_code == 200, r.text
    return parse_events(r.text)


def test_an_uploaded_folder_is_validated_like_an_import(client, home) -> None:
    store.set_github("me", None)
    body = done(do_upload(client, good_files()))
    assert (body["owner"], body["repo"], body["familyVersion"]) == (
        "me",
        "code-crew",
        "0.1.0",
    )
    assert body["prompts"] == {"lead": "You lead.", "reviewer": "You review."}
    assert (home / "imports" / body["importId"] / "family.json").is_file()


def test_an_uploaded_folder_with_a_missing_prompt_is_refused_and_removed(
    client, home
) -> None:
    store.set_github("me", None)
    files = good_files()
    del files["prompts/reviewer.md"]
    events = do_upload(client, files)
    assert failed(events)["code"] == "invalid_family"
    assert list((home / "imports").iterdir()) == []


def test_an_uploaded_folder_cannot_escape_or_bring_git_history(client, home) -> None:
    store.set_github("me", None)
    body = done(do_upload(client, {**good_files(), ".git/config": "x"}))
    assert not (home / "imports" / body["importId"] / ".git").exists()
    events = do_upload(client, {**good_files(), "../evil.txt": "x"})
    assert "unsafe path" in failed(events)["message"]
    assert not (home / "evil.txt").exists()


def upload_refused(client, names: list[str]):
    parts = [("files", (name, b"1")) for name in names]
    r = client.post("/api/imports/upload", files=parts)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"
    return r.json()["error"]["message"]


def test_an_upload_is_named_after_its_folder(client) -> None:
    store.set_github("me", None)
    body = done(do_upload(client, good_files(), top="My_Crew.v2"))
    assert (body["owner"], body["repo"]) == ("me", "My_Crew.v2")


def test_an_upload_needs_a_usable_folder_name(client) -> None:
    assert "rename the folder" in upload_refused(client, ["my family/family.json"])
    assert "rename the folder" in upload_refused(client, ["../family.json"])


def test_an_upload_must_be_one_folder(client) -> None:
    assert "loose files" in upload_refused(client, ["family.json"])
    assert "one folder" in upload_refused(client, ["a/family.json", "b/x.md"])
    r = client.post("/api/imports/upload", files=[])
    assert r.status_code == 422
