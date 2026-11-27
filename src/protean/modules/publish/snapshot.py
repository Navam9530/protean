"""The new snapshot of a family: the files to commit, with the README and LICENSE worked out, and
the upload of every file as a blob."""

import asyncio
import datetime
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path

from protean.core.sse import Event
from protean.core.storage import write_text_atomic
from protean.family import licenses
from protean.integrations.github import repos
from protean.modules.publish.schemas import PublishRequest

UPLOADS_AT_ONCE = 8


@dataclass
class Item:
    """One file of the new snapshot: bytes to upload, or a blob that is already in the repo."""

    path: str
    data: bytes | None = None
    sha: str | None = None
    mode: str = "100644"


async def _license_item(key: licenses.License, owner: str) -> Item:
    text = await repos.license_text(key)
    text = text.replace("[year]", str(datetime.date.today().year)).replace(
        "[fullname]", owner
    )
    return Item("LICENSE", text.encode("utf-8"))


async def extras(
    req: PublishRequest,
    folder: Path,
    owner: str,
    remote: list[dict],
) -> list[Item]:
    """README and LICENSE for the new snapshot. A field the user set wins; otherwise the repo's
    own files stay as they are (`remote`, empty for a new repo), and a new repo takes the family
    folder's files."""
    items: list[Item] = []

    def existing(prefixes: tuple[str, ...]) -> list[Item]:
        if remote:
            return [
                Item(e["path"], sha=e["sha"], mode=e["mode"])
                for e in remote
                if e["type"] == "blob" and e["path"].upper().startswith(prefixes)
            ]
        return [
            Item(f.name, f.read_bytes()) for f in licenses.root_files(folder, prefixes)
        ]

    if req.readme is not None:
        items.append(Item("README.md", req.readme.encode("utf-8")))
    else:
        items += existing(("README",)) or [Item("README.md", b"")]
    if req.license is not None:
        items.append(await _license_item(req.license, owner))
    else:
        items += existing(licenses.LICENSE_FILES)
    return items


async def upload(
    owner: str, repo: str, folder: Path, files: list[Path], extras: list[Item]
) -> AsyncGenerator[Event | list[dict]]:
    """Upload every file as a blob, reporting progress; the last value is the tree entries."""
    items = [
        Item(
            p.relative_to(folder).as_posix(),
            p.read_bytes(),
            mode="100755" if p.stat().st_mode & 0o111 else "100644",
        )
        for p in files
    ] + extras
    todo = [i for i in items if i.sha is None]
    gate = asyncio.Semaphore(UPLOADS_AT_ONCE)

    async def send(item: Item) -> None:
        async with gate:
            assert item.data is not None
            item.sha = await repos.create_blob(owner, repo, item.data)

    tasks = [asyncio.create_task(send(i)) for i in todo]
    try:
        for count, finished in enumerate(asyncio.as_completed(tasks), 1):
            await finished
            yield "progress", {"id": "upload", "done": count, "total": len(tasks)}
    finally:
        for t in tasks:
            t.cancel()
    yield [
        {"path": i.path, "mode": i.mode, "type": "blob", "sha": i.sha} for i in items
    ]


def remember(folder: Path, extras: list[Item], req: PublishRequest) -> None:
    """Keep what the user set in the family folder, so the form shows it next time."""
    for field, prefixes in (
        ("readme", ("README",)),
        ("license", licenses.LICENSE_FILES),
    ):
        if getattr(req, field) is None:
            continue
        for old in licenses.root_files(folder, prefixes):
            old.unlink()
        item = next(
            i
            for i in extras
            if i.data is not None and i.path.upper().startswith(prefixes)
        )
        assert item.data is not None
        write_text_atomic(folder / item.path, item.data.decode("utf-8"))
