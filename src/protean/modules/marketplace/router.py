from typing import Annotated

from fastapi import APIRouter, Query

from protean.core.patterns import Owner, Repo, Version
from protean.modules.marketplace import service
from protean.modules.marketplace.schemas import RepoDetail, SearchOut

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


@router.get("/search", response_model=SearchOut)
async def search(
    q: str = "", page: Annotated[int, Query(ge=1, le=50)] = 1
) -> SearchOut:
    """Public repos tagged with the marketplace topic (GitHub allows only the first 1000)."""
    return await service.search(q, page)


@router.get("/{owner}/{repo}", response_model=RepoDetail)
async def repo_detail(
    owner: Owner,
    repo: Repo,
    version: Version | None = None,
) -> RepoDetail:
    """Which expected files the repo has, and its README, on the default branch or at the tag
    `version`. Without a version it also lists the repo's tags. Nothing is parsed yet."""
    return await service.detail(owner, repo, version)
