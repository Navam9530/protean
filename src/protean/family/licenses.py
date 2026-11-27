"""The licenses a family can be published under, and the README/LICENSE files in a folder."""

from pathlib import Path
from typing import Literal

License = Literal[
    "mit", "apache-2.0"
]  # what the user can choose; GitHub supplies the text
LICENSE_FILES = ("LICENSE", "LICENCE", "COPYING")


def kind(text: str) -> str:
    """ "mit", "apache-2.0", or "other" for any license text that is neither."""
    low = text.lower()
    if "mit license" in low or "permission is hereby granted, free of charge" in low:
        return "mit"
    if "apache license" in low and "version 2.0" in low:
        return "apache-2.0"
    return "other"


def root_files(folder: Path, prefixes: tuple[str, ...]) -> list[Path]:
    """The files at the root of `folder` whose names start with one of `prefixes`."""
    return sorted(
        p
        for p in folder.iterdir()
        if p.is_file() and p.name.upper().startswith(prefixes)
    )


def read_readme(folder: Path) -> str:
    files = root_files(folder, ("README",))
    best = next(
        (f for f in files if f.name == "README.md"), files[0] if files else None
    )
    return best.read_text(encoding="utf-8", errors="replace") if best else ""


def read_license(folder: Path) -> str | None:
    """The kind of the folder's license ("mit", "apache-2.0", "other"), None without one."""
    files = root_files(folder, LICENSE_FILES)
    if not files:
        return None
    return kind(files[0].read_text(encoding="utf-8", errors="replace"))
