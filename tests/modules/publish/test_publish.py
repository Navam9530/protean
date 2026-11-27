import base64
import datetime
import itertools
import json

import httpx
import pytest
import respx
from helpers import good_files, make_import, parse_events

from protean.family import published
from protean.identity import profile, tokens

NAME = "me_code-crew"
API = "https://api.github.com"
REPO = f"{API}/repos/me/code-crew"


@pytest.fixture(autouse=True)
def saved(client, home) -> None:
    """One saved family owned by the signed-in user "me", made the real way."""
    profile.set_github("me", None)
    tokens.save_token("tok", "public_repo")
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
    assert parse_events(client.post(f"/api/drafts/{NAME}/save").text)[-1][0] == "done"


class Github:
    """A fake GitHub that records the writes. `exists` says whether the repo is there."""

    def __init__(self, m: respx.MockRouter, *, exists: bool, topics: list[str]) -> None:
        self.m = m
        self.blobs: dict[str, bytes] = {}
        self.tree: list[dict] = []
        self.commit: dict = {}
        self.topics: list[str] | None = None
        self.created: dict | None = None
        self.tag_exists = False
        self.tags_made: list[str] = []
        self.description: str | None = None
        self.branch_moved = False
        self.head_tree = "t1"
        counter = itertools.count(1)
        repo = {
            "html_url": "https://github.com/me/code-crew",
            "default_branch": "main",
            "owner": {"login": "me"},
            "topics": topics,
        }
        self.remote = [
            {"path": "README.md", "mode": "100644", "type": "blob", "sha": "oldreadme"},
            {"path": "LICENSE", "mode": "100644", "type": "blob", "sha": "oldlicense"},
            {"path": "old.txt", "mode": "100644", "type": "blob", "sha": "oldfile"},
        ]

        def blob(request: httpx.Request) -> httpx.Response:
            sha = f"b{next(counter)}"
            self.blobs[sha] = base64.b64decode(json.loads(request.content)["content"])
            return httpx.Response(201, json={"sha": sha})

        def new_tree(request: httpx.Request) -> httpx.Response:
            self.tree = json.loads(request.content)["tree"]
            same = self.tree == self.remote_as_tree()
            return httpx.Response(201, json={"sha": "t1" if same else "t2"})

        def new_commit(request: httpx.Request) -> httpx.Response:
            self.commit = json.loads(request.content)
            return httpx.Response(201, json={"sha": "c2"})

        def move(request: httpx.Request) -> httpx.Response:
            return httpx.Response(422 if self.branch_moved else 200, json={})

        def tag(request: httpx.Request) -> httpx.Response:
            self.tags_made.append(json.loads(request.content)["ref"])
            return httpx.Response(201, json={})

        def tag_lookup(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200 if self.tag_exists else 404, json={})

        def topics_put(request: httpx.Request) -> httpx.Response:
            self.topics = json.loads(request.content)["names"]
            return httpx.Response(200, json={})

        def describe(request: httpx.Request) -> httpx.Response:
            self.description = json.loads(request.content)["description"]
            return httpx.Response(200, json={})

        def create(request: httpx.Request) -> httpx.Response:
            self.created = json.loads(request.content)
            return httpx.Response(201, json={**repo, "topics": []})

        m.get(REPO).mock(
            return_value=httpx.Response(200, json=repo)
            if exists
            else httpx.Response(404, json={})
        )
        m.post(f"{API}/user/repos").mock(side_effect=create)
        m.get(f"{REPO}/git/ref/heads/main").respond(json={"object": {"sha": "c1"}})
        m.get(f"{REPO}/git/commits/c1").mock(
            side_effect=lambda _: httpx.Response(
                200, json={"tree": {"sha": self.head_tree}}
            )
        )
        m.get(f"{REPO}/git/trees/t1").mock(
            side_effect=lambda _: httpx.Response(200, json={"tree": self.remote})
        )
        m.post(f"{REPO}/git/blobs").mock(side_effect=blob)
        m.post(f"{REPO}/git/trees").mock(side_effect=new_tree)
        m.post(f"{REPO}/git/commits").mock(side_effect=new_commit)
        m.patch(f"{REPO}/git/refs/heads/main").mock(side_effect=move)
        m.post(f"{REPO}/git/refs").mock(side_effect=tag)
        m.get(f"{REPO}/git/ref/tags/v0.1.0").mock(side_effect=tag_lookup)
        m.patch(REPO).mock(side_effect=describe)
        m.put(f"{REPO}/topics").mock(side_effect=topics_put)
        m.get(f"{API}/licenses/mit").respond(
            json={"body": "MIT License\n\nCopyright (c) [year] [fullname]"}
        )
        m.get(f"{API}/licenses/apache-2.0").respond(
            json={"body": "Apache License\nVersion 2.0"}
        )

    def remote_as_tree(self) -> list[dict]:
        return []  # a publish never equals the fake remote, unless a test sets it

    def paths(self) -> list[str]:
        return [e["path"] for e in self.tree]

    def entry(self, path: str) -> dict:
        return next(e for e in self.tree if e["path"] == path)

    def text(self, path: str) -> str:
        return self.blobs[self.entry(path)["sha"]].decode()


@pytest.fixture
def gh():
    with respx.mock(assert_all_called=False) as m:

        def make(*, exists: bool = True, topics=("protean", "agents-marketplace")):
            return Github(m, exists=exists, topics=list(topics))

        yield make


def publish(client, body: dict | None = None) -> list:
    r = client.post(f"/api/families/{NAME}/publish", json=body)
    assert r.status_code == 200, r.text
    return parse_events(r.text)


def failure(events) -> dict:
    assert events[-1][0] == "error", events[-3:]
    return events[-1][1]


def done(events) -> dict:
    assert events[-1][0] == "done", events[-3:]
    return events[-1][1]


# ---- a first publish ------------------------------------------------------------------
def test_a_first_publish_creates_the_repo_and_everything_in_it(client, gh) -> None:
    g = gh(exists=False)
    events = publish(client, {"description": "Reviews a diff."})
    result = done(events)
    assert result == {
        "url": "https://github.com/me/code-crew",
        "commit": "c2",
        "tag": "v0.1.0",
        "familyVersion": "0.1.0",
        "listed": True,
    }
    assert g.created == {
        "name": "code-crew",
        "description": "Reviews a diff.",
        "private": False,
        "auto_init": True,
    }
    assert sorted(g.paths()) == [
        "LICENSE",
        "README.md",
        "family.json",
        "prompts/lead.md",
        "prompts/reviewer.md",
    ]
    assert g.text("README.md") == "# Code crew"  # the family folder's own file
    assert g.topics == ["protean", "agents-marketplace"]
    stages = [d["id"] for e, d in events if e == "stage" and d["state"] == "running"]
    assert stages == ["check", "repo", "upload", "commit", "tag", "topics"]


def test_the_commit_sits_on_the_head_and_names_no_author(client, gh) -> None:
    g = gh(exists=False)
    publish(client)
    assert g.commit == {"message": "Publish v0.1.0", "tree": "t2", "parents": ["c1"]}


def test_a_first_publish_without_a_readme_pushes_an_empty_one(client, gh, home) -> None:
    g = gh(exists=False)
    (home / "families" / NAME / "README.md").unlink()
    publish(client)
    assert g.text("README.md") == ""


# ---- updating -------------------------------------------------------------------------
def test_an_update_keeps_the_repos_readme_and_license_when_not_sent(client, gh) -> None:
    g = gh()
    done(publish(client))
    assert g.created is None
    assert g.entry("README.md")["sha"] == "oldreadme"
    assert g.entry("LICENSE")["sha"] == "oldlicense"
    assert "old.txt" not in g.paths()  # the snapshot is replaced as a whole


def test_a_changed_readme_replaces_the_repos_one(client, gh, home) -> None:
    g = gh()
    done(publish(client, {"readme": "# New words"}))
    assert g.text("README.md") == "# New words"
    assert g.entry("LICENSE")["sha"] == "oldlicense"
    saved = (home / "families" / NAME / "README.md").read_text()
    assert saved == "# New words"  # remembered for the next form


def test_a_chosen_license_is_filled_in_with_the_year_and_the_owner(client, gh) -> None:
    g = gh()
    done(publish(client, {"license": "mit"}))
    year = datetime.date.today().year
    assert g.text("LICENSE") == f"MIT License\n\nCopyright (c) {year} me"
    assert client.get(f"/api/families/{NAME}/publish").json()["license"] == "mit"


def test_nothing_changed_makes_no_commit_but_still_tags(client, gh) -> None:
    g = gh()
    g.remote_as_tree = lambda: g.tree  # the new snapshot equals the one on GitHub
    events = publish(client)
    assert done(events)["commit"] == "c1"
    assert g.commit == {}
    assert ("stage", {"id": "commit", "state": "done", "note": "no changes"}) in events


def test_a_readme_update_of_the_same_version_keeps_its_tag(client, gh) -> None:
    g = gh()
    done(publish(client))  # records version 0.1.0 as published by Protean
    g.tag_exists = True
    g.tags_made.clear()
    events = publish(client, {"readme": "# Better words"})
    assert done(events)["tag"] == "v0.1.0"
    assert g.tags_made == []  # the tag stays where it is
    assert not [d for e, d in events if e == "warning"]


def test_a_tag_protean_did_not_publish_is_never_reused(client, gh) -> None:
    g = gh()
    g.tag_exists = True  # no record of publishing 0.1.0 from here
    error = failure(publish(client))
    assert (
        error["code"] == "conflict" and "Change the family version" in error["message"]
    )
    assert g.blobs == {} and g.commit == {}


def test_a_repo_that_lost_the_marketplace_topic_is_pushed_but_not_re_listed(
    client, gh
) -> None:
    g = gh(topics=["protean"])
    result = done(publish(client))
    assert result["listed"] is False
    assert g.topics is None  # never added without the user's say-so


# ---- refusals ---------------------------------------------------------------------------
def test_a_repo_not_made_by_protean_is_refused(client, gh) -> None:
    g = gh(topics=["agents-marketplace"])
    error = failure(publish(client))
    assert error["code"] == "not_protean_repo" and "add the topic" in error["message"]
    assert g.blobs == {} and g.commit == {}


def test_a_draft_blocks_publishing(client, gh) -> None:
    g = gh()
    client.post("/api/drafts", json={"kind": "family", "name": NAME})
    assert failure(publish(client))["code"] == "draft_exists"
    assert g.blobs == {}


def test_only_your_own_families_can_be_published(client, gh) -> None:
    gh()
    profile.set_github("someone", None)
    assert failure(publish(client))["code"] == "not_owner"


def test_publishing_needs_a_github_sign_in(client, gh) -> None:
    gh()
    tokens.delete_token()
    assert failure(publish(client))["code"] == "not_signed_in"


def test_a_branch_that_moved_is_never_overwritten(client, gh) -> None:
    g = gh()
    g.branch_moved = True
    assert failure(publish(client))["code"] == "conflict"


def test_an_unknown_family_is_not_found(client, gh) -> None:
    gh()
    r = client.post("/api/families/me_nothing/publish")
    assert parse_events(r.text)[-1][1]["code"] == "not_found"


def test_a_rejected_token_is_dropped(client, gh) -> None:
    g = gh()
    g.m.get(REPO).respond(401, json={})
    assert failure(publish(client))["code"] == "not_signed_in"
    assert tokens.load_token() is None


def test_an_odd_license_or_huge_readme_is_a_422(client, gh) -> None:
    gh()
    assert (
        client.post(
            f"/api/families/{NAME}/publish", json={"license": "gpl"}
        ).status_code
        == 422
    )
    big = {"readme": "x" * 200_001}
    assert client.post(f"/api/families/{NAME}/publish", json=big).status_code == 422


# ---- the form's starting values ---------------------------------------------------------
def test_the_form_starts_from_the_readme_and_license_kind(client) -> None:
    body = client.get(f"/api/families/{NAME}/publish").json()
    assert body == {  # the fixture's LICENSE says only "MIT"
        "description": "",
        "readme": "# Code crew",
        "license": "other",
    }
    assert "family" not in body and "prompts" not in body


def test_the_form_of_an_unknown_family_is_404(client) -> None:
    assert client.get("/api/families/me_nothing/publish").status_code == 404


# ---- what was last published ------------------------------------------------------------
def summary(client) -> dict:
    (item,) = client.get("/api/families").json()
    return item


def test_a_family_is_unpublished_until_it_is_published(client, gh) -> None:
    gh()
    assert summary(client)["publishedFamilyVersion"] is None
    done(publish(client))
    assert summary(client)["publishedFamilyVersion"] == "0.1.0"


def test_a_failed_publish_records_nothing(client, gh) -> None:
    gh(topics=["agents-marketplace"])  # not made by Protean
    failure(publish(client))
    assert summary(client)["publishedFamilyVersion"] is None


def test_deleting_the_family_forgets_what_was_published(client, gh) -> None:
    gh()
    done(publish(client))
    client.delete(f"/api/families/{NAME}")
    assert published.version(NAME) is None


# ---- unpublish and list again --------------------------------------------------------------
def test_unpublish_removes_only_the_marketplace_topic(client, gh) -> None:
    g = gh()
    done(publish(client))
    r = client.delete(f"/api/families/{NAME}/publish")
    assert r.status_code == 200 and r.json() == {"listed": False}
    assert g.topics == ["protean"]
    assert summary(client)["listed"] is False
    assert (
        summary(client)["publishedFamilyVersion"] == "0.1.0"
    )  # still published, just unlisted


def test_listing_again_adds_the_topic_back(client, gh) -> None:
    g = gh(topics=["protean"])
    done(publish(client))
    assert summary(client)["listed"] is False
    r = client.post(f"/api/families/{NAME}/publish/topic")
    assert r.json() == {"listed": True}
    assert g.topics == ["protean", "agents-marketplace"]
    assert summary(client)["listed"] is True


def test_listing_a_repo_already_listed_changes_nothing(client, gh) -> None:
    g = gh()
    assert client.post(f"/api/families/{NAME}/publish/topic").json() == {"listed": True}
    assert g.topics is None


def test_unpublish_never_touches_a_repo_made_elsewhere(client, gh) -> None:
    g = gh(topics=["agents-marketplace"])
    r = client.delete(f"/api/families/{NAME}/publish")
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_protean_repo"
    assert g.topics is None


def test_unpublish_of_a_missing_repo_is_404(client, gh) -> None:
    gh(exists=False)
    r = client.delete(f"/api/families/{NAME}/publish")
    assert r.status_code == 404 and r.json()["error"]["code"] == "repo_not_found"


def test_unpublish_needs_the_owner(client, gh) -> None:
    gh()
    profile.set_github("someone", None)
    assert client.delete(f"/api/families/{NAME}/publish").status_code == 403
    tokens.delete_token()
    assert client.post(f"/api/families/{NAME}/publish/topic").status_code in (401, 403)


# ---- the repo's About text ------------------------------------------------------------------
def test_a_description_is_set_on_an_existing_repo_and_remembered(client, gh) -> None:
    g = gh()
    done(publish(client, {"description": "Reviews diffs."}))
    assert g.description == "Reviews diffs."
    assert (
        client.get(f"/api/families/{NAME}/publish").json()["description"]
        == "Reviews diffs."
    )


def test_a_description_left_out_is_not_touched_and_the_last_one_is_kept(
    client, gh
) -> None:
    g = gh()
    done(publish(client, {"description": "Reviews diffs."}))
    g.description = None
    g.tag_exists = True
    done(publish(client, {"readme": "# x"}))
    assert g.description is None  # nothing sent to GitHub
    assert (
        client.get(f"/api/families/{NAME}/publish").json()["description"]
        == "Reviews diffs."
    )


def test_an_overlong_description_is_a_422(client, gh) -> None:
    gh()
    r = client.post(f"/api/families/{NAME}/publish", json={"description": "x" * 351})
    assert r.status_code == 422
