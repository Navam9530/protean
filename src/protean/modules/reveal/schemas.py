"""Request body for the reveal endpoint."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from protean.core.patterns import ID_PATTERN, Name
from protean.family.folder import Kind


class RevealRequest(BaseModel):
    """A family or draft folder, or (with all three of kind, agentId, itemId) one skill or MCP's."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    scope: Literal["family", "draft"]
    name: Name
    kind: Kind | None = None
    agent_id: str | None = Field(None, alias="agentId", pattern=ID_PATTERN)
    item_id: str | None = Field(None, alias="itemId", pattern=ID_PATTERN)

    @model_validator(mode="after")
    def _all_or_none(self) -> RevealRequest:
        if len({self.kind is None, self.agent_id is None, self.item_id is None}) != 1:
            raise ValueError("kind, agentId and itemId go together")
        return self
