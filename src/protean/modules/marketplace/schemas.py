import re
from typing import Annotated

from pydantic import AfterValidator, Field

from protean.core.schemas import CamelModel
from protean.modules.families.schemas import Agent


def check_version(v: str) -> str:
    """A tag name, checked so nothing odd can be spliced into the GitHub URLs we build."""
    if not re.fullmatch(r"[A-Za-z0-9._/-]{1,100}", v) or v[0] in "-/" or ".." in v:
        raise ValueError("is not a usable version name")
    return v


Version = Annotated[str, AfterValidator(check_version)]


class RepoSummary(CamelModel):
    owner: str
    repo: str
    description: str = ""
    stars: int = 0
    license: str | None = None  # SPDX id, None when the repo has none
    pushed_at: int  # epoch milliseconds
    avatar_url: str | None = None


class SearchOut(CamelModel):
    items: list[RepoSummary]
    total: int
    page: int


class Has(CamelModel):
    family_json: bool
    license: bool
    prompts: bool
    readme: bool


class RepoDetail(CamelModel):
    has: Has
    readme: str | None = None
    versions: list[str] = Field(
        default_factory=list
    )  # tag names; only for the default branch


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
