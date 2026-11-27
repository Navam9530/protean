import itertools
import json
import stat
from pathlib import Path

import httpx
import respx

from protean.integrations.github.oauth import DEVICE_CODE_URL, TOKEN_URL, USER_URL

DEVICE = {
    "device_code": "dev-123",
    "user_code": "ABCD-1234",
    "verification_uri": "https://github.com/login/device",
    "expires_in": 900,
    "interval": 0,
}
TOKEN = "gho_supersecrettoken"
PENDING = httpx.Response(200, json={"error": "authorization_pending"})
GRANTED = httpx.Response(200, json={"access_token": TOKEN, "scope": "public_repo"})
USER = {"login": "navateja", "avatar_url": "https://avatars.githubusercontent.com/u/1"}


def then_pending(*first: httpx.Response):
    """Scripted poll results, then authorization_pending forever (the backend keeps polling)."""
    return itertools.chain(first, itertools.repeat(PENDING))


def mock_github(
    m: respx.MockRouter, polls: list[httpx.Response], user: dict = USER
) -> dict[str, respx.Route]:
    return {
        "device": m.post(DEVICE_CODE_URL).respond(json=DEVICE),
        "token": m.post(TOKEN_URL).mock(side_effect=then_pending(*polls)),
        "user": m.get(USER_URL).respond(json=user),
    }


def test_happy_path(client, home: Path, wait_for) -> None:
    with respx.mock(assert_all_called=False) as m:
        routes = mock_github(m, [PENDING, PENDING, GRANTED])

        start = client.post("/api/auth/github/device")
        assert start.status_code == 200
        assert start.json()["userCode"] == "ABCD-1234"
        assert start.json()["verificationUri"] == "https://github.com/login/device"

        done = wait_for(client, "authorized")

    assert done["profile"] == {
        "owner": "navateja",
        "source": "github",
        "avatarUrl": USER["avatar_url"],
    }
    assert routes["token"].call_count == 3
    assert (
        routes["user"].calls.last.request.headers["authorization"] == f"Bearer {TOKEN}"
    )

    token_file = home / "keys" / "github.json"
    assert json.loads(token_file.read_text())["access_token"] == TOKEN
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
    assert stat.S_IMODE((home / "keys").stat().st_mode) == 0o700

    # The token must never be exposed through the API.
    for path in ("/api/profile", "/api/auth/github/status"):
        assert TOKEN not in client.get(path).text
    assert client.get("/api/profile").json()["owner"] == "navateja"


def test_start_requests_public_repo_scope(client) -> None:
    with respx.mock(assert_all_called=False) as m:
        routes = mock_github(m, [])
        client.post("/api/auth/github/device")
        body = routes["device"].calls.last.request.content.decode()
    assert "client_id=Ov23licFzZUlfSOQC8iY" in body
    assert "scope=public_repo" in body


def test_start_is_idempotent_while_pending(client) -> None:
    with respx.mock(assert_all_called=False) as m:
        routes = mock_github(m, [])
        a = client.post("/api/auth/github/device").json()
        b = client.post("/api/auth/github/device").json()
    assert a["userCode"] == b["userCode"]
    assert routes["device"].call_count == 1
    assert client.get("/api/auth/github/status").json()["state"] == "pending"


def test_status_pending_includes_code(client) -> None:
    with respx.mock(assert_all_called=False) as m:
        mock_github(m, [])
        client.post("/api/auth/github/device")
        body = client.get("/api/auth/github/status").json()
    assert body["state"] == "pending"
    assert body["userCode"] == "ABCD-1234"
    assert 0 < body["expiresIn"] <= 900


def test_slow_down_is_handled(client, wait_for) -> None:
    slow = httpx.Response(200, json={"error": "slow_down", "interval": 0})
    with respx.mock(assert_all_called=False) as m:
        mock_github(m, [slow, GRANTED])
        client.post("/api/auth/github/device")
        wait_for(client, "authorized")


def test_denied(client, home: Path, wait_for) -> None:
    with respx.mock(assert_all_called=False) as m:
        mock_github(m, [httpx.Response(200, json={"error": "access_denied"})])
        client.post("/api/auth/github/device")
        wait_for(client, "denied")
    assert not (home / "keys" / "github.json").exists()
    assert client.get("/api/profile").json()["source"] is None  # still no choice made


def test_expired(client, wait_for) -> None:
    with respx.mock(assert_all_called=False) as m:
        mock_github(m, [httpx.Response(200, json={"error": "expired_token"})])
        client.post("/api/auth/github/device")
        wait_for(client, "expired")


def test_unknown_github_error_surfaces_as_error_state(client, wait_for) -> None:
    with respx.mock(assert_all_called=False) as m:
        mock_github(
            m, [httpx.Response(200, json={"error": "incorrect_client_credentials"})]
        )
        client.post("/api/auth/github/device")
        body = wait_for(client, "error")
    assert "incorrect_client_credentials" in body["error"]


def test_can_retry_after_denied(client, wait_for) -> None:
    with respx.mock(assert_all_called=False) as m:
        mock_github(m, [httpx.Response(200, json={"error": "access_denied"}), GRANTED])
        client.post("/api/auth/github/device")
        wait_for(client, "denied")
        assert client.post("/api/auth/github/device").status_code == 200
        wait_for(client, "authorized")


def test_device_flow_disabled_returns_502(client) -> None:
    with respx.mock(assert_all_called=False) as m:
        m.post(DEVICE_CODE_URL).respond(
            json={
                "error": "device_flow_disabled",
                "error_description": "Device Flow must be enabled",
            }
        )
        r = client.post("/api/auth/github/device")
    assert r.status_code == 502
    assert r.json()["error"] == {
        "code": "github_error",
        "message": "Device Flow must be enabled",
    }


def test_github_unreachable_returns_502(client) -> None:
    with respx.mock(assert_all_called=False) as m:
        m.post(DEVICE_CODE_URL).mock(side_effect=httpx.ConnectError("boom"))
        r = client.post("/api/auth/github/device")
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "github_unreachable"


def test_transient_poll_failures_are_retried(client, wait_for) -> None:
    with respx.mock(assert_all_called=False) as m:
        mock_github(m, [httpx.Response(502), httpx.Response(503), GRANTED])
        client.post("/api/auth/github/device")
        wait_for(client, "authorized")


def test_cancel_stops_polling(client) -> None:
    with respx.mock(assert_all_called=False) as m:
        mock_github(m, [])
        client.post("/api/auth/github/device")
        assert client.post("/api/auth/github/cancel").json()["state"] == "idle"
    assert client.get("/api/auth/github/status").json()["state"] == "idle"


def test_already_signed_in_is_409(client, wait_for) -> None:
    with respx.mock(assert_all_called=False) as m:
        mock_github(m, [GRANTED])
        client.post("/api/auth/github/device")
        wait_for(client, "authorized")
        r = client.post("/api/auth/github/device")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "already_signed_in"


def test_token_without_scope_is_asked_again(client, home) -> None:
    """A token from before scopes were requested cannot publish: sign in again to upgrade."""
    (home / "keys").mkdir(exist_ok=True)
    (home / "keys" / "github.json").write_text(
        json.dumps({"access_token": "gho_old", "scope": ""})
    )
    (home / "profile.json").write_text(
        json.dumps({"source": "github", "github_login": "navateja"})
    )
    with respx.mock(assert_all_called=False) as m:
        mock_github(m, [])
        assert client.post("/api/auth/github/device").status_code == 200


def test_skip_is_refused_when_signed_in(client, wait_for) -> None:
    with respx.mock(assert_all_called=False) as m:
        mock_github(m, [GRANTED])
        client.post("/api/auth/github/device")
        wait_for(client, "authorized")
    assert client.post("/api/profile/skip-github").status_code == 409


def test_logout_reverts_to_hostname_and_deletes_token(
    client, home: Path, wait_for
) -> None:
    owner = client.post("/api/profile/skip-github").json()[
        "owner"
    ]  # local owner captured first
    with respx.mock(assert_all_called=False) as m:
        mock_github(m, [GRANTED])
        client.post("/api/auth/github/device")
        wait_for(client, "authorized")
    assert (home / "keys" / "github.json").exists()

    out = client.post("/api/auth/github/logout")
    assert out.status_code == 200
    assert out.json() == {
        "owner": owner,
        "source": "hostname",
        "avatarUrl": None,
    }
    assert not (home / "keys" / "github.json").exists()
    assert client.get("/api/auth/github/status").json()["state"] == "idle"


def test_logout_when_signed_out_is_harmless(client) -> None:
    assert client.post("/api/auth/github/logout").status_code == 200


def test_login_survives_restart(home: Path, client, wait_for) -> None:
    from fastapi.testclient import TestClient

    from protean.app import create_app

    with respx.mock(assert_all_called=False) as m:
        mock_github(m, [GRANTED])
        client.post("/api/auth/github/device")
        wait_for(client, "authorized")
    with TestClient(create_app(), base_url="http://localhost") as restarted:
        assert restarted.get("/api/auth/github/status").json()["state"] == "authorized"
        assert restarted.get("/api/profile").json()["owner"] == "navateja"


def test_cross_site_post_is_blocked(client) -> None:
    r = client.post(
        "/api/auth/github/logout", headers={"Origin": "https://evil.example"}
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden_origin"
    assert (
        client.post(
            "/api/auth/github/logout", headers={"Origin": "http://localhost:9530"}
        ).status_code
        == 200
    )


def test_unknown_host_is_rejected(client) -> None:
    assert (
        client.get("/api/profile", headers={"Host": "evil.example"}).status_code == 400
    )
