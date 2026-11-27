"""Request and response bodies for the draft and family endpoints."""

from typing import Annotated, Any, Literal

from pydantic import Field

from protean.core.patterns import (
    IMPORT_ID_PATTERN,
    NAME_PATTERN,
    OWNER_PATTERN,
    REPO_PATTERN,
)
from protean.core.schemas import CamelModel
from protean.family.card import CardFields
from protean.family.values import Secrets
from protean.family.version import Bump


class Blank(CamelModel):
    """A new, empty family named <you>_<repo>."""

    kind: Literal["blank"]
    repo: str = Field(pattern=REPO_PATTERN)


class FromFamily(CamelModel):
    """An editable copy of a saved family."""

    kind: Literal["family"]
    name: str = Field(pattern=NAME_PATTERN)


class FromImport(CamelModel):
    """A finished import, named after the repo it came from."""

    kind: Literal["import"]
    import_id: str = Field(pattern=IMPORT_ID_PATTERN)
    owner: str = Field(pattern=OWNER_PATTERN)
    repo: str = Field(pattern=REPO_PATTERN)


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


class SaveRequest(CamelModel):
    """How to save. The version is raised by the backend when a saved family has changed."""

    bump: Bump = "patch"
