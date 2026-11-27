from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from protean.modules.drafts.uploads import Kind
from protean.modules.families.api_schemas import Name
from protean.modules.families.schemas import ID
from protean.modules.reveal import service

router = APIRouter(prefix="/reveal", tags=["reveal"])


class RevealRequest(BaseModel):
    """A family or draft folder, or (with all three of kind, agentId, itemId) one skill or MCP's."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    scope: Literal["family", "draft"]
    name: Name
    kind: Kind | None = None
    agent_id: str | None = Field(None, alias="agentId", pattern=ID.pattern)
    item_id: str | None = Field(None, alias="itemId", pattern=ID.pattern)

    @model_validator(mode="after")
    def _all_or_none(self) -> RevealRequest:
        if len({self.kind is None, self.agent_id is None, self.item_id is None}) != 1:
            raise ValueError("kind, agentId and itemId go together")
        return self


@router.post("", status_code=204)
async def reveal(req: RevealRequest) -> Response:
    """Open the folder in the system file manager."""
    service.open_folder(
        service.folder(req.scope, req.name, req.kind, req.agent_id, req.item_id)
    )
    return Response(status_code=204)
