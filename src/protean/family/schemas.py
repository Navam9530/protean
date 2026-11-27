"""family.json, schema v1. These models are the single definition of what a valid family is.

Field names in the file are kept as aliases ("sub-agents", "managedBy", ...), so a model dumped
with by_alias=True is exactly what goes back into family.json (and what the UI uses).
"""

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    ValidationError,
    field_validator,
    model_validator,
)

from protean import config
from protean.core.errors import INVALID_FAMILY, AppError
from protean.core.patterns import (
    ENV_NAME_PATTERN,
    FAMILY_VERSION_PATTERN,
    HEADER_NAME_PATTERN,
    ID_PATTERN,
)

ENV_RULE = "environment variable names use letters, digits and _, and do not start with a digit"


def check_id(v: object) -> str:
    """Ids become folder names, so they stay simple and can never point outside the family."""
    if not isinstance(v, str) or not re.match(ID_PATTERN, v):
        raise ValueError("must be lowercase letters, digits and hyphens")
    return v


class _Strict(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class ModelRef(_Strict):
    provider: str
    name: str


def _names(names: list[str] | None, pattern: str, rule: str) -> list[str] | None:
    """The names of values kept in the keys folder: valid, and each only once."""
    for name in names or []:
        if not re.match(pattern, name):
            raise ValueError(f"“{name}”: {rule}")
    if names and len(set(names)) != len(names):
        raise ValueError("each name can be listed only once")
    return names


class McpEntry(_Strict):
    id: str
    managed_by: Literal["harness", "external"] = Field(alias="managedBy")
    transport: Literal["http", "stdio"] | None = None  # harness only
    url: str | None = None  # not for stdio
    client_headers: list[str] | None = Field(
        default=None, alias="clientHeaders"
    )  # not for stdio
    server_env: list[str] | None = Field(
        default=None, alias="serverEnv"
    )  # harness only
    disabled_tools: list[str] | None = Field(default=None, alias="disabledTools")
    tool_aliases: dict[str, str] | None = Field(default=None, alias="toolAliases")

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        return check_id(v)

    @field_validator("client_headers")
    @classmethod
    def _headers(cls, v: list[str] | None) -> list[str] | None:
        return _names(
            v,
            HEADER_NAME_PATTERN,
            "header names use letters, digits and - _ . ~ ! # $ % & ' * + ^ ` |",
        )

    @field_validator("server_env")
    @classmethod
    def _env(cls, v: list[str] | None) -> list[str] | None:
        return _names(v, ENV_NAME_PATTERN, ENV_RULE)

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if self.managed_by == "external":
            if self.transport or self.server_env is not None:
                raise ValueError(
                    "external MCP servers cannot set transport or serverEnv"
                )
            if not self.url:
                raise ValueError("external MCP servers need a url")
        elif self.transport is None:
            raise ValueError("harness-managed MCP servers need a transport")
        elif self.transport == "stdio":
            if self.url or self.client_headers is not None:
                raise ValueError("stdio MCP servers cannot set url or clientHeaders")
        elif not self.url:
            raise ValueError("http MCP servers need a url")
        return self


class Skill(_Strict):
    """A skill of an agent: a folder skills/<agent-id>/<id>/, and the names of the environment
    variables its scripts need (the values are kept in the keys folder, never here)."""

    id: str
    env: list[str] | None = None

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        return check_id(v)

    @field_validator("env")
    @classmethod
    def _env(cls, v: list[str] | None) -> list[str] | None:
        return _names(v, ENV_NAME_PATTERN, ENV_RULE)


class Agent(_Strict):
    id: str
    name: str
    description: str = ""
    model: ModelRef | None = None
    mcps: list[McpEntry] = []
    skills: list[Skill] = []
    sub_agents: list[Agent] = Field(default=[], alias="sub-agents")

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        return check_id(v)

    @field_validator("skills")
    @classmethod
    def _skills(cls, v: list[Skill]) -> list[Skill]:
        if len({s.id for s in v}) != len(v):
            raise ValueError("lists the same skill twice")
        return v

    @field_validator("mcps")
    @classmethod
    def _mcps(cls, v: list[McpEntry]) -> list[McpEntry]:
        if len({m.id for m in v}) != len(v):
            raise ValueError("lists the same MCP server twice")
        return v

    @field_validator("sub_agents")
    @classmethod
    def _sub_agent_names(cls, v: list[Agent]) -> list[Agent]:
        """A parent calls its sub-agents as tools, so their names must tell them apart."""
        seen: set[str] = set()
        for agent in v:
            key = agent.name.strip().casefold()
            if key in seen:
                raise ValueError(
                    f"two sub-agents are named “{agent.name}”; a parent calls them as "
                    "tools, so each name must be unique"
                )
            seen.add(key)
        return v


class Family(_Strict):
    schema_url: str = Field(alias="$schema")
    schema_version: StrictInt = Field(alias="schemaVersion")
    family_version: str = Field(
        alias="familyVersion"
    )  # separates chats; see family/version.py
    agents: Agent

    @field_validator("schema_version")
    @classmethod
    def _schema_version(cls, v: int) -> int:
        if v > config.SCHEMA_VERSION:
            raise ValueError(
                f"this family uses schema version {v}, but this version of Protean "
                f"supports up to version {config.SCHEMA_VERSION}. Update Protean to use it"
            )
        if v < 1:
            raise ValueError("must be 1 or higher")
        return v  # older versions are accepted: migrate them here when schema 2 exists

    @field_validator("family_version")
    @classmethod
    def _family_version(cls, v: str) -> str:
        if not re.match(FAMILY_VERSION_PATTERN, v):
            raise ValueError("must look like 1.2.3")
        return v

    @model_validator(mode="after")
    def _unique_agent_ids(self) -> Self:
        seen: set[str] = set()
        stack = [self.agents]
        while stack:
            agent = stack.pop()
            if agent.id in seen:
                raise ValueError(f"two agents share the id “{agent.id}”")
            seen.add(agent.id)
            stack += agent.sub_agents
        return self


def walk_agents(root: Agent) -> Iterator[Agent]:
    """The agent and everything below it, parents first."""
    yield root
    for child in root.sub_agents:
        yield from walk_agents(child)


def _invalid(message: str) -> AppError:
    return AppError(422, INVALID_FAMILY, message)


def read_family(folder: Path) -> Family:
    """Parse <folder>/family.json. Raises INVALID_FAMILY with a message the user can act on."""
    try:
        raw = json.loads((folder / "family.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise _invalid("family.json was not found.") from None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise _invalid(f"family.json is not valid JSON ({exc}).") from exc
    try:
        return Family.model_validate(raw)
    except ValidationError as exc:
        problems = [
            f"{'.'.join(str(p) for p in e['loc']) or 'family.json'}: "
            f"{e['msg'].removeprefix('Value error, ')}"
            for e in exc.errors()[:5]
        ]
        raise _invalid("family.json is invalid: " + "; ".join(problems)) from exc
