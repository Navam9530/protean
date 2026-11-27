from pydantic import Field

from protean.core.schemas import CamelModel


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
