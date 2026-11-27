"""Request and response bodies for adding an import to a draft."""

from typing import Any, Literal

from pydantic import Field

from protean.core.patterns import ID_PATTERN, IMPORT_ID_PATTERN
from protean.core.schemas import CamelModel


class MergeTarget(CamelModel):
    """Which finished import to add, and the draft agent to add it under or merge it into."""

    import_id: str = Field(pattern=IMPORT_ID_PATTERN)
    parent_id: str = Field(pattern=ID_PATTERN)
    mode: Literal["append", "merge"]  # add as a new sub-agent, or merge into `parentId`


class Custom(CamelModel):
    custom: str  # your own text instead of either version (not for `model`)


class Drop(CamelModel):
    drop: Literal[True]  # leave the imported one out


class Alias(CamelModel):
    alias: str = Field(pattern=ID_PATTERN)  # keep both: the imported one gets this id


class AgentResolution(CamelModel):
    """How to settle one agent that exists in both. Keys are field names ("name",
    "description", "model", "prompt"), skill ids and MCP ids."""

    fields: dict[str, Literal["old", "new"] | Custom] = Field(default_factory=dict)
    skills: dict[str, Drop | Alias] = Field(default_factory=dict)
    mcps: dict[str, Drop | Alias] = Field(default_factory=dict)


class MergeRequest(MergeTarget):
    resolutions: dict[str, AgentResolution] = Field(
        default_factory=dict
    )  # by draft agent id


class FieldConflict(CamelModel):
    field: str
    old: Any  # what the draft has
    new: Any  # what the import has


class AgentConflict(CamelModel):
    agent_id: str  # the draft's agent
    imported_id: str  # the imported agent merged into it
    fields: list[FieldConflict] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    mcps: list[str] = Field(default_factory=list)


class MergePreview(CamelModel):
    added: list[str]  # agent ids that join the draft as new agents
    merged: list[str]  # agent ids that already exist and take what the import adds
    conflicts: list[AgentConflict]  # what the user has to settle first
    renamed: dict[str, str] = Field(
        default_factory=dict
    )  # imported id -> the id it gets, when the draft already uses it
    warnings: list[str] = Field(
        default_factory=list
    )  # in the result; fix them in the draft
