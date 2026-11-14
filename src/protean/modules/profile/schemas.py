from typing import Literal

from protean.core.schemas import CamelModel


class Profile(CamelModel):
    # None until the user makes the first-run choice (so there is no separate "onboarded" flag).
    source: Literal["hostname", "github"] | None
    owner: str  # id prefix: the sanitized hostname or the GitHub login, depending on `source`
    avatar_url: str | None = None
