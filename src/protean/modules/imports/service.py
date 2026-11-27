"""Import a repo, or an uploaded folder, as a stream: unpack safely into imports/<id>/ and
validate it as a family. Both ways share the validation and end the same way.

The folder is kept only when every check passed. It is deleted when anything fails or the client
goes away, and by the merge or discard that comes after.
"""

import asyncio
import contextlib
import shutil
import uuid
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from typing import BinaryIO

from protean import config
from protean.core.errors import AppError
from protean.core.sse import Event
from protean.family.validation import archive, integrity
from protean.family.validation.stream import Checked, validate
from protean.integrations.github import availability, read
from protean.modules.imports.schemas import ImportOut


def discard(import_id: str) -> None:
    """Delete an import that was not used. Fine to call when the folder is already gone."""
    shutil.rmtree(config.IMPORTS_DIR / import_id, ignore_errors=True)


def _size(n: int) -> str:
    return f"{n / 1_000_000:.1f} MB" if n >= 100_000 else f"{n // 1000} KB"


async def _download(
    owner: str, repo: str, version: str | None, folder: Path
) -> AsyncGenerator[Event]:
    zip_path = config.IMPORTS_DIR / f"{folder.name}.zip"
    try:
        yield "stage", {"id": "download", "state": "running"}
        sizes = read.download_zip(owner, repo, zip_path, version)
        async with contextlib.aclosing(sizes):
            async for size in sizes:
                yield "progress", {"id": "download", "bytes": size}
        note = _size(zip_path.stat().st_size)
        yield "stage", {"id": "download", "state": "done", "note": note}

        yield "stage", {"id": "extract", "state": "running"}
        folder.mkdir()
        files = await asyncio.to_thread(archive.extract, zip_path, folder)
        yield "stage", {"id": "extract", "state": "done", "note": f"{files} files"}
    finally:
        zip_path.unlink(missing_ok=True)


async def _unpack(
    files: list[tuple[str, BinaryIO]], folder: Path
) -> AsyncGenerator[Event]:
    yield "stage", {"id": "extract", "state": "running"}
    folder.mkdir()
    count = await asyncio.to_thread(archive.store_files, folder, files)
    yield "stage", {"id": "extract", "state": "done", "note": f"{count} files"}


async def _validate(folder: Path, owner: str, repo: str) -> AsyncGenerator[Event]:
    """The schema and agents stages, then `done`."""
    checked = Checked()
    async for event in validate(folder, checked):
        yield event
    family = checked.family
    assert family is not None  # validate sets it or raises
    result = ImportOut(
        import_id=folder.name,
        owner=owner,
        repo=repo,
        family_version=family.family_version,
        agents=family.agents,
        prompts=integrity.read_prompts(folder, family),
        warnings=checked.warnings,
    )
    yield "done", result.model_dump(mode="json", by_alias=True, exclude_none=True)


async def _import(
    owner: str, repo: str, acquire: Callable[[Path], AsyncGenerator[Event]]
) -> AsyncGenerator[Event]:
    """Run `acquire` (which fills the folder), then validate. Cleans up unless it all passed."""
    folder = config.IMPORTS_DIR / uuid.uuid4().hex
    config.IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stage = ""
    kept = False  # set once the import succeeded; closing the stream after `done` is normal
    try:
        try:
            for steps in (acquire(folder), _validate(folder, owner, repo)):
                async with contextlib.aclosing(steps):
                    async for name, data in steps:
                        if name == "stage" and data["state"] == "running":
                            stage = data["id"]
                        if name == "done":
                            kept = True
                        yield name, data
        except AppError:
            if stage:
                yield "stage", {"id": stage, "state": "error"}
            raise
    except BaseException:  # failure, or the client went away
        if not kept:
            shutil.rmtree(folder, ignore_errors=True)
        raise


def import_repo(
    owner: str, repo: str, version: str | None = None
) -> AsyncGenerator[Event]:
    return _import(owner, repo, lambda folder: _download(owner, repo, version, folder))


async def _unpack_if_free(
    owner: str, repo: str, files: list[tuple[str, BinaryIO]], folder: Path
) -> AsyncGenerator[Event]:
    await availability.ensure_free(owner, repo)  # before anything is written
    async for event in _unpack(files, folder):
        yield event


def import_folder(
    owner: str, repo: str, files: list[tuple[str, BinaryIO]]
) -> AsyncGenerator[Event]:
    """Import a folder the user uploaded from their computer, named <owner>_<repo>."""
    return _import(
        owner, repo, lambda folder: _unpack_if_free(owner, repo, files, folder)
    )
