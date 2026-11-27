from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from protean.core.schemas import CamelModel
from protean.core.sse import sse_response
from protean.modules.families.api_schemas import Name
from protean.modules.publish import service
from protean.modules.publish.schemas import PublishForm, PublishRequest

router = APIRouter(prefix="/families", tags=["publish"])


@router.get("/{name}/publish", response_model=PublishForm)
async def publish_form(name: Name) -> PublishForm:
    """The README and license kind the publish form starts from. Nothing else of the family."""
    return service.form(name)


@router.post("/{name}/publish")
async def publish_family(
    name: Name, body: PublishRequest | None = None
) -> StreamingResponse:
    """Push the saved family to the user's own GitHub repo, streaming progress as events.

    Events: stage (check, repo, upload, commit, tag, topics), progress (upload), warning, then
    one `done` ({url, commit, tag, version, listed}) or one `error`. The body carries only the
    README and license the user changed; see PublishRequest.
    """
    return sse_response(service.publish(name, body or PublishRequest()))


class ListedOut(CamelModel):
    listed: bool


@router.post("/{name}/publish/topic", response_model=ListedOut)
async def list_in_marketplace(name: Name) -> ListedOut:
    """List the published repo in the marketplace again (add the `agents-marketplace` topic).
    Only on the user's say-so: publishing never re-adds it by itself."""
    return ListedOut(listed=await service.set_listed(name, True))


@router.delete("/{name}/publish", response_model=ListedOut)
async def unpublish_family(name: Name) -> ListedOut:
    """Unpublish: remove the `agents-marketplace` topic so the repo leaves the marketplace.
    The repo, its history and the local family stay. Protean never deletes a repo."""
    return ListedOut(listed=await service.set_listed(name, False))
