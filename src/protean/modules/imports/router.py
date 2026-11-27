from fastapi import APIRouter, Response, UploadFile
from fastapi.responses import StreamingResponse

from protean.core.patterns import ImportId, Owner, Repo
from protean.core.sse import sse_response
from protean.family.validation import archive
from protean.identity import profile
from protean.modules.imports import service
from protean.modules.imports.schemas import ImportRequest

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/github/{owner}/{repo}")
async def import_from_github(
    owner: Owner, repo: Repo, body: ImportRequest | None = None
) -> StreamingResponse:
    """Download the repo (the default branch, or the tag `version`) into imports/ and validate
    it, streaming progress as events.

    Events: stage, progress, tree, agent, check, warning, then one `done` (the family and its
    prompts) or one `error`. Nothing is saved; the folder waits in imports/ for the next step.
    """
    return sse_response(
        service.import_repo(owner, repo, body.version if body else None)
    )


@router.post("/upload")
async def import_from_upload(files: list[UploadFile]) -> StreamingResponse:
    """Validate a family folder from the user's computer that is not on GitHub yet.

    Multipart, one `files` part per file, each named by its relative path
    ("my-family/prompts/lead.md"). The family is named <you>_<folder>, after the folder. The
    events and the result are those of a GitHub import.
    """
    named = [(f.filename or "", f.file) for f in files]
    repo = archive.folder_name([name for name, _ in named])
    return sse_response(service.import_folder(profile.get().owner, repo, named))


@router.delete("/{import_id}", status_code=204)
def discard_import(import_id: ImportId) -> Response:
    """Throw away a finished import that the user did not use (closed the dialog)."""
    service.discard(import_id)
    return Response(status_code=204)
