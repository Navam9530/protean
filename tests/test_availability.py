import httpx
import pytest
import respx
from helpers import good_files, parse_events

from protean.modules.auth import tokens
from protean.modules.profile import store

REPO = "https://api.github.com/repos/me/code-crew"


@pytest.fixture
def signed_in(home) -> None:
    store.set_github("me", None)
    tokens.save_token("tok", "public_repo")


def create_blank(client):
    return client.post("/api/drafts", json={"kind": "blank", "repo": "code-crew"})


def upload(client):
    parts = [
        ("files", (f"code-crew/{p}", str(c).encode())) for p, c in good_files().items()
    ]
    r = client.post("/api/imports/upload", files=parts)
    assert r.status_code == 200, r.text
    return parse_events(r.text)


def test_a_name_that_is_already_a_repo_is_refused(client, signed_in) -> None:
    with respx.mock as m:
        m.get(REPO).respond(200, json={"name": "code-crew"})
        r = create_blank(client)
    assert r.status_code == 409
    error = r.json()["error"]
    assert error["code"] == "already_exists" and "import it" in error["message"]
    assert client.get("/api/drafts").json() == []


def test_a_free_name_is_created(client, signed_in) -> None:
    with respx.mock as m:
        m.get(REPO).respond(404, json={})
        assert create_blank(client).status_code == 201


def test_github_trouble_does_not_stop_creation(client, signed_in) -> None:
    with respx.mock as m:
        m.get(REPO).mock(side_effect=httpx.ConnectError("offline"))
        assert create_blank(client).status_code == 201


def test_without_a_github_sign_in_github_is_not_asked(client, home) -> None:
    store.set_github("me", None)  # a profile, but no token
    with respx.mock:  # any call would fail: nothing is mocked
        assert create_blank(client).status_code == 201


def test_an_uploaded_folder_named_like_a_repo_is_refused(
    client, signed_in, home
) -> None:
    with respx.mock as m:
        m.get(REPO).respond(200, json={"name": "code-crew"})
        events = upload(client)
    assert events[-1][0] == "error" and events[-1][1]["code"] == "already_exists"
    assert not any((home / "imports").iterdir())


def test_an_uploaded_folder_with_a_free_name_is_imported(client, signed_in) -> None:
    with respx.mock as m:
        m.get(REPO).respond(404, json={})
        assert upload(client)[-1][0] == "done"
