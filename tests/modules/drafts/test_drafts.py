import copy
import errno
import json
from pathlib import Path

import pytest
from helpers import family, good_files, make_import

from protean import config
from protean.identity import profile

NAME = "me_code-crew"


@pytest.fixture(autouse=True)
def signed_in(client) -> None:
    profile.set_github("me", None)  # the owner part of new names


def make_saved(home: Path, name: str = NAME) -> Path:
    """A saved family on disk (its name is the folder's)."""
    folder = home / "families" / name
    for path, content in good_files().items():
        target = folder / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content))
    return folder


def from_import(client, import_id: str, owner="me", repo="code-crew"):
    return client.post(
        "/api/drafts",
        json={"kind": "import", "importId": import_id, "owner": owner, "repo": repo},
    )


# ---- create -----------------------------------------------------------------------
def test_a_blank_draft_is_named_after_the_signed_in_owner(client, home) -> None:
    r = client.post("/api/drafts", json={"kind": "blank", "repo": "my-crew"})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "me_my-crew"
    assert "name" not in body["family"]  # the name is the folder's, not the file's
    assert body["family"]["agents"]["id"] == "lead"
    assert (home / "drafts" / "me_my-crew" / "family.json").is_file()
    assert client.get("/api/drafts/me_my-crew").json() == body


def test_a_name_that_exists_as_draft_or_family_is_refused(client, home) -> None:
    assert (
        client.post("/api/drafts", json={"kind": "blank", "repo": "x"}).status_code
        == 201
    )
    r = client.post("/api/drafts", json={"kind": "blank", "repo": "x"})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "already_exists")
    make_saved(home, "me_saved")
    r = client.post("/api/drafts", json={"kind": "blank", "repo": "saved"})
    assert r.status_code == 409


def test_a_bad_repo_name_is_refused(client) -> None:
    for repo in ("", "has space", "../x", "a" * 101):
        r = client.post("/api/drafts", json={"kind": "blank", "repo": repo})
        assert r.status_code == 422, repo


def test_a_draft_from_an_import_takes_its_name_from_the_repo(client, home) -> None:
    files = good_files(
        **{
            "skills/nobody/x/SKILL.md": "unlisted",
        }
    )
    import_id = make_import(home, files)
    r = from_import(client, import_id)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == NAME
    assert "name" not in body["family"]
    assert body["prompts"] == {"lead": "You lead.", "reviewer": "You review."}
    folder = home / "drafts" / NAME
    assert (folder / "LICENSE").is_file() and (folder / "README.md").is_file()
    assert not (folder / "skills" / "nobody").exists()  # not listed, so not copied
    assert not (home / "imports" / import_id).exists()  # the staging folder is gone


def test_an_import_with_listed_skill_and_mcp_folders_brings_them_along(
    client, home
) -> None:
    fam = family()
    fam["agents"]["skills"] = [{"id": "pr-review"}]
    fam["agents"]["mcps"] = [
        {"id": "files", "managedBy": "harness", "transport": "stdio"},
        {"id": "gh", "managedBy": "external", "url": "https://x"},
    ]
    files = good_files(
        **{
            "family.json": json.dumps(fam),
            "skills/lead/pr-review/SKILL.md": "s",
            "mcps/lead/files/server.py": "m",
        }
    )
    from_import(client, make_import(home, files))
    folder = home / "drafts" / NAME
    assert (folder / "skills/lead/pr-review/SKILL.md").read_text() == "s"
    assert (folder / "mcps/lead/files/server.py").read_text() == "m"


def test_an_import_that_is_gone_is_404(client) -> None:
    r = from_import(client, "b" * 32)
    assert (r.status_code, r.json()["error"]["code"]) == (404, "not_found")


def test_importing_a_name_that_is_taken_keeps_the_import(client, home) -> None:
    make_saved(home)
    import_id = make_import(home, good_files())
    assert from_import(client, import_id).status_code == 409
    assert (home / "imports" / import_id).is_dir()  # nothing was lost


def test_a_failed_copy_leaves_no_half_made_draft(client, home, monkeypatch) -> None:
    import_id = make_import(home, good_files())

    def boom(*_a, **_k):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr("protean.family.folder.shutil.copy2", boom)
    r = from_import(client, import_id)
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"
    assert "No space left" in r.json()["error"]["message"]
    assert list((home / "drafts").iterdir()) == []
    assert (home / "imports" / import_id).is_dir()


def test_editing_a_saved_family_copies_it_into_drafts(client, home) -> None:
    saved = make_saved(home)
    r = client.post("/api/drafts", json={"kind": "family", "name": NAME})
    assert r.status_code == 201 and r.json()["prompts"]["lead"] == "You lead."
    again = client.post("/api/drafts", json={"kind": "family", "name": NAME})
    assert again.status_code == 200  # resumes the same edit
    assert (saved / "family.json").is_file()  # the saved one is untouched
    assert (
        client.post(
            "/api/drafts", json={"kind": "family", "name": "me_nope"}
        ).status_code
        == 404
    )


def test_the_source_must_be_one_of_the_three_kinds(client) -> None:
    r = client.post("/api/drafts", json={"kind": "other"})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "invalid_request")
    assert client.post("/api/drafts", json={}).status_code == 422


# ---- list -------------------------------------------------------------------------
def test_listing_shows_drafts_and_whether_they_edit_a_saved_family(
    client, home
) -> None:
    client.post("/api/drafts", json={"kind": "blank", "repo": "fresh"})
    make_saved(home)
    client.post("/api/drafts", json={"kind": "family", "name": NAME})
    (home / "drafts" / ".half-built").mkdir()  # never shown
    listing = {d["name"]: d for d in client.get("/api/drafts").json()}
    assert set(listing) == {"me_fresh", NAME}
    assert (
        listing["me_fresh"]["editing"] is False
        and listing["me_fresh"]["agentCount"] == 1
    )
    assert listing[NAME]["editing"] is True and listing[NAME]["agentCount"] == 2
    assert listing[NAME]["familyVersion"] == "0.1.0"
    card = listing["me_fresh"]  # drafts carry the same card fields as saved families
    assert card["family"]["agents"]["id"] == "lead" and card["chatCount"] == 0
    assert card["accessedAt"] == card["updatedAt"]


# ---- autosave ---------------------------------------------------------------------
def doc(client, name="me_my-crew") -> dict:
    return client.get(f"/api/drafts/{name}").json()


def test_autosave_replaces_family_and_prompts_but_keeps_skill_folders(
    client, home
) -> None:
    client.post("/api/drafts", json={"kind": "blank", "repo": "my-crew"})
    skill = home / "drafts" / "me_my-crew" / "skills" / "lead" / "s" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("keep me")
    body = doc(client)
    body["family"]["agents"]["description"] = "half done"
    body["family"]["familyVersion"] = "1."  # incomplete values are fine in a draft
    r = client.put(
        "/api/drafts/me_my-crew",
        json={"family": body["family"], "prompts": {"lead": "Hi", "old": "x"}},
    )
    assert r.status_code == 200 and r.json()["updatedAt"] > 0
    r = client.put(
        "/api/drafts/me_my-crew",
        json={"family": body["family"], "prompts": {"lead": "Hello"}},
    )
    saved = doc(client)
    assert saved["family"]["agents"]["description"] == "half done"
    assert saved["prompts"] == {"lead": "Hello"}  # the removed agent's prompt is gone
    assert (
        saved["updatedAt"] == r.json()["updatedAt"]
    )  # a read says what the next autosave builds on
    assert skill.read_text() == "keep me"


@pytest.mark.parametrize(
    "change",
    [
        lambda f, p: f["agents"].update(id="../x"),
        lambda f, p: f["agents"].update(skills=[{"id": "../escape"}]),
        lambda f, p: f["agents"].update(mcps=[{"id": "A B"}]),
        lambda f, p: f["agents"]["sub-agents"].append("nope"),
        lambda f, p: p.update({"../evil": "x"}),
        lambda f, p: p.update({"lead": 5}),
    ],
)
def test_autosave_refuses_anything_that_could_escape_the_folder(
    client, home, change
) -> None:
    client.post("/api/drafts", json={"kind": "blank", "repo": "my-crew"})
    body = doc(client)
    family_doc, prompts = body["family"], {"lead": "x"}
    change(family_doc, prompts)
    r = client.put(
        "/api/drafts/me_my-crew", json={"family": family_doc, "prompts": prompts}
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] in ("invalid_draft", "invalid_request")
    assert not list(home.glob("evil*"))


def test_autosave_enforces_the_size_limit(client, monkeypatch) -> None:
    client.post("/api/drafts", json={"kind": "blank", "repo": "my-crew"})
    monkeypatch.setattr(config, "MAX_UNZIPPED_BYTES", 2000)
    body = doc(client)
    r = client.put(
        "/api/drafts/me_my-crew",
        json={"family": body["family"], "prompts": {"lead": "x" * 5000}},
    )
    assert (r.status_code, r.json()["error"]["code"]) == (413, "too_large")


def test_autosave_of_a_draft_that_does_not_exist_is_404(client) -> None:
    r = client.put(
        "/api/drafts/me_nope", json={"family": {"name": "me_nope"}, "prompts": {}}
    )
    assert r.status_code == 404


# ---- discard ----------------------------------------------------------------------
def test_discarding_deletes_the_draft_but_not_the_saved_family(client, home) -> None:
    saved = make_saved(home)
    client.post("/api/drafts", json={"kind": "family", "name": NAME})
    assert client.delete(f"/api/drafts/{NAME}").status_code == 204
    assert not (home / "drafts" / NAME).exists()
    assert (saved / "family.json").is_file()
    assert (
        client.delete(f"/api/drafts/{NAME}").status_code == 204
    )  # already gone is fine
    assert client.get(f"/api/drafts/{NAME}").status_code == 404


def test_names_in_urls_are_checked(client, home) -> None:
    for bad in ("nounderscore", "me_..%2F..", "me_a b", "a" * 40 + "_x"):
        assert client.get(f"/api/drafts/{bad}").status_code in (404, 422), bad
        assert client.delete(f"/api/drafts/{bad}").status_code in (404, 405, 422), bad


# ---- autosave -----------------------------------------------------------------------
def test_autosave_writes_only_what_changed(client, home) -> None:
    client.post("/api/drafts", json={"kind": "blank", "repo": "my-crew"})
    doc = client.get("/api/drafts/me_my-crew").json()
    folder = home / "drafts" / "me_my-crew"
    first = client.put("/api/drafts/me_my-crew", json=doc).json()["updatedAt"]
    before = (folder / "family.json").stat().st_mtime_ns
    again = client.put("/api/drafts/me_my-crew", json=doc).json()["updatedAt"]
    assert again == first and (folder / "family.json").stat().st_mtime_ns == before
    doc["prompts"]["lead"] = "Now with a prompt."
    changed = client.put("/api/drafts/me_my-crew", json=doc).json()["updatedAt"]
    assert changed > first  # a prompt-only change still moves updatedAt


def test_a_stale_autosave_is_refused(client, home) -> None:
    client.post("/api/drafts", json={"kind": "blank", "repo": "my-crew"})
    doc = client.get("/api/drafts/me_my-crew").json()
    seen = client.put("/api/drafts/me_my-crew", json=doc).json()["updatedAt"]
    doc["prompts"]["lead"] = "Typed in tab one."
    client.put("/api/drafts/me_my-crew", json={**doc, "baseUpdatedAt": seen})
    doc["prompts"]["lead"] = "Typed in tab two."
    r = client.put("/api/drafts/me_my-crew", json={**doc, "baseUpdatedAt": seen})
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    assert client.get("/api/drafts/me_my-crew").json()["prompts"]["lead"] == (
        "Typed in tab one."
    )


# ---- skill and MCP uploads -------------------------------------------------------------
ITEM = "/api/drafts/me_my-crew/agents/lead/skills/lint"


def upload(client, url: str, files: dict[str, str], top="lint"):
    parts = [
        ("files", (f"{top}/{path}", text.encode())) for path, text in files.items()
    ]
    return client.put(url, files=parts)


@pytest.fixture
def draft(client):
    client.post("/api/drafts", json={"kind": "blank", "repo": "my-crew"})


def test_a_skill_folder_is_stored_under_its_agent(client, home, draft) -> None:
    r = upload(client, ITEM, {"SKILL.md": "# Lint", "scripts/run.sh": "echo"})
    assert r.status_code == 200 and r.json() == {"files": 2}
    base = home / "drafts" / "me_my-crew" / "skills" / "lead" / "lint"
    assert (base / "SKILL.md").read_text() == "# Lint"
    assert (base / "scripts" / "run.sh").is_file()


def test_uploading_again_replaces_the_item(client, home, draft) -> None:
    upload(client, ITEM, {"SKILL.md": "old", "old.txt": "x"})
    upload(client, ITEM, {"SKILL.md": "new"})
    base = home / "drafts" / "me_my-crew" / "skills" / "lead" / "lint"
    assert (base / "SKILL.md").read_text() == "new"
    assert not (base / "old.txt").exists()
    assert [p.name for p in base.parent.iterdir()] == ["lint"]  # no temp folder left


def test_a_skill_needs_skill_md_and_a_failed_upload_keeps_the_old_one(
    client, home, draft
) -> None:
    upload(client, ITEM, {"SKILL.md": "keep"})
    r = upload(client, ITEM, {"README.md": "no skill file"})
    assert r.status_code == 422 and "SKILL.md" in r.json()["error"]["message"]
    base = home / "drafts" / "me_my-crew" / "skills" / "lead" / "lint"
    assert (base / "SKILL.md").read_text() == "keep"
    assert [p.name for p in base.parent.iterdir()] == ["lint"]


def test_an_mcp_folder_needs_files_but_no_particular_one(client, home, draft) -> None:
    url = "/api/drafts/me_my-crew/agents/lead/mcps/search"
    assert (
        upload(client, url, {"server.py": "print()"}, top="search").status_code == 200
    )
    assert client.put(url, files=[("files", ("search/", b""))]).status_code == 422


def test_upload_paths_and_ids_are_checked(client, home, draft) -> None:
    r = upload(client, ITEM, {"SKILL.md": "x", "../escape.txt": "x"})
    assert r.status_code == 422
    assert not (home / "drafts" / "me_my-crew" / "skills" / "escape.txt").exists()
    bad = "/api/drafts/me_my-crew/agents/Lead/skills/lint"
    assert upload(client, bad, {"SKILL.md": "x"}).status_code == 422
    assert (
        upload(
            client, "/api/drafts/me_nope/agents/lead/skills/lint", {"SKILL.md": "x"}
        ).status_code
        == 404
    )


def test_uploads_count_against_the_family_limits(
    client, home, draft, monkeypatch
) -> None:
    monkeypatch.setattr(config, "MAX_FILES", 2)  # family.json is already one
    r = upload(client, ITEM, {"SKILL.md": "x", "a.txt": "x"})
    assert r.status_code == 413
    assert upload(client, ITEM, {"SKILL.md": "x"}).status_code == 200


def list_skill(client, listed: bool) -> dict:
    """Autosave the draft with the lint skill listed on the root agent, or not."""
    body = client.get("/api/drafts/me_my-crew").json()
    body["family"]["agents"]["skills"] = [{"id": "lint"}] if listed else []
    r = client.put("/api/drafts/me_my-crew", json=body)
    assert r.status_code == 200, r.text
    return body


def test_there_is_no_endpoint_to_delete_an_item(client, draft) -> None:
    assert client.delete(ITEM).status_code == 405


def test_removed_items_stay_on_disk_and_do_not_count_against_the_limits(
    client, home, draft, monkeypatch
) -> None:
    upload(client, ITEM, {"SKILL.md": "x", "a.txt": "x"})  # unlisted: a removed item
    monkeypatch.setattr(config, "MAX_FILES", 3)  # family.json and two more
    assert (home / "drafts" / "me_my-crew" / "skills" / "lead" / "lint").is_dir()
    other = "/api/drafts/me_my-crew/agents/lead/skills/other"
    r = upload(client, other, {"SKILL.md": "x", "b.txt": "x"}, "other")
    assert r.status_code == 200  # 1 + 2: the removed item is not counted


def test_a_listed_item_counts_at_autosave(client, draft, monkeypatch) -> None:
    upload(client, ITEM, {"SKILL.md": "x", "a.txt": "x"})
    monkeypatch.setattr(config, "MAX_FILES", 2)
    list_skill(client, False)  # fine: nothing listed
    body = client.get("/api/drafts/me_my-crew").json()
    body["family"]["agents"]["skills"] = [{"id": "lint"}]
    r = client.put("/api/drafts/me_my-crew", json=body)  # 2 + family.json > 2
    assert (r.status_code, r.json()["error"]["code"]) == (413, "too_large")


def test_removed_items_are_capped_on_disk(client, draft, monkeypatch) -> None:
    upload(client, ITEM, {"SKILL.md": "x", "a.txt": "x"})  # unlisted: removed
    monkeypatch.setattr(config, "MAX_FILES", 1)
    monkeypatch.setattr(config, "DRAFT_DISK_FACTOR", 2)  # 2 files may stay on disk
    r = upload(
        client,
        "/api/drafts/me_my-crew/agents/lead/skills/two",
        {"SKILL.md": "x"},
        "two",
    )
    assert r.status_code == 413 and "removed items" in r.json()["error"]["message"]


def test_an_uploaded_skill_survives_autosave_and_is_copied_when_listed(
    client, home, draft
) -> None:
    upload(client, ITEM, {"SKILL.md": "x"})
    doc = client.get("/api/drafts/me_my-crew").json()
    client.put("/api/drafts/me_my-crew", json=doc)
    assert (
        home / "drafts" / "me_my-crew" / "skills" / "lead" / "lint" / "SKILL.md"
    ).is_file()


def test_a_drafts_size_counts_only_what_it_keeps(client, draft) -> None:
    (before,) = client.get("/api/drafts").json()
    upload(client, ITEM, {"SKILL.md": "x" * 1000})  # not listed: a removed item
    assert client.get("/api/drafts").json()[0]["size"] == before["size"]
    list_skill(client, True)
    assert client.get("/api/drafts").json()[0]["size"] >= before["size"] + 1000


# ---- MCP header and env values ---------------------------------------------------------
MCP = {
    "id": "jira",
    "managedBy": "external",
    "url": "https://x.test/mcp",
    "clientHeaders": ["Authorization"],
}


def with_mcp(client, values: dict | None = None, mcp: dict | None = None) -> dict:
    body = client.get("/api/drafts/me_my-crew").json()
    body["family"]["agents"]["mcps"] = [copy.deepcopy(mcp or MCP)]  # tests change it
    body["secrets"] = {"mcps": {"lead": {"jira": values}}} if values is not None else {}
    return body


def keys_file(home, scope="drafts"):
    return home / "keys" / scope / "me_my-crew" / "mcps" / "lead" / "jira.json"


def test_values_are_kept_in_the_keys_folder_not_in_family_json(
    client, home, draft
) -> None:
    body = with_mcp(client, {"clientHeaders": {"Authorization": "Bearer s3cret"}})
    assert client.put("/api/drafts/me_my-crew", json=body).status_code == 200
    stored = json.loads(keys_file(home).read_text())
    assert stored == {
        "clientHeaders": {"Authorization": "Bearer s3cret"},
        "serverEnv": {},
    }
    assert oct(keys_file(home).stat().st_mode & 0o777) == "0o600"
    assert "s3cret" not in (home / "drafts" / "me_my-crew" / "family.json").read_text()
    again = client.get("/api/drafts/me_my-crew").json()
    assert again["secrets"]["mcps"]["lead"]["jira"]["clientHeaders"] == {
        "Authorization": "Bearer s3cret"
    }


def test_removing_a_name_or_an_mcp_removes_its_value(client, home, draft) -> None:
    body = with_mcp(client, {"clientHeaders": {"Authorization": "x"}})
    client.put("/api/drafts/me_my-crew", json=body)
    body["family"]["agents"]["mcps"][0]["clientHeaders"] = []
    assert client.put("/api/drafts/me_my-crew", json=body).status_code == 200
    assert not keys_file(home).exists()
    assert not (
        home / "keys" / "drafts" / "me_my-crew"
    ).exists()  # empty folders are cleaned up


def test_values_follow_a_renamed_mcp_through_the_document(client, home, draft) -> None:
    body = with_mcp(client, {"clientHeaders": {"Authorization": "x"}})
    client.put("/api/drafts/me_my-crew", json=body)
    body["family"]["agents"]["mcps"][0]["id"] = "jira2"
    body["secrets"] = {
        "mcps": {"lead": {"jira2": {"clientHeaders": {"Authorization": "x"}}}}
    }
    r = client.put("/api/drafts/me_my-crew", json=body)
    assert r.status_code == 200, r.text
    assert not keys_file(home).exists()
    assert (keys_file(home).parent / "jira2.json").is_file()


def test_an_autosave_without_secrets_leaves_the_values_alone(
    client, home, draft
) -> None:
    body = with_mcp(client, {"clientHeaders": {"Authorization": "x"}})
    client.put("/api/drafts/me_my-crew", json=body)
    del body["secrets"]
    r = client.put("/api/drafts/me_my-crew", json=body)
    assert r.status_code == 200, r.text
    assert keys_file(home).is_file()


def test_empty_values_are_not_stored(client, home, draft) -> None:
    body = with_mcp(client, {"clientHeaders": {"Authorization": ""}})
    client.put("/api/drafts/me_my-crew", json=body)
    assert not keys_file(home).exists()


def test_discarding_a_draft_removes_its_values(client, home, draft) -> None:
    body = with_mcp(client, {"clientHeaders": {"Authorization": "x"}})
    client.put("/api/drafts/me_my-crew", json=body)
    client.delete("/api/drafts/me_my-crew")
    assert not (home / "keys" / "drafts" / "me_my-crew").exists()


def test_a_new_family_does_not_inherit_old_values(client, home) -> None:
    for scope in ("drafts", "families"):
        stale = keys_file(home, scope)
        stale.parent.mkdir(parents=True)
        stale.write_text('{"clientHeaders": {"Authorization": "old"}}')
    client.post("/api/drafts", json={"kind": "blank", "repo": "my-crew"})
    assert not (home / "keys" / "drafts" / "me_my-crew").exists()
    assert not (home / "keys" / "families" / "me_my-crew").exists()
