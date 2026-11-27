"""The GitHub reads the marketplace needs: search, a repo's files and README, its tags, and the
zip download. They return plain data; the marketplace turns it into its own shapes.

They use the signed-in user's token when there is one (higher rate limits), so browsing the
marketplace never breaks on a stale sign-in (see `client.request`).
"""

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path

import httpx

from protean import config
from protean.core.errors import (
    GITHUB_ERROR,
    GITHUB_UNREACHABLE,
    NOT_FOUND,
    REPO_NOT_FOUND,
    TOO_LARGE,
    AppError,
)
from protean.integrations.github import client

PROGRESS_STEP = 256 * 1024  # how often the download reports its size


@dataclass(frozen=True)
class RepoContents:
    paths: list[str]  # every file path in the repo at that version
    readme: str | None
    tags: list[str]  # only for the default branch


async def search(params: dict) -> dict:
    """The JSON body of a repository search."""
    resp = await client.request("GET", "/search/repositories", params=params)
    if resp.status_code != 200:
        raise AppError(502, GITHUB_ERROR, resp.json().get("message", "Search failed."))
    return resp.json()


async def _tags(owner: str, repo: str) -> list[str]:
    """The repo's tag names, as GitHub lists them (at most 100). Empty when it has none."""
    resp = await client.request(
        "GET", f"/repos/{owner}/{repo}/tags", params={"per_page": 100}
    )
    return [t["name"] for t in resp.json()] if resp.status_code == 200 else []


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


async def contents(owner: str, repo: str, version: str | None = None) -> RepoContents:
    """The files and README of the default branch, or of the tag `version`.

    The list of tags comes only with the default-branch call: the UI keeps it while the user
    switches between versions.
    """
    tree, readme, tags = await asyncio.gather(
        client.request(
            "GET",
            f"/repos/{owner}/{repo}/git/trees/{version or 'HEAD'}",
            params={"recursive": "1"},
        ),
        client.request(
            "GET",
            f"/repos/{owner}/{repo}/readme",
            accept=client.RAW,
            params=_ref(version),
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
    return RepoContents(
        paths=paths,
        readme=readme.text if readme.status_code == 200 else None,
        tags=tags,
    )


async def download_zip(
    owner: str, repo: str, dest: Path, version: str | None = None
) -> AsyncGenerator[int]:
    """Stream the default branch (or the tag `version`) as a zip into `dest`, giving up past the size limit.

    Yields the bytes written so far, at most once per PROGRESS_STEP.
    """
    resp = await client.request(
        "GET",
        f"/repos/{owner}/{repo}/zipball/{version or ''}".rstrip("/"),
        stream=True,
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
