import json

import pytest
from helpers import family, good_files, make_import

from protean.modules.profile import store

DRAFT = "me_my-crew"
URL = f"/api/drafts/{DRAFT}"


@pytest.fixture(autouse=True)
def draft(client) -> None:
    store.set_github("me", None)
    client.post("/api/drafts", json={"kind": "blank", "repo": "my-crew"})


def preview(client, import_id, parent="lead", mode="append"):
    return client.post(
        f"{URL}/merge/preview",
        json={"importId": import_id, "parentId": parent, "mode": mode},
    )


def merge(client, import_id, parent="lead", resolutions=None, mode="append"):
    body = {"importId": import_id, "parentId": parent, "mode": mode}
    return client.post(f"{URL}/merge", json={**body, "resolutions": resolutions or {}})


def agent(root: dict, agent_id: str) -> dict:
    stack = [root]
    while stack:
        a = stack.pop()
        if a["id"] == agent_id:
            return a
        stack += a["sub-agents"]
    raise KeyError(agent_id)


def helper_family(**agent_changes) -> dict:
    """An import whose root (`helper`) is not in the draft."""
    root = {
        "id": "helper",
        "name": "helper",
        "description": "Helps.",
        "mcps": [],
        "skills": [],
        "sub-agents": [],
        **agent_changes,
    }
    return family(agents=root)


def helper_files(**extra) -> dict:
    return {
        "family.json": json.dumps(helper_family()),
        "prompts/helper.md": "You help.",
        **extra,
    }


def upload_skill(client, agent_id: str, skill: str, text: str) -> None:
    r = client.put(
        f"{URL}/agents/{agent_id}/skills/{skill}",
        files=[("files", (f"{skill}/SKILL.md", text.encode()))],
    )
    assert r.status_code == 200
    doc = client.get(URL).json()
    agent(doc["family"]["agents"], agent_id)["skills"].append(
        {"id": skill}
    )  # as the UI does
    assert client.put(URL, json=doc).status_code == 200


def test_a_new_agent_joins_under_the_parent_with_its_prompt(client, home) -> None:
    import_id = make_import(home, helper_files())
    p = preview(client, import_id).json()
    assert p == {
        "added": ["helper"],
        "merged": [],
        "conflicts": [],
        "renamed": {},
        "warnings": [],
    }
    r = merge(client, import_id)
    assert r.status_code == 200
    body = r.json()
    lead = body["family"]["agents"]
    assert [a["id"] for a in lead["sub-agents"]] == ["helper"]
    assert body["prompts"]["helper"] == "You help."
    assert not (home / "imports" / import_id).exists()  # the staging folder is gone


def test_preview_changes_nothing(client, home) -> None:
    before = client.get(URL).json()
    import_id = make_import(home, good_files())
    preview(client, import_id)
    assert client.get(URL).json() == before
    assert (home / "imports" / import_id).is_dir()


def test_paired_agents_clash_only_where_the_values_differ(client, home) -> None:
    import_id = make_import(home, good_files())
    p = preview(client, import_id, mode="merge").json()
    assert p["added"] == ["reviewer"] and p["merged"] == ["lead"]
    (c,) = p["conflicts"]
    assert c["agentId"] == "lead"
    # name is equal, model and prompt are empty in the draft: only the description differs
    assert [f["field"] for f in c["fields"]] == ["description"]
    assert c["fields"][0]["new"] == "Splits the review."


def test_unsettled_conflicts_block_the_merge_and_change_nothing(client, home) -> None:
    import_id = make_import(home, good_files())
    before = client.get(URL).json()
    r = merge(client, import_id, mode="merge")
    assert r.status_code == 409 and r.json()["error"]["code"] == "unresolved_conflicts"
    assert client.get(URL).json() == before
    assert (home / "imports" / import_id).is_dir()


@pytest.mark.parametrize(
    ("choice", "expected"),
    [
        ("old", "Coordinates the family and delegates work to sub-agents."),
        ("new", "Splits the review."),
        ({"custom": "Mine."}, "Mine."),
    ],
)
def test_each_way_of_settling_a_field(client, home, choice, expected) -> None:
    import_id = make_import(home, good_files())
    r = merge(
        client,
        import_id,
        mode="merge",
        resolutions={"lead": {"fields": {"description": choice}}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert agent(body["family"]["agents"], "lead")["description"] == expected
    # the import's reviewer came along, and the empty fields were filled in
    assert agent(
        body["family"]["agents"], "reviewer"
    )  # the import's reviewer came along
    assert body["prompts"]["lead"] == "You lead." and body["prompts"]["reviewer"]
    assert agent(body["family"]["agents"], "lead")["model"]["provider"] == "anthropic"


def test_a_skill_with_the_same_id_and_different_files_clashes(client, home) -> None:
    upload_skill(client, "lead", "lint", "mine")
    files = good_files(**{"skills/lead/lint/SKILL.md": "theirs"})
    fam = family()
    fam["agents"]["skills"] = [{"id": "lint"}]
    files["family.json"] = json.dumps(fam)
    import_id = make_import(home, files)
    p = preview(client, import_id, mode="merge").json()
    assert p["conflicts"][0]["skills"] == ["lint"]  # ids
    settle = {"fields": {"description": "old"}}

    dropped = merge(
        client,
        import_id,
        mode="merge",
        resolutions={"lead": {**settle, "skills": {"lint": {"drop": True}}}},
    )
    assert dropped.status_code == 200
    assert (home / "drafts" / DRAFT / "skills/lead/lint/SKILL.md").read_text() == "mine"
    assert agent(dropped.json()["family"]["agents"], "lead")["skills"] == [
        {"id": "lint"}
    ]


def test_a_clashing_skill_can_be_kept_under_another_id(client, home) -> None:
    upload_skill(client, "lead", "lint", "mine")
    files = good_files(**{"skills/lead/lint/SKILL.md": "theirs"})
    fam = family()
    fam["agents"]["skills"] = [{"id": "lint"}]
    files["family.json"] = json.dumps(fam)
    import_id = make_import(home, files)
    settle = {"fields": {"description": "old"}}
    bad = merge(
        client,
        import_id,
        mode="merge",
        resolutions={"lead": {**settle, "skills": {"lint": {"alias": "lint"}}}},
    )
    assert bad.status_code == 422  # the id is taken
    ok = merge(
        client,
        import_id,
        mode="merge",
        resolutions={"lead": {**settle, "skills": {"lint": {"alias": "lint-2"}}}},
    )
    assert ok.status_code == 200
    base = home / "drafts" / DRAFT / "skills" / "lead"
    assert (base / "lint" / "SKILL.md").read_text() == "mine"
    assert (base / "lint-2" / "SKILL.md").read_text() == "theirs"
    assert agent(ok.json()["family"]["agents"], "lead")["skills"] == [
        {"id": "lint"},
        {"id": "lint-2"},
    ]


def test_an_identical_skill_is_not_a_clash(client, home) -> None:
    upload_skill(client, "lead", "lint", "same")
    fam = family()
    fam["agents"]["skills"] = [{"id": "lint"}]
    fam["agents"]["description"] = (
        "Coordinates the family and delegates work to sub-agents."
    )
    import_id = make_import(
        home,
        good_files(
            **{"family.json": json.dumps(fam), "skills/lead/lint/SKILL.md": "same"}
        ),
    )
    assert preview(client, import_id, mode="merge").json()["conflicts"] == []


def test_the_same_skill_combines_its_environment_names(client, home) -> None:
    upload_skill(client, "lead", "lint", "same")
    doc = client.get(URL).json()
    agent(doc["family"]["agents"], "lead")["skills"] = [
        {"id": "lint", "env": ["A", "B"]}
    ]
    assert client.put(URL, json=doc).status_code == 200
    fam = family()
    fam["agents"]["skills"] = [{"id": "lint", "env": ["B", "C"]}]
    fam["agents"]["description"] = (
        "Coordinates the family and delegates work to sub-agents."
    )
    import_id = make_import(
        home,
        good_files(
            **{"family.json": json.dumps(fam), "skills/lead/lint/SKILL.md": "same"}
        ),
    )
    r = client.post(
        f"{URL}/merge",
        json={
            "importId": import_id,
            "parentId": "lead",
            "mode": "merge",
            "resolutions": {},
        },
    )
    assert r.status_code == 200, r.text
    skills = agent(r.json()["family"]["agents"], "lead")["skills"]
    assert skills == [{"id": "lint", "env": ["A", "B", "C"]}]


def test_skills_of_new_agents_are_copied(client, home) -> None:
    fam = helper_family(skills=[{"id": "lint"}])
    import_id = make_import(
        home,
        helper_files(
            **{"family.json": json.dumps(fam), "skills/helper/lint/SKILL.md": "x"}
        ),
    )
    assert merge(client, import_id).status_code == 200
    assert (home / "drafts" / DRAFT / "skills/helper/lint/SKILL.md").is_file()


def test_a_second_import_goes_below_the_first_one(client, home) -> None:
    merge(client, make_import(home, helper_files(), "a" * 32))
    other = helper_family(id="other", name="other")
    r = merge(
        client,
        make_import(
            home, {"family.json": json.dumps(other), "prompts/other.md": "o"}, "b" * 32
        ),
    )
    kids = r.json()["family"]["agents"]["sub-agents"]
    assert [k["id"] for k in kids] == ["helper", "other"]


def test_unknown_parent_or_import_is_not_found(client, home) -> None:
    import_id = make_import(home, helper_files())
    assert preview(client, import_id, parent="nobody").status_code == 404
    assert preview(client, "c" * 32).status_code == 404
    assert merge(client, "c" * 32).status_code == 404


# ---- append: add the import's agents as new ones ---------------------------------------
def test_unpaired_agents_are_renamed_only_the_ids_the_draft_already_uses(
    client, home
) -> None:
    fam = family()
    fam["agents"]["skills"] = [{"id": "lint"}]
    import_id = make_import(
        home,
        good_files(
            **{"family.json": json.dumps(fam), "skills/lead/lint/SKILL.md": "s"}
        ),
    )
    p = preview(client, import_id).json()
    assert p["renamed"] == {"lead": "lead-2"} and p["conflicts"] == []
    assert sorted(p["added"]) == ["lead-2", "reviewer"] and p["merged"] == []
    r = merge(client, import_id)  # no resolutions needed
    assert r.status_code == 200, r.text
    body = r.json()
    root = body["family"]["agents"]
    second = agent(root, "lead-2")
    assert [a["id"] for a in root["sub-agents"]] == ["lead-2"]
    assert [a["id"] for a in second["sub-agents"]] == ["reviewer"]
    assert (
        second["description"] == "Splits the review."
    )  # the draft's lead is untouched
    assert root["description"].startswith("Coordinates")
    assert body["prompts"]["lead-2"] == "You lead." and "lead" not in body["prompts"]
    assert (home / "drafts" / DRAFT / "skills/lead-2/lint/SKILL.md").is_file()
    assert not (home / "imports" / import_id).exists()


def test_adding_the_same_import_twice_finds_free_ids(client, home) -> None:
    merge(client, make_import(home, good_files(), "a" * 32))
    p = preview(client, make_import(home, good_files(), "b" * 32))
    assert p.json()["renamed"] == {"lead": "lead-3", "reviewer": "reviewer-2"}


def test_without_id_clashes_renames_nothing(client, home) -> None:
    import_id = make_import(home, helper_files())
    assert preview(client, import_id).json()["renamed"] == {}


def test_a_draft_with_two_agents_of_one_id_cannot_take_an_import(client, home) -> None:
    doc = client.get(URL).json()
    twin = {**doc["family"]["agents"], "sub-agents": []}
    doc["family"]["agents"]["sub-agents"] = [twin]  # autosave allows it
    assert client.put(URL, json=doc).status_code == 200
    import_id = make_import(home, helper_files())
    r = preview(client, import_id)
    assert r.status_code == 422 and "share the id" in r.json()["error"]["message"]
    assert (home / "imports" / import_id).is_dir()


def test_adding_an_agent_named_like_a_sibling_is_flagged(client, home) -> None:
    first = make_import(home, helper_files(), "a" * 32)
    merge(client, first)  # lead now has a sub-agent named "helper"
    other = helper_family(id="other", name="Helper")  # same name, other id
    second = make_import(
        home, {"family.json": json.dumps(other), "prompts/other.md": "o"}, "b" * 32
    )
    p = preview(client, second).json()
    assert p["conflicts"] == []
    assert p["warnings"] == ["“lead” has two sub-agents named “Helper”."]


# ---- merging agents whose ids differ ---------------------------------------------------
def test_agents_with_different_ids_can_be_merged(client, home) -> None:
    fam = helper_family(skills=[{"id": "lint"}])
    fam["agents"]["sub-agents"] = [
        {
            "id": "sub",
            "name": "sub",
            "mcps": [],
            "skills": [],
            "sub-agents": [],
        }
    ]
    import_id = make_import(
        home,
        {
            "family.json": json.dumps(fam),
            "prompts/helper.md": "You help.",
            "prompts/sub.md": "Sub.",
            "skills/helper/lint/SKILL.md": "x",
        },
    )
    p = preview(client, import_id, mode="merge").json()
    assert p["added"] == ["sub"] and p["merged"] == ["lead"]
    (c,) = p["conflicts"]
    assert (c["agentId"], c["importedId"]) == ("lead", "helper")
    assert {f["field"] for f in c["fields"]} == {"name", "description"}

    answers = {"lead": {"fields": {"name": "old", "description": {"custom": "Both."}}}}
    r = merge(client, import_id, mode="merge", resolutions=answers)
    assert r.status_code == 200, r.text
    body = r.json()
    root = body["family"]["agents"]
    assert root["id"] == "lead" and root["description"] == "Both."
    assert [a["id"] for a in root["sub-agents"]] == ["sub"]  # the children came along
    assert "helper" not in body["prompts"] and body["prompts"]["lead"] == "You help."
    assert root["skills"] == [{"id": "lint"}]  # copied under the draft agent's id
    assert (home / "drafts" / DRAFT / "skills/lead/lint/SKILL.md").is_file()


def test_appending_gives_a_clashing_id_a_free_one(client, home) -> None:
    import_id = make_import(home, good_files())
    p = preview(client, import_id).json()
    assert p["renamed"] == {"lead": "lead-2"} and p["conflicts"] == []


def test_merging_into_an_unknown_agent_is_not_found(client, home) -> None:
    import_id = make_import(home, helper_files())
    assert preview(client, import_id, parent="ghost", mode="merge").status_code == 404


def test_a_mode_is_required(client, home) -> None:
    import_id = make_import(home, helper_files())
    body = {"importId": import_id, "parentId": "lead"}
    assert client.post(f"{URL}/merge/preview", json=body).status_code == 422
