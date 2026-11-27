"""Every pattern that decides whether a name, id or version is acceptable, written once.

The regexes are plain anchored strings, so they work with `re.fullmatch`, with pydantic's
`pattern=` and with FastAPI's `Path(pattern=...)`. The Annotated types below are for URL path
parameters. The rules that go with them (the messages, the extra checks) stay with the schema
that uses them.
"""

import re
from typing import Annotated

from fastapi import Path
from pydantic import AfterValidator

# ---- GitHub names -------------------------------------------------------------------------
OWNER_PATTERN = r"^[A-Za-z0-9-]{1,39}$"  # a GitHub login
REPO_PATTERN = r"^[A-Za-z0-9._-]{1,100}$"  # a GitHub repo name
# <owner>_<repo>. GitHub logins have no underscore, so the first one splits the name.
NAME_PATTERN = r"^[A-Za-z0-9-]{1,39}_[A-Za-z0-9._-]{1,100}$"
TAG_PATTERN = r"^[A-Za-z0-9._/-]{1,100}$"  # a git tag; see `check_version` for the rest

# ---- ids that become file and folder names ----------------------------------------------------
ID_PATTERN = r"^[a-z0-9][a-z0-9-]*$"  # an agent, skill or MCP server
IMPORT_ID_PATTERN = r"^[0-9a-f]{32}$"  # a folder under imports/

# ---- family.json contents -------------------------------------------------------------------
FAMILY_VERSION_PATTERN = r"^\d+\.\d+\.\d+$"  # MAJOR.MINOR.PATCH
HEADER_NAME_PATTERN = (
    r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$"  # an HTTP header name (RFC 9110 token)
)
ENV_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"  # an environment variable


def check_version(v: str) -> str:
    """A tag name, checked so nothing odd can be spliced into the GitHub URLs we build."""
    if not re.fullmatch(TAG_PATTERN, v) or v[0] in "-/" or ".." in v:
        raise ValueError("is not a usable version name")
    return v


# ---- URL path parameters --------------------------------------------------------------------
Name = Annotated[str, Path(pattern=NAME_PATTERN)]  # a family or draft: <owner>_<repo>
Owner = Annotated[str, Path(pattern=OWNER_PATTERN)]
Repo = Annotated[str, Path(pattern=REPO_PATTERN)]
ItemId = Annotated[str, Path(pattern=ID_PATTERN)]  # an agent, skill or MCP server
ImportId = Annotated[str, Path(pattern=IMPORT_ID_PATTERN)]
Version = Annotated[str, AfterValidator(check_version)]  # a tag, in a query or a body
