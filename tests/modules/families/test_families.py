import pytest
from helpers import good_files, make_import, parse_events

from protean.identity import profile

NAME = "me_code-crew"


@pytest.fixture(autouse=True)
def saved(client, home) -> None:
    """One saved family, made the real way: import, draft, save."""
    profile.set_github("me", None)
    make_import(home, good_files())
    client.post(
        "/api/drafts",
        json={
            "kind": "import",
            "importId": "a" * 32,
            "owner": "me",
            "repo": "code-crew",
        },
    )
    events = parse_events(client.post(f"/api/drafts/{NAME}/save").text)
    assert events[-1][0] == "done"


def test_the_list_shows_saved_families(client) -> None:
    (item,) = client.get("/api/families").json()
    assert item["name"] == NAME and item["familyVersion"] == "0.1.0"
    assert item["agentCount"] == 2


def test_the_list_carries_what_a_card_shows(client) -> None:
    (item,) = client.get("/api/families").json()
    assert item["family"]["agents"]["id"] == "lead"  # family.json, for the minimap
    assert item["description"] == "Splits the review."  # the root agent's
    assert item["size"] > 0  # family.json, prompts and the rest of what is kept
    assert item["chatCount"] == 0  # until chats exist
    assert item["accessedAt"] == item["updatedAt"]  # until opens are tracked


def test_a_family_is_read_with_its_prompts(client) -> None:
    body = client.get(f"/api/families/{NAME}").json()
    assert body["name"] == NAME and body["family"]["familyVersion"] == "0.1.0"
    assert body["prompts"] == {"lead": "You lead.", "reviewer": "You review."}


def test_an_unknown_family_is_not_found(client) -> None:
    r = client.get("/api/families/me_nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_delete_removes_only_the_saved_family(client, home) -> None:
    client.post("/api/drafts", json={"kind": "family", "name": NAME})
    assert client.delete(f"/api/families/{NAME}").status_code == 204
    assert client.get("/api/families").json() == []
    assert (home / "drafts" / NAME).is_dir()  # the draft is a separate thing
    assert client.delete(f"/api/families/{NAME}").status_code == 204  # already gone


def test_a_name_that_is_not_owner_repo_is_refused(client) -> None:
    assert client.get("/api/families/not-a-name").status_code == 422


def test_a_family_is_exported_as_a_zip(client) -> None:
    import io
    import zipfile

    r = client.get(f"/api/families/{NAME}/export")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert f"{NAME}.zip" in r.headers["content-disposition"]
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert f"{NAME}/family.json" in names and f"{NAME}/prompts/lead.md" in names


def test_an_unknown_family_cannot_be_exported(client) -> None:
    assert client.get("/api/families/me_nope/export").status_code == 404
