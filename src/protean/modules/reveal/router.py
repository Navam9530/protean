from fastapi import APIRouter, Response

from protean.modules.reveal import service
from protean.modules.reveal.schemas import RevealRequest

router = APIRouter(prefix="/reveal", tags=["reveal"])


@router.post("", status_code=204)
async def reveal(req: RevealRequest) -> Response:
    """Open the folder in the system file manager."""
    service.open_folder(
        service.folder(req.scope, req.name, req.kind, req.agent_id, req.item_id)
    )
    return Response(status_code=204)
