import pytest

from protean.modules.reveal import service


@pytest.fixture
def opened(monkeypatch) -> list:
    calls: list = []
    monkeypatch.setattr(service, "open_folder", calls.append)
    return calls


def test_a_draft_folder_is_opened(client, home, opened) -> None:
    (home / "drafts" / "me_crew").mkdir(parents=True)
    r = client.post("/api/reveal", json={"scope": "draft", "name": "me_crew"})
    assert r.status_code == 204 and opened == [home / "drafts" / "me_crew"]


def test_a_skill_folder_is_opened(client, home, opened) -> None:
    skill = home / "families" / "me_crew" / "skills" / "lead" / "review"
    skill.mkdir(parents=True)
    body = {
        "scope": "family",
        "name": "me_crew",
        "kind": "skills",
        "agentId": "lead",
        "itemId": "review",
    }
    assert client.post("/api/reveal", json=body).status_code == 204
    assert opened == [skill]


def test_a_missing_folder_is_not_found(client, opened) -> None:
    r = client.post("/api/reveal", json={"scope": "draft", "name": "me_nope"})
    assert r.status_code == 404 and opened == []


@pytest.mark.parametrize(
    "body",
    [
        {
            "scope": "draft",
            "name": "me_crew",
            "kind": "skills",
        },  # kind, agent and item go together
        {"scope": "draft", "name": "../etc"},
        {
            "scope": "draft",
            "name": "me_crew",
            "kind": "skills",
            "agentId": "..",
            "itemId": "x",
        },
        {"scope": "draft", "name": "me_crew", "path": "/etc"},
    ],
)
def test_bad_requests_are_refused(client, opened, body) -> None:
    assert client.post("/api/reveal", json=body).status_code == 422 and opened == []
