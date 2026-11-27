"""GitHub calls for the marketplace: search, repo contents and the zip download.

They use the signed-in user's token when there is one (higher rate limits). If GitHub rejects
the token (revoked or expired), it is dropped and the call is retried anonymously, so browsing
the marketplace never breaks on a stale sign-in.
"""

import asyncio
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import cast

import httpx

from protean import config
from protean.core import network
from protean.core.errors import (
    GITHUB_ERROR,
    GITHUB_UNREACHABLE,
    NOT_FOUND,
    RATE_LIMITED,
    REPO_NOT_FOUND,
    TOO_LARGE,
    AppError,
)
from protean.modules.auth import login
from protean.modules.families.validation import integrity
from protean.modules.marketplace.schemas import Has, RepoDetail, RepoSummary, SearchOut

API = "https://api.github.com"
JSON = "application/vnd.github+json"
PROGRESS_STEP = 256 * 1024  # how often the download reports its size
RAW = "application/vnd.github.raw+json"

_cache: dict[tuple, tuple[float, object]] = {}


async def _cached[T](key: tuple, load: Callable[[], Awaitable[T]]) -> T:
    """Remember a result for a minute: GitHub search allows only 10-30 calls a minute."""
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < config.SEARCH_CACHE_SECONDS:
        return cast("T", hit[1])
    value = await load()
    if len(_cache) > 200:
        _cache.clear()
    _cache[key] = (time.monotonic(), value)
    return value


async def _get(
    url: str, *, accept: str = JSON, params: dict | None = None, stream: bool = False
) -> httpx.Response:
    """GET with the user's token. A streamed response must be closed by the caller."""
    token = login.access_token()
    while True:
        headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        http = network.client()
        try:
            resp = await http.send(
                http.build_request("GET", url, params=params, headers=headers),
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
            login.drop_token()
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


def _summary(item: dict) -> RepoSummary:
    spdx = (item.get("license") or {}).get("spdx_id")
    pushed = datetime.fromisoformat(item["pushed_at"])
    return RepoSummary(
        owner=item["owner"]["login"],
        repo=item["name"],
        description=item.get("description") or "",
        stars=item.get("stargazers_count", 0),
        license=("Other" if spdx == "NOASSERTION" else spdx),
        pushed_at=int(pushed.timestamp() * 1000),
        avatar_url=item["owner"].get("avatar_url"),
    )


async def search(query: str, page: int) -> SearchOut:
    text = query.strip()
    q = f"topic:{config.MARKETPLACE_TOPIC} archived:false"
    if text:
        q += f" {text} in:name,description"
    params = {
        "q": q,
        "sort": "stars",
        "order": "desc",
        "per_page": config.SEARCH_PAGE_SIZE,
        "page": page,
    }

    async def load() -> SearchOut:
        resp = await _get(f"{API}/search/repositories", params=params)
        if resp.status_code != 200:
            raise AppError(
                502, GITHUB_ERROR, resp.json().get("message", "Search failed.")
            )
        body = resp.json()
        items = [_summary(i) for i in body["items"]]
        return SearchOut(items=items, total=body["total_count"], page=page)

    return await _cached(("search", text, page), load)


async def _tags(owner: str, repo: str) -> list[str]:
    """The repo's tag names, as GitHub lists them (at most 100). Empty when it has none."""
    resp = await _get(f"{API}/repos/{owner}/{repo}/tags", params={"per_page": 100})
    return [t["name"] for t in resp.json()] if resp.status_code == 200 else []


async def detail(owner: str, repo: str, version: str | None = None) -> RepoDetail:
    """The files and README of the default branch, or of the tag `version`.

    The list of tags comes only with the default-branch call: the UI keeps it while the user
    switches between versions.
    """
    ref = version or "HEAD"

    async def load() -> RepoDetail:
        tree, readme, tags = await asyncio.gather(
            _get(
                f"{API}/repos/{owner}/{repo}/git/trees/{ref}",
                params={"recursive": "1"},
            ),
            _get(
                f"{API}/repos/{owner}/{repo}/readme", accept=RAW, params=_ref(version)
            ),
            _tags(owner, repo) if version is None else _nothing(),
        )
        if tree.status_code == 404:
            raise _not_found(owner, repo, version)
        if tree.status_code == 409:  # empty repository
            paths: list[str] = []
        elif tree.status_code != 200:
            raise AppError(
                502,
                GITHUB_ERROR,
                tree.json().get("message", "Could not read the repository."),
            )
        else:
            paths = [e["path"] for e in tree.json().get("tree", [])]
        return RepoDetail(
            has=Has(**integrity.expected_files(paths)),
            readme=readme.text[: config.MAX_README_CHARS]
            if readme.status_code == 200
            else None,
            versions=tags,
        )

    return await _cached(("detail", owner.lower(), repo.lower(), version), load)


async def _nothing() -> list[str]:
    return []


def _ref(version: str | None) -> dict | None:
    return {"ref": version} if version else None


def _not_found(owner: str, repo: str, version: str | None) -> AppError:
    if version:
        return AppError(
            404, NOT_FOUND, f"{owner}/{repo} has no version called “{version}”."
        )
    return AppError(404, REPO_NOT_FOUND, f"{owner}/{repo} was not found.")


async def download_zip(
    owner: str, repo: str, dest: Path, version: str | None = None
) -> AsyncGenerator[int]:
    """Stream the default branch (or the tag `version`) as a zip into `dest`, giving up past the size limit.

    Yields the bytes written so far, at most once per PROGRESS_STEP.
    """
    resp = await _get(
        f"{API}/repos/{owner}/{repo}/zipball/{version or ''}".rstrip("/"), stream=True
    )
    try:
        if resp.status_code == 404:
            raise _not_found(owner, repo, version)
        if resp.status_code != 200:
            raise AppError(
                502,
                GITHUB_ERROR,
                f"GitHub returned {resp.status_code} for the download.",
            )
        size, reported = 0, 0
        with dest.open("wb") as out:
            async for chunk in resp.aiter_bytes():
                size += len(chunk)
                if size > config.MAX_ZIP_BYTES:
                    mb = config.MAX_ZIP_BYTES // 1_000_000
                    raise AppError(
                        413, TOO_LARGE, f"The download is larger than {mb} MB."
                    )
                out.write(chunk)
                if size - reported >= PROGRESS_STEP:
                    reported = size
                    yield size
    except httpx.HTTPError as exc:
        raise AppError(
            502, GITHUB_UNREACHABLE, "The download was interrupted."
        ) from exc
    finally:
        await resp.aclose()
