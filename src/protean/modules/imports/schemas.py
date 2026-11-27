"""Request and response bodies for importing a family."""

from pydantic import Field

from protean.core.patterns import Version
from protean.core.schemas import CamelModel
from protean.family.schemas import Agent


class ImportRequest(CamelModel):
    version: Version | None = None  # a tag; the default branch when left out


class ImportOut(CamelModel):
    import_id: str  # folder under imports/ that holds the downloaded files
    owner: str
    repo: str
    family_version: str
    agents: Agent
    prompts: dict[str, str]  # agent id -> contents of prompts/<id>.md
    warnings: list[str] = Field(default_factory=list)
