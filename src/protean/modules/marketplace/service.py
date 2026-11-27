"""Marketplace search and repository details, as the UI shows them.

GitHub's search allows only 10-30 calls a minute, so results are remembered for a minute.
"""

import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import cast

from protean import config
from protean.family.validation import integrity
from protean.integrations.github import read
from protean.modules.marketplace.schemas import Has, RepoDetail, RepoSummary, SearchOut

_cache: dict[tuple, tuple[float, object]] = {}


async def _cached[T](key: tuple, load: Callable[[], Awaitable[T]]) -> T:
    """Remember a result for a minute."""
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < config.SEARCH_CACHE_SECONDS:
        return cast("T", hit[1])
    value = await load()
    if len(_cache) > 200:
        _cache.clear()
    _cache[key] = (time.monotonic(), value)
    return value


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
        body = await read.search(params)
        items = [_summary(i) for i in body["items"]]
        return SearchOut(items=items, total=body["total_count"], page=page)

    return await _cached(("search", text, page), load)


async def detail(owner: str, repo: str, version: str | None = None) -> RepoDetail:
    """Which expected files the repo has, and its README, at the default branch or the tag."""

    async def load() -> RepoDetail:
        found = await read.contents(owner, repo, version)
        return RepoDetail(
            has=Has(**integrity.expected_files(found.paths)),
            readme=found.readme[: config.MAX_README_CHARS] if found.readme else None,
            versions=found.tags,
        )

    return await _cached(("detail", owner.lower(), repo.lower(), version), load)
