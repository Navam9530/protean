"""The one way Protean calls the GitHub API.

Every call goes through `request`, so the headers, the user's token and the failures (GitHub down,
the rate limit, a token that was revoked) are handled in one place. The token never leaves the
backend. Commits made with it are attributed to that account by GitHub.
"""

from typing import Literal

import httpx

from protean.core import network
from protean.core.errors import (
    GITHUB_UNREACHABLE,
    NOT_SIGNED_IN,
    RATE_LIMITED,
    AppError,
)
from protean.identity import tokens

API = "https://api.github.com"
JSON = "application/vnd.github+json"
RAW = "application/vnd.github.raw+json"
VERSION = "2022-11-28"


async def request(
    method: str,
    path: str,
    *,
    auth: Literal["optional", "required"] = "optional",
    accept: str = JSON,
    params: dict | None = None,
    body: dict | None = None,
    stream: bool = False,
) -> httpx.Response:
    """One call to `API + path`. Returns the response for any status the caller may handle itself
    (404, 409, 422 ...); GitHub being down, the rate limit and a lost sign-in are raised.

    auth="optional": the token is sent when there is one (higher rate limits). If GitHub rejects
    it, it is dropped and the call is retried anonymously, so browsing never breaks on a stale
    sign-in. auth="required": no token is a 401 `not_signed_in`, and so is a rejected one.
    A streamed response must be closed by the caller.
    """
    token = tokens.access_token()
    if auth == "required" and not token:
        raise AppError(401, NOT_SIGNED_IN, "Sign in with GitHub to publish.")
    while True:
        headers = {"Accept": accept, "X-GitHub-Api-Version": VERSION}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        http = network.client()
        try:
            resp = await http.send(
                http.build_request(
                    method, f"{API}{path}", params=params, json=body, headers=headers
                ),
                stream=stream,
            )
        except httpx.HTTPError as exc:
            raise AppError(
                502,
                GITHUB_UNREACHABLE,
                "Could not reach GitHub. Check your connection.",
            ) from exc
        if resp.status_code == 401 and token:
            await resp.aclose()
            tokens.drop_token()
            if auth == "required":
                raise AppError(
                    401, NOT_SIGNED_IN, "GitHub rejected your sign-in. Sign in again."
                )
            token = None
            continue
        break
    limited = resp.status_code == 429 or (
        resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0"
    )
    if limited:
        await resp.aclose()
        hint = "" if token else " Signing in with GitHub raises the limit."
        raise AppError(
            429,
            RATE_LIMITED,
            f"GitHub rate limit reached. Try again in a minute.{hint}",
        )
    if resp.status_code >= 500:
        await resp.aclose()
        raise AppError(502, GITHUB_UNREACHABLE, f"GitHub returned {resp.status_code}.")
    return resp
