"""Request and response bodies for the saved-family endpoints."""

from typing import Annotated, Any

from fastapi import Path
from pydantic import Field

from protean.core.schemas import CamelModel
from protean.modules.families.files import NAME_PATTERN

Name = Annotated[str, Path(pattern=NAME_PATTERN)]


class CardFields(CamelModel):
    """What a family or draft card shows. Times are ms since the epoch."""

    name: str
    family: dict[str, Any]  # family.json, for the minimap
    description: str  # the root agent's
    family_version: str
    agent_count: int
    size: int  # bytes the family keeps when saved
    chat_count: int  # phase 2
    updated_at: int  # modified
    accessed_at: int  # phase 2: for now the same as updated_at


class McpValues(CamelModel):
    """The values of one MCP server's client headers and environment variables, by name. They
    are kept in keys/<family>/<agent-id>/<mcp-id>.json, never in family.json."""

    client_headers: dict[str, str] = Field(default_factory=dict)
    server_env: dict[str, str] = Field(default_factory=dict)


class Secrets(CamelModel):
    """Every value of a family: by agent id, then MCP id or skill id. A skill's values are its
    environment variables, name -> value."""

    mcps: dict[str, dict[str, McpValues]] = Field(default_factory=dict)
    skills: dict[str, dict[str, dict[str, str]]] = Field(default_factory=dict)


class FamilySummary(CardFields):
    published_family_version: str | None = (
        None  # the familyVersion last pushed to GitHub
    )
    listed: bool = False  # the published repo carries the marketplace topic


class FamilyOut(CamelModel):
    """A saved family as the UI shows it: family.json plus each agent's prompt text."""

    name: str
    family: dict[str, Any]
    prompts: dict[str, str]
    secrets: Secrets = Field(default_factory=Secrets)
