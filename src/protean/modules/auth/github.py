"""GitHub calls for signing in: device code, token poll and the user profile."""

import httpx

from protean import config
from protean.core import network
from protean.modules.auth.schemas import DeviceCode, GithubUser, TokenPoll

DEVICE_CODE_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
USER_URL = "https://api.github.com/user"
JSON = {"Accept": "application/json"}


class GithubUnavailable(Exception):
    """Network failure or GitHub 5xx. Usually transient."""


class GithubError(Exception):
    """GitHub answered with an error (e.g. Device Flow not enabled, token revoked)."""

    def __init__(self, code: str, description: str = "") -> None:
        super().__init__(description or code)
        self.code = code
        self.description = description or code


async def _send(method: str, url: str, **kwargs) -> dict:
    try:
        resp = await network.client().request(method, url, **kwargs)
        body = resp.json()
    except httpx.HTTPError as exc:
        raise GithubUnavailable(str(exc) or type(exc).__name__) from exc
    except ValueError as exc:
        raise GithubUnavailable("GitHub returned a non-JSON response") from exc
    if resp.status_code >= 500:
        raise GithubUnavailable(f"GitHub returned {resp.status_code}")
    return body if isinstance(body, dict) else {}


async def request_device_code(scope: str) -> DeviceCode:
    body = await _send(
        "POST",
        DEVICE_CODE_URL,
        data={"client_id": config.GITHUB_CLIENT_ID, "scope": scope},
        headers=JSON,
    )
    if "error" in body:
        raise GithubError(body["error"], body.get("error_description", ""))
    try:
        return DeviceCode(
            device_code=body["device_code"],
            user_code=body["user_code"],
            verification_uri=body["verification_uri"],
            expires_in=int(body["expires_in"]),
            interval=int(body.get("interval", 5)),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise GithubUnavailable("Unexpected device-code response from GitHub") from exc


async def poll_token(device_code: str) -> TokenPoll:
    form = {
        "client_id": config.GITHUB_CLIENT_ID,
        "device_code": device_code,
        "grant_type": DEVICE_GRANT,
    }
    body = await _send("POST", TOKEN_URL, data=form, headers=JSON)
    if "access_token" in body:
        return TokenPoll(access_token=body["access_token"], scope=body.get("scope", ""))
    return TokenPoll(
        error=body.get("error", "unknown_error"), interval=body.get("interval")
    )


async def get_user(access_token: str) -> GithubUser:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = await _send("GET", USER_URL, headers=headers)
    if "login" not in body:
        raise GithubError(
            "bad_user_response",
            body.get("message", "Unexpected /user response from GitHub"),
        )
    return GithubUser(login=body["login"], avatar_url=body.get("avatar_url"))
