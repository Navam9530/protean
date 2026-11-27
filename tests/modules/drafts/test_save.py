import json

import pytest
from helpers import good_files, make_import, parse_events

from protean import config
from protean.family import version
from protean.identity import profile

NAME = "me_code-crew"
DRAFT = f"/api/drafts/{NAME}"


@pytest.fixture(autouse=True)
def signed_in(client) -> None:
    profile.set_github("me", None)


def draft_from_import(client, home, files=None, import_id="a" * 32) -> None:
    make_import(home, files or good_files(), import_id)
    r = client.post(
        "/api/drafts",
        json={
            "kind": "import",
            "importId": import_id,
            "owner": "me",
            "repo": "code-crew",
        },
    )
    assert r.status_code == 201, r.text


def save(client, name=NAME, **body):
    r = client.post(f"/api/drafts/{name}/save", json=body)
    assert r.status_code == 200, r.text
    return parse_events(r.text)


def done(events) -> dict:
    assert events[-1][0] == "done", events[-3:]
    return events[-1][1]


def failed(events) -> dict:
    assert events[-1][0] == "error", events[-3:]
    return events[-1][1]


def edit_prompt(client, text: str) -> None:
    """Start (or resume) an edit of the saved family and change the lead's prompt."""
    client.post("/api/drafts", json={"kind": "family", "name": NAME})
    doc = client.get(DRAFT).json()
    doc["prompts"]["lead"] = text
    assert client.put(DRAFT, json=doc).status_code == 200


def saved_version(home) -> str:
    return json.loads((home / "families" / NAME / "family.json").read_text())[
        "familyVersion"
    ]


def stages(events) -> list[str]:
    seen = []
    for event, data in events:
        if event == "stage" and data["id"] not in seen:
            seen.append(data["id"])
    return seen


# ---- the first save -------------------------------------------------------------------
def test_the_first_save_promotes_the_draft_and_keeps_its_version(client, home) -> None:
    draft_from_import(client, home)
    events = save(client)
    assert stages(events) == ["schema", "agents", "keys", "workspace", "promote"]
    assert done(events) == {
        "name": NAME,
        "familyVersion": "0.1.0",
        "bumped": False,
        "changed": True,
    }
    assert (home / "families" / NAME / "prompts" / "lead.md").read_text() == "You lead."
    assert (home / "families" / NAME / "LICENSE").is_file()
    assert not (home / "drafts" / NAME).exists()  # promoted, not copied
    assert [f["name"] for f in client.get("/api/families").json()] == [NAME]


def test_a_draft_that_fails_stays_and_nothing_is_saved(client, home) -> None:
    client.post("/api/drafts", json={"kind": "blank", "repo": "code-crew"})
    events = save(client)  # the blank lead has no prompt yet
    assert failed(events)["code"] == "invalid_family"
    assert ("stage", {"id": "agents", "state": "error"}) in events
    assert (home / "drafts" / NAME / "family.json").is_file()
    assert not (home / "families" / NAME).exists()


def test_saving_a_draft_that_does_not_exist_is_an_error_event(client) -> None:
    assert failed(save(client, "me_nope"))["code"] == "not_found"


def test_a_save_stops_when_the_disk_is_full(client, home, monkeypatch) -> None:
    class Full:
        free = 0

    monkeypatch.setattr(
        "protean.family.validation.workspace.shutil.disk_usage",
        lambda _: Full(),
    )
    draft_from_import(client, home)
    assert failed(save(client))["code"] == "no_space"
    assert (home / "drafts" / NAME).is_dir()


def test_skills_listed_and_uploaded_are_saved_and_unlisted_ones_are_left(
    client, home
) -> None:
    draft_from_import(client, home)
    for skill in ("lint", "extra"):
        client.put(
            f"{DRAFT}/agents/lead/skills/{skill}",
            files=[("files", (f"{skill}/SKILL.md", b"x"))],
        )
    doc = client.get(DRAFT).json()
    doc["family"]["agents"]["skills"] = [{"id": "lint"}]  # "extra" stays unlisted
    client.put(DRAFT, json=doc)
    events = save(client)
    assert any(
        "skills/lead/extra/" in d["message"] for e, d in events if e == "warning"
    )
    done(events)
    base = home / "families" / NAME / "skills" / "lead"
    assert (base / "lint" / "SKILL.md").is_file() and not (base / "extra").exists()


# ---- editing a saved family: the version ------------------------------------------------
def test_an_edit_that_changed_something_gets_a_new_version(client, home) -> None:
    draft_from_import(client, home)
    save(client)
    edit_prompt(client, "You lead, differently.")
    result = done(save(client))
    assert result == {
        "name": NAME,
        "familyVersion": "0.1.1",
        "bumped": True,
        "changed": True,
    }
    assert saved_version(home) == "0.1.1"
    assert (
        home / "families" / NAME / "prompts" / "lead.md"
    ).read_text() == "You lead, differently."


@pytest.mark.parametrize(("bump", "expected"), [("minor", "0.2.0"), ("major", "1.0.0")])
def test_the_bump_size_is_the_users_choice(client, home, bump, expected) -> None:
    draft_from_import(client, home)
    save(client)
    edit_prompt(client, "Changed.")
    assert done(save(client, bump=bump))["familyVersion"] == expected


def test_an_edit_with_no_changes_saves_nothing_and_keeps_the_version(
    client, home
) -> None:
    draft_from_import(client, home)
    save(client)
    before = (home / "families" / NAME / "family.json").stat().st_mtime_ns
    client.post("/api/drafts", json={"kind": "family", "name": NAME})
    result = done(save(client, bump="major"))
    assert result == {
        "name": NAME,
        "familyVersion": "0.1.0",
        "bumped": False,
        "changed": False,
    }
    assert (home / "families" / NAME / "family.json").stat().st_mtime_ns == before
    assert not (home / "drafts" / NAME).exists()


def test_a_version_typed_into_the_draft_does_not_count_as_a_change(
    client, home
) -> None:
    draft_from_import(client, home)
    save(client)
    client.post("/api/drafts", json={"kind": "family", "name": NAME})
    doc = client.get(DRAFT).json()
    doc["family"]["familyVersion"] = "9.9.9"
    client.put(DRAFT, json=doc)
    assert done(save(client))["changed"] is False
    assert saved_version(home) == "0.1.0"


def test_a_changed_skill_file_counts_as_a_change(client, home) -> None:
    files = good_files(**{"skills/lead/lint/SKILL.md": "one"})
    fam = json.loads(files["family.json"])
    fam["agents"]["skills"] = [{"id": "lint"}]
    files["family.json"] = json.dumps(fam)
    draft_from_import(client, home, files)
    save(client)
    client.post("/api/drafts", json={"kind": "family", "name": NAME})
    client.put(
        f"{DRAFT}/agents/lead/skills/lint",
        files=[("files", ("lint/SKILL.md", b"two"))],
    )
    assert done(save(client))["familyVersion"] == "0.1.1"


def test_an_unknown_bump_is_refused(client, home) -> None:
    draft_from_import(client, home)
    r = client.post(f"{DRAFT}/save", json={"bump": "huge"})
    assert r.status_code == 422


def test_version_bumps() -> None:
    assert version.bump("1.2.3", "patch") == "1.2.4"
    assert version.bump("1.2.3", "minor") == "1.3.0"
    assert version.bump("1.2.3", "major") == "2.0.0"
    assert version.bump("0.9.10", "patch") == "0.9.11"


def test_a_save_still_works_with_the_default_body(client, home) -> None:
    draft_from_import(client, home)
    r = client.post(f"{DRAFT}/save")  # no body at all
    assert parse_events(r.text)[-1][0] == "done"
    assert config.FAMILIES_DIR.joinpath(NAME).is_dir()


# ---- MCP values --------------------------------------------------------------------------
def draft_with_headers(client, home, values: dict | None):
    """A draft whose root agent has an external MCP that lists the Authorization header."""
    draft_from_import(client, home)
    body = client.get(f"/api/drafts/{NAME}").json()
    body["family"]["agents"]["mcps"] = [
        {
            "id": "jira",
            "managedBy": "external",
            "url": "https://x.test/mcp",
            "clientHeaders": ["Authorization"],
        }
    ]
    body["secrets"] = {"mcps": {"lead": {"jira": values}}} if values else {}
    assert client.put(f"/api/drafts/{NAME}", json=body).status_code == 200


def test_save_refuses_names_that_have_no_value(client, home) -> None:
    draft_with_headers(client, home, None)
    events = save(client)
    event, data = events[-1]
    assert event == "error" and data["code"] == "invalid_family"
    assert "lead / MCP jira: Authorization" in data["message"]
    assert (home / "drafts" / NAME).is_dir()  # the draft is kept


def test_save_goes_ahead_when_every_name_has_a_value(client, home) -> None:
    secret = {"clientHeaders": {"Authorization": "Bearer s3cret-value"}}
    draft_with_headers(client, home, secret)
    assert save(client)[-1][0] == "done"
    assert (home / "keys" / "families" / NAME / "mcps" / "lead" / "jira.json").is_file()
    assert not (home / "keys" / "drafts" / NAME).exists()
    assert "s3cret-value" not in (home / "families" / NAME / "family.json").read_text()


def test_deleting_the_saved_family_removes_its_values(client, home) -> None:
    draft_with_headers(client, home, {"clientHeaders": {"Authorization": "x"}})
    save(client)
    client.delete(f"/api/families/{NAME}")
    assert not (home / "keys" / "families" / NAME).exists()


@pytest.mark.parametrize(
    ("field", "names"),
    [
        ("clientHeaders", ["Bad Name"]),
        ("clientHeaders", ["Authorization", "Authorization"]),
        ("clientHeaders", [""]),
    ],
)
def test_save_checks_the_names_of_headers(client, home, field, names) -> None:
    draft_from_import(client, home)
    body = client.get(f"/api/drafts/{NAME}").json()
    mcp = {"id": "jira", "managedBy": "external", "url": "https://x.test", field: names}
    body["family"]["agents"]["mcps"] = [mcp]
    assert (
        client.put(f"/api/drafts/{NAME}", json=body).status_code == 200
    )  # a draft may be incomplete
    event, data = save(client)[-1]
    assert event == "error" and data["code"] == "invalid_family"


# ---- a draft and the saved family keep their own values --------------------------------
def saved_values(home) -> dict:
    return json.loads(
        (home / "keys" / "families" / NAME / "mcps" / "lead" / "jira.json").read_text()
    )


def edit_values(client, values: dict) -> None:
    body = client.get(f"/api/drafts/{NAME}").json()
    body["secrets"] = {"mcps": {"lead": {"jira": values}}}
    assert client.put(f"/api/drafts/{NAME}", json=body).status_code == 200


def test_a_new_draft_of_a_saved_family_starts_with_its_values(client, home) -> None:
    draft_with_headers(client, home, {"clientHeaders": {"Authorization": "one"}})
    save(client)
    r = client.post("/api/drafts", json={"kind": "family", "name": NAME})
    assert r.json()["secrets"]["mcps"]["lead"]["jira"]["clientHeaders"] == {
        "Authorization": "one"
    }


def test_editing_a_draft_does_not_change_the_saved_familys_values(client, home) -> None:
    draft_with_headers(client, home, {"clientHeaders": {"Authorization": "one"}})
    save(client)
    client.post("/api/drafts", json={"kind": "family", "name": NAME})
    edit_values(client, {"clientHeaders": {"Authorization": "two"}})
    assert saved_values(home)["clientHeaders"] == {"Authorization": "one"}
    assert client.get(f"/api/families/{NAME}").json()["secrets"]["mcps"]["lead"][
        "jira"
    ]["clientHeaders"] == {"Authorization": "one"}


def test_saving_replaces_the_values_even_when_only_a_value_changed(
    client, home
) -> None:
    draft_with_headers(client, home, {"clientHeaders": {"Authorization": "one"}})
    save(client)
    client.post("/api/drafts", json={"kind": "family", "name": NAME})
    edit_values(client, {"clientHeaders": {"Authorization": "two"}})
    events = save(client)
    assert done(events)["changed"] is False and done(events)["familyVersion"] == "0.1.0"
    assert saved_values(home)["clientHeaders"] == {"Authorization": "two"}
    assert not (home / "keys" / "drafts" / NAME).exists()


def test_discarding_a_draft_keeps_the_saved_familys_values(client, home) -> None:
    draft_with_headers(client, home, {"clientHeaders": {"Authorization": "one"}})
    save(client)
    client.post("/api/drafts", json={"kind": "family", "name": NAME})
    client.delete(f"/api/drafts/{NAME}")
    assert saved_values(home)["clientHeaders"] == {"Authorization": "one"}


def test_deleting_a_family_keeps_its_drafts_values(client, home) -> None:
    draft_with_headers(client, home, {"clientHeaders": {"Authorization": "one"}})
    save(client)
    client.post("/api/drafts", json={"kind": "family", "name": NAME})
    client.delete(f"/api/families/{NAME}")
    assert not (home / "keys" / "families" / NAME).exists()
    assert (home / "keys" / "drafts" / NAME / "mcps" / "lead" / "jira.json").is_file()


# ---- skill environment variables --------------------------------------------------------
def draft_with_skill_env(client, home, values: dict | None):
    """A draft whose root agent has a skill that lists the GITHUB_TOKEN variable."""
    draft_from_import(client, home)
    client.put(
        f"{DRAFT}/agents/lead/skills/lint",
        files=[("files", ("lint/SKILL.md", b"x"))],
    )
    body = client.get(DRAFT).json()
    body["family"]["agents"]["skills"] = [{"id": "lint", "env": ["GITHUB_TOKEN"]}]
    body["secrets"] = {"skills": {"lead": {"lint": values}}} if values else {}
    assert client.put(DRAFT, json=body).status_code == 200


def test_skill_values_are_kept_flat_in_the_keys_folder(client, home) -> None:
    draft_with_skill_env(client, home, {"GITHUB_TOKEN": "ghp_s3cret"})
    path = home / "keys" / "drafts" / NAME / "skills" / "lead" / "lint.json"
    assert json.loads(path.read_text()) == {"GITHUB_TOKEN": "ghp_s3cret"}
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert "ghp_s3cret" not in (home / "drafts" / NAME / "family.json").read_text()
    got = client.get(DRAFT).json()["secrets"]["skills"]["lead"]["lint"]
    assert got == {"GITHUB_TOKEN": "ghp_s3cret"}


def test_save_refuses_a_skill_variable_that_has_no_value(client, home) -> None:
    draft_with_skill_env(client, home, None)
    event, data = save(client)[-1]
    assert event == "error" and "lead / skill lint: GITHUB_TOKEN" in data["message"]


def test_a_saved_skills_values_follow_the_family(client, home) -> None:
    draft_with_skill_env(client, home, {"GITHUB_TOKEN": "ghp_s3cret"})
    assert save(client)[-1][0] == "done"
    saved = home / "keys" / "families" / NAME / "skills" / "lead" / "lint.json"
    assert json.loads(saved.read_text()) == {"GITHUB_TOKEN": "ghp_s3cret"}
    assert not (home / "keys" / "drafts" / NAME).exists()
    listed = json.loads((home / "families" / NAME / "family.json").read_text())
    assert listed["agents"]["skills"] == [{"id": "lint", "env": ["GITHUB_TOKEN"]}]


def test_removing_a_skills_variable_removes_its_value(client, home) -> None:
    draft_with_skill_env(client, home, {"GITHUB_TOKEN": "x"})
    body = client.get(DRAFT).json()
    body["family"]["agents"]["skills"] = [{"id": "lint"}]
    assert client.put(DRAFT, json=body).status_code == 200
    assert not (home / "keys" / "drafts" / NAME).exists()


def test_save_checks_the_names_of_skill_variables(client, home) -> None:
    draft_from_import(client, home)
    body = client.get(DRAFT).json()
    body["family"]["agents"]["skills"] = [{"id": "lint", "env": ["1BAD"]}]
    assert client.put(DRAFT, json=body).status_code == 200
    event, data = save(client)[-1]
    assert event == "error" and data["code"] == "invalid_family"
