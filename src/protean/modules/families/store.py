"""Saved families, in families/<name>/. Written only by saving a draft (drafts/save.py); here
they are listed, read and deleted. Editing one means making a draft copy of it."""

import shutil

from protean import config
from protean.core.errors import NOT_FOUND, AppError
from protean.core.storage import read_json
from protean.family import published, values
from protean.family.card import card_fields
from protean.family.folder import read_prompts
from protean.modules.families.schemas import FamilyOut, FamilySummary


def list_families() -> list[FamilySummary]:
    out = []
    for folder in config.FAMILIES_DIR.iterdir():
        if folder.name.startswith(".") or not (folder / "family.json").is_file():
            continue  # a family that is being swapped in
        family = read_json(folder / "family.json") or {}
        out.append(
            FamilySummary(
                **card_fields(
                    folder, family, int((folder / "family.json").stat().st_mtime * 1000)
                ),
                published_family_version=published.version(folder.name),
                listed=published.listed(folder.name),
            )
        )
    return sorted(out, key=lambda f: f.updated_at, reverse=True)


def read(name: str) -> FamilyOut:
    folder = config.FAMILIES_DIR / name
    family = read_json(folder / "family.json")
    if family is None:
        raise AppError(404, NOT_FOUND, f"There is no family named “{name}”.")
    return FamilyOut(
        name=name,
        family=family,
        prompts=read_prompts(folder),
        secrets=values.read("family", name),
    )


def delete(name: str) -> None:
    """Delete the saved family from this machine. Fine when it is already gone. A draft of the
    same name is left alone (it becomes a family that has never been saved)."""
    shutil.rmtree(config.FAMILIES_DIR / name, ignore_errors=True)
    values.delete("family", name)
    published.forget(name)
