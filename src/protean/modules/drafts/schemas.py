"""Request and response bodies for the draft and family endpoints."""

from typing import Annotated, Any, Literal

from pydantic import Field

from protean.core.schemas import CamelModel
from protean.modules.families.api_schemas import CardFields, Secrets
from protean.modules.families.files import NAME_PATTERN, REPO_PATTERN
from protean.modules.families.schemas import ID
from protean.modules.families.version import Bump

ID_PATTERN = ID.pattern
Owner = r"^[A-Za-z0-9-]{1,39}$"
Repo = REPO_PATTERN


class Blank(CamelModel):
    """A new, empty family named <you>_<repo>."""

    kind: Literal["blank"]
    repo: str = Field(pattern=Repo)


class FromFamily(CamelModel):
    """An editable copy of a saved family."""

    kind: Literal["family"]
    name: str = Field(pattern=NAME_PATTERN)


class FromImport(CamelModel):
    """A finished import, named after the repo it came from."""

    kind: Literal["import"]
    import_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    owner: str = Field(pattern=Owner)
    repo: str = Field(pattern=Repo)


DraftSource = Annotated[Blank | FromFamily | FromImport, Field(discriminator="kind")]


class DraftDoc(CamelModel):
    """The whole draft as the UI edits it: family.json plus each agent's prompt text."""

    family: dict[str, Any]
    prompts: dict[str, str] = Field(default_factory=dict)


class DraftEdit(DraftDoc):
    """An autosave. `base_updated_at` is the `updatedAt` this edit started from; when the draft
    has changed since (another tab), the save is refused instead of overwriting it."""

    base_updated_at: int | None = None
    # The values of MCP headers and env vars. Given: the keys folder is made to match it. Left
    # out: it is left as it is.
    secrets: Secrets | None = None


class Uploaded(CamelModel):
    files: int


class DraftOut(DraftDoc):
    name: str
    updated_at: int  # send it back as `baseUpdatedAt` with the next autosave
    secrets: Secrets = Field(default_factory=Secrets)


class Saved(CamelModel):
    updated_at: int  # ms since the epoch


class DraftSummary(CardFields):
    editing: (
        bool  # a saved family with this name exists: these are unsaved changes to it
    )


# ---- merging an import into a draft -------------------------------------------------------
class MergeTarget(CamelModel):
    """Which finished import to add, and the draft agent to add it under or merge it into."""

    import_id: str = Field(pattern=r"^[0-9a-f]{32}$")
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


class SaveRequest(CamelModel):
    """How to save. The version is raised by the backend when a saved family has changed."""

    bump: Bump = "patch"
