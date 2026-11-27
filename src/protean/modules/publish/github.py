"""The GitHub calls that create or update a repo. Protean never deletes anything on GitHub.

They need the signed-in user's token, and commits made with it are attributed to that account
by GitHub, so no author name or email is ever sent. A token GitHub rejects is dropped.
"""

import asyncio
import base64

import httpx

from protean.core import network
from protean.core.errors import (
    ALREADY_EXISTS,
    CONFLICT,
    GITHUB_ERROR,
    GITHUB_UNREACHABLE,
    NOT_SIGNED_IN,
    RATE_LIMITED,
    AppError,
)
from protean.modules.auth import login

API = "https://api.github.com"
EMPTY_REPO_RETRIES = 6  # a repo made a moment ago may not show its first commit yet


async def _call(method: str, path: str, body: dict | None = None) -> httpx.Response:
    """One authenticated call. Returns the response for any status the caller may handle
    itself (4xx); a lost sign-in, the rate limit and GitHub being down are raised."""
    token = login.access_token()
    if not token:
        raise AppError(401, NOT_SIGNED_IN, "Sign in with GitHub to publish.")
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        resp = await network.client().request(
            method, f"{API}{path}", json=body, headers=headers
        )
    except httpx.HTTPError as exc:
        raise AppError(
            502, GITHUB_UNREACHABLE, "Could not reach GitHub. Check your connection."
        ) from exc
    if resp.status_code == 401:
        login.drop_token()
        raise AppError(
            401, NOT_SIGNED_IN, "GitHub rejected your sign-in. Sign in again."
        )
    if resp.status_code == 429 or (
        resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0"
    ):
        raise AppError(
            429, RATE_LIMITED, "GitHub rate limit reached. Try again in a minute."
        )
    if resp.status_code >= 500:
        raise AppError(502, GITHUB_UNREACHABLE, f"GitHub returned {resp.status_code}.")
    return resp


def _fail(resp: httpx.Response, what: str) -> AppError:
    try:
        reason = resp.json().get("message", "")
    except ValueError:
        reason = ""
    return AppError(
        502, GITHUB_ERROR, f"Could not {what} ({resp.status_code}). {reason}".strip()
    )


async def get_repo(owner: str, repo: str) -> dict | None:
    """The repo (with its `topics` and `default_branch`), or None when it does not exist."""
    resp = await _call("GET", f"/repos/{owner}/{repo}")
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise _fail(resp, "read the repository")
    return resp.json()


async def create_repo(name: str, about: str) -> dict:
    """A public repo under the signed-in account, with a first commit to build on."""
    body = {
        "name": name,
        "description": about,
        "private": False,
        "auto_init": True,
    }
    resp = await _call("POST", "/user/repos", body)
    if resp.status_code == 201:
        return resp.json()
    if resp.status_code == 422 and "already exists" in resp.text:
        raise AppError(
            409, ALREADY_EXISTS, f"A repository named “{name}” already exists."
        )
    raise _fail(resp, "create the repository")


async def set_description(owner: str, repo: str, text: str) -> None:
    resp = await _call("PATCH", f"/repos/{owner}/{repo}", {"description": text})
    if resp.status_code != 200:
        raise _fail(resp, "update the repository description")


async def tag_exists(owner: str, repo: str, tag: str) -> bool:
    resp = await _call("GET", f"/repos/{owner}/{repo}/git/ref/tags/{tag}")
    if resp.status_code == 200:
        return True
    if resp.status_code == 404:
        return False
    raise _fail(resp, "look for the version tag")


async def head(owner: str, repo: str, branch: str, *, fresh: bool) -> tuple[str, str]:
    """(commit sha, tree sha) of the branch. `fresh` waits for a just-created repo's commit."""
    for attempt in range(EMPTY_REPO_RETRIES if fresh else 1):
        ref = await _call("GET", f"/repos/{owner}/{repo}/git/ref/heads/{branch}")
        if ref.status_code == 200:
            commit = ref.json()["object"]["sha"]
            got = await _call("GET", f"/repos/{owner}/{repo}/git/commits/{commit}")
            if got.status_code != 200:
                raise _fail(got, "read the latest commit")
            return commit, got.json()["tree"]["sha"]
        if ref.status_code not in (404, 409) or attempt == EMPTY_REPO_RETRIES - 1:
            raise _fail(ref, "read the repository's branch")
        await asyncio.sleep(0.5)
    raise AssertionError("unreachable")


async def root_entries(owner: str, repo: str, tree: str) -> list[dict]:
    """The top level of a tree: [{path, mode, type, sha}]."""
    resp = await _call("GET", f"/repos/{owner}/{repo}/git/trees/{tree}")
    if resp.status_code != 200:
        raise _fail(resp, "read the repository's files")
    return resp.json()["tree"]


async def create_blob(owner: str, repo: str, data: bytes) -> str:
    body = {"content": base64.b64encode(data).decode("ascii"), "encoding": "base64"}
    resp = await _call("POST", f"/repos/{owner}/{repo}/git/blobs", body)
    if resp.status_code != 201:
        raise _fail(resp, "upload a file")
    return resp.json()["sha"]


async def create_tree(owner: str, repo: str, entries: list[dict]) -> str:
    """A whole new snapshot (no base tree): files that are not listed are not in it."""
    resp = await _call("POST", f"/repos/{owner}/{repo}/git/trees", {"tree": entries})
    if resp.status_code != 201:
        raise _fail(resp, "build the new version")
    return resp.json()["sha"]


async def create_commit(
    owner: str, repo: str, message: str, tree: str, parent: str
) -> str:
    """The parent is the commit we read, so every older version stays in the history."""
    body = {"message": message, "tree": tree, "parents": [parent]}
    resp = await _call("POST", f"/repos/{owner}/{repo}/git/commits", body)
    if resp.status_code != 201:
        raise _fail(resp, "commit the new version")
    return resp.json()["sha"]


async def move_branch(owner: str, repo: str, branch: str, commit: str) -> None:
    """Never forced: if the branch moved since we read it, GitHub refuses."""
    path = f"/repos/{owner}/{repo}/git/refs/heads/{branch}"
    resp = await _call("PATCH", path, {"sha": commit, "force": False})
    if resp.status_code == 422:
        raise AppError(
            409,
            CONFLICT,
            "The repository changed on GitHub while publishing. Publish again to include "
            "those changes.",
        )
    if resp.status_code != 200:
        raise _fail(resp, "update the branch")


async def create_tag(owner: str, repo: str, tag: str, commit: str) -> bool:
    """A lightweight tag. False when the tag already exists (it is never moved)."""
    body = {"ref": f"refs/tags/{tag}", "sha": commit}
    resp = await _call("POST", f"/repos/{owner}/{repo}/git/refs", body)
    if resp.status_code == 201:
        return True
    if resp.status_code == 422 and "already exists" in resp.text:
        return False
    raise _fail(resp, "tag the version")


async def set_topics(owner: str, repo: str, topics: list[str]) -> None:
    """Replaces all topics, so the caller passes the full list."""
    resp = await _call("PUT", f"/repos/{owner}/{repo}/topics", {"names": topics})
    if resp.status_code != 200:
        raise _fail(resp, "set the repository topics")


async def license_text(key: str) -> str:
    """The standard text of a license, with [year] and [fullname] to fill in."""
    resp = await _call("GET", f"/licenses/{key}")
    if resp.status_code != 200:
        raise _fail(resp, "fetch the license text")
    return resp.json()["body"]
