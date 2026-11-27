from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, UploadFile
from fastapi.responses import StreamingResponse

from protean.core.sse import sse_response
from protean.modules.families.files import REPO_PATTERN
from protean.modules.families.validation import archive
from protean.modules.marketplace import github, importer
from protean.modules.marketplace.schemas import (
    ImportRequest,
    RepoDetail,
    SearchOut,
    Version,
)
from protean.modules.profile import store as profile

router = APIRouter(prefix="/marketplace", tags=["marketplace"])

# Checked here so nothing odd can be spliced into the GitHub URLs we build.
Owner = Annotated[str, Path(pattern=r"^[A-Za-z0-9-]{1,39}$")]
Repo = Annotated[str, Path(pattern=REPO_PATTERN)]


@router.get("/search", response_model=SearchOut)
async def search(
    q: str = "", page: Annotated[int, Query(ge=1, le=50)] = 1
) -> SearchOut:
    """Public repos tagged with the marketplace topic (GitHub allows only the first 1000)."""
    return await github.search(q, page)


@router.get("/{owner}/{repo}", response_model=RepoDetail)
async def repo_detail(
    owner: Owner,
    repo: Repo,
    version: Version | None = None,
) -> RepoDetail:
    """Which expected files the repo has, and its README, on the default branch or at the tag
    `version`. Without a version it also lists the repo's tags. Nothing is parsed yet."""
    return await github.detail(owner, repo, version)


@router.post("/{owner}/{repo}/import")
async def import_family(
    owner: Owner, repo: Repo, body: ImportRequest | None = None
) -> StreamingResponse:
    """Download the repo (the default branch, or the tag `version`) into imports/ and validate
    it, streaming progress as events.

    Events: stage, progress, tree, agent, check, warning, then one `done` (the family and its
    prompts) or one `error`. Nothing is saved; the folder waits in imports/ for the next step.
    """
    return sse_response(
        importer.import_repo(owner, repo, body.version if body else None)
    )


imports_router = APIRouter(prefix="/imports", tags=["marketplace"])
ImportId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]


@imports_router.delete("/{import_id}", status_code=204)
def discard_import(import_id: ImportId) -> Response:
    """Throw away a finished import that the user did not use (closed the dialog)."""
    importer.discard(import_id)
    return Response(status_code=204)


@imports_router.post("/upload")
async def import_upload(files: list[UploadFile]) -> StreamingResponse:
    """Validate a family folder from the user's computer that is not on GitHub yet.

    Multipart, one `files` part per file, each named by its relative path
    ("my-family/prompts/lead.md"). The family is named <you>_<folder>, after the folder. The
    events and the result are those of a marketplace import.
    """
    named = [(f.filename or "", f.file) for f in files]
    repo = archive.folder_name([name for name, _ in named])
    return sse_response(importer.import_folder(profile.get().owner, repo, named))
