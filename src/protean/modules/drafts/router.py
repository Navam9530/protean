from typing import Annotated

from fastapi import APIRouter, Path, Response, UploadFile
from fastapi.responses import StreamingResponse

from protean.core.sse import sse_response
from protean.modules.drafts import merge, save, store, uploads
from protean.modules.drafts.schemas import (
    Blank,
    DraftEdit,
    DraftOut,
    DraftSource,
    DraftSummary,
    MergePreview,
    MergeRequest,
    MergeTarget,
    Saved,
    SaveRequest,
    Uploaded,
)
from protean.modules.families.api_schemas import Name
from protean.modules.families.schemas import ID
from protean.modules.profile import store as profile
from protean.modules.publish import availability

router = APIRouter(prefix="/drafts", tags=["drafts"])


@router.get("", response_model=list[DraftSummary])
async def list_drafts() -> list[DraftSummary]:
    """Families being built, newest first."""
    return store.list_drafts()


@router.post("", response_model=DraftOut, status_code=201)
async def create_draft(source: DraftSource, response: Response) -> DraftOut:
    """Start a draft from nothing, from a saved family (to edit it) or from a finished import.

    409 when the name is taken here, or (signed in with GitHub) is already a repo on your account.
    200 instead of 201 when an edit of that saved family already exists.
    """
    if isinstance(source, Blank):
        await availability.ensure_free(profile.get().owner, source.repo)
    draft, created = store.create(source)
    if not created:
        response.status_code = 200
    return draft


@router.get("/{name}", response_model=DraftOut)
async def get_draft(name: Name) -> DraftOut:
    return store.read(name)


@router.put("/{name}", response_model=Saved)
async def save_draft(name: Name, doc: DraftEdit) -> Saved:
    """Autosave the whole draft. Only checks that it is safe to store; it may be incomplete.

    409 `conflict` when `baseUpdatedAt` is older than the draft: it was changed elsewhere.
    """
    return Saved(updated_at=store.write(name, doc))


@router.delete("/{name}", status_code=204)
async def discard_draft(name: Name) -> Response:
    store.discard(name)
    return Response(status_code=204)


Item = Annotated[str, Path(pattern=ID.pattern)]


@router.put("/{name}/agents/{agent_id}/{kind}/{item_id}", response_model=Uploaded)
async def upload_item(
    name: Name,
    agent_id: Item,
    kind: uploads.Kind,
    item_id: Item,
    files: list[UploadFile],
) -> Uploaded:
    """Upload a skill or MCP server folder for an agent, replacing an earlier upload.

    Multipart, one `files` part per file named by its relative path ("my-skill/SKILL.md"); the
    top folder name is dropped. A skill needs a SKILL.md at its top. Only writes files: the UI
    lists the item in family.json through autosave.
    """
    named = [(f.filename or "", f.file) for f in files]
    return Uploaded(files=uploads.put(name, agent_id, kind, item_id, named))


@router.post("/{name}/merge/preview", response_model=MergePreview)
async def preview_merge(name: Name, target: MergeTarget) -> MergePreview:
    """What adding an import under `parentId` would do, and what clashes. Changes nothing.

    `mode`: append adds the import's root as a sub-agent of `parentId`; merge merges it into
    `parentId`.
    """
    return merge.preview(name, target)


@router.post("/{name}/merge", response_model=DraftOut)
async def merge_import(name: Name, request: MergeRequest) -> DraftOut:
    """Add the import under `parentId`, then delete the import folder. 409 `unresolved_conflicts`
    (and nothing changes) unless `resolutions` settles every conflict the preview listed."""
    return merge.merge(name, request)


@router.post("/{name}/save")
async def save_draft_as_family(
    name: Name, request: SaveRequest | None = None
) -> StreamingResponse:
    """Check the draft completely and turn it into a saved family, streaming the progress.

    Events: stage (schema, agents, workspace, promote), tree, agent, check, warning, then one
    `done` ({name, version, bumped, changed}) or one `error`. The draft is deleted on success and
    left as it is on failure. `bump` (patch, minor or major) applies only when a saved family of
    this name exists and the draft changed it; the first save keeps the draft's version.
    """
    return sse_response(save.save(name, (request or SaveRequest()).bump))
