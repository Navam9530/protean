"""Family versions: MAJOR.MINOR.PATCH, raised by the backend when a family is saved."""

from typing import Literal

Bump = Literal["patch", "minor", "major"]


def bump(version: str, kind: Bump) -> str:
    """The next version. The schema has already checked that `version` is three numbers."""
    major, minor, patch = (int(part) for part in version.split("."))
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"
