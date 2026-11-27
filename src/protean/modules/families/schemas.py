"""Request and response bodies for the saved-family endpoints."""

from typing import Any

from pydantic import Field

from protean.core.schemas import CamelModel
from protean.family.card import CardFields
from protean.family.values import Secrets


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
