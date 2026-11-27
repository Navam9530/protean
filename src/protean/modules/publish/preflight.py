"""What must hold before anything is sent to GitHub: who may publish, and that the family is whole."""

from pathlib import Path

from protean import config
from protean.core.errors import (
    DRAFT_EXISTS,
    INVALID_FAMILY,
    NOT_FOUND,
    NOT_OWNER,
    NOT_SIGNED_IN,
    TOO_LARGE,
    AppError,
)
from protean.family.folder import EXTRA_FILES
from protean.family.schemas import Family, read_family, walk_agents
from protean.family.validation import integrity
from protean.identity import profile, tokens


def owned(name: str) -> None:
    """Signed in with GitHub as the owner of the family's repo."""
    if not tokens.access_token():
        raise AppError(401, NOT_SIGNED_IN, "Sign in with GitHub to publish.")
    owner = name.split("_", 1)[0]
    if owner.lower() != profile.get().owner.lower():
        raise AppError(
            403,
            NOT_OWNER,
            f"You are signed in as {profile.get().owner}, so you can only publish "
            f"families that start with “{profile.get().owner}_”.",
        )


def check(name: str, folder: Path) -> Family:
    """Everything that must hold before anything is sent to GitHub."""
    if not (folder / "family.json").is_file():
        raise AppError(404, NOT_FOUND, f"There is no saved family named “{name}”.")
    if (config.DRAFTS_DIR / name).exists():
        raise AppError(
            409,
            DRAFT_EXISTS,
            "This family has unsaved changes in a draft. Save or discard the draft first.",
        )
    owned(name)
    family = read_family(folder)
    missing = [
        path
        for agent in walk_agents(family.agents)
        for paths in integrity.check_agent(folder, agent).values()
        for path in paths
    ]
    if missing:
        raise AppError(
            422,
            INVALID_FAMILY,
            f"Files that family.json needs are missing: {', '.join(missing[:8])}",
        )
    return family


def family_files(folder: Path) -> list[Path]:
    """Every file to publish except the README and LICENSE, with the same limits as import."""
    files, total = [], 0
    for p in sorted(folder.rglob("*")):
        if p.is_symlink():
            raise AppError(
                422, INVALID_FAMILY, f"“{p.relative_to(folder)}” is a link, not a file."
            )
        if not p.is_file():
            continue
        rel = p.relative_to(folder)
        if len(rel.parts) == 1 and rel.name.upper().startswith(EXTRA_FILES):
            continue
        files.append(p)
        total += p.stat().st_size
    if len(files) > config.MAX_FILES:
        raise AppError(
            413, TOO_LARGE, f"The family has more than {config.MAX_FILES} files."
        )
    if total > config.MAX_UNZIPPED_BYTES:
        mb = config.MAX_UNZIPPED_BYTES // 1_000_000
        raise AppError(413, TOO_LARGE, f"The family is larger than {mb} MB.")
    return files
