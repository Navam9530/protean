"""Publish a saved family to the user's own GitHub repo, as a stream.

Stages: check, repo, upload, commit, tag, topics, then `done` or `error`. One commit on top of
the repo's current head, never forced, so every earlier version stays in the history; the
version is also tagged. The family is replaced as a whole snapshot: a skill deleted here is
gone from the new commit but still in the old ones. Only repos that carry the `protean` topic
(made by Protean) are pushed to.
"""

import asyncio
import datetime
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path

from protean import config
from protean.core.errors import (
    CONFLICT,
    DRAFT_EXISTS,
    INVALID_FAMILY,
    NOT_FOUND,
    NOT_OWNER,
    NOT_PROTEAN_REPO,
    NOT_SIGNED_IN,
    REPO_NOT_FOUND,
    TOO_LARGE,
    AppError,
)
from protean.core.sse import Event
from protean.core.storage import write_text_atomic
from protean.modules.auth import login
from protean.modules.families import licenses, published
from protean.modules.families.schemas import Family, read_family, walk_agents
from protean.modules.families.validation import integrity
from protean.modules.profile import store as profile
from protean.modules.publish import github
from protean.modules.publish.schemas import PublishForm, PublishRequest

UPLOADS_AT_ONCE = 8
EXTRAS = (
    "README",
    *licenses.LICENSE_FILES,
)  # the root files that are not part of the family


@dataclass
class Item:
    """One file of the new snapshot: bytes to upload, or a blob that is already in the repo."""

    path: str
    data: bytes | None = None
    sha: str | None = None
    mode: str = "100644"


def _owned(name: str) -> None:
    """Signed in with GitHub as the owner of the family's repo."""
    if not login.access_token():
        raise AppError(401, NOT_SIGNED_IN, "Sign in with GitHub to publish.")
    owner = name.split("_", 1)[0]
    if owner.lower() != profile.get().owner.lower():
        raise AppError(
            403,
            NOT_OWNER,
            f"You are signed in as {profile.get().owner}, so you can only publish "
            f"families that start with “{profile.get().owner}_”.",
        )


def _check(name: str, folder: Path) -> Family:
    """Everything that must hold before anything is sent to GitHub."""
    if not (folder / "family.json").is_file():
        raise AppError(404, NOT_FOUND, f"There is no saved family named “{name}”.")
    if (config.DRAFTS_DIR / name).exists():
        raise AppError(
            409,
            DRAFT_EXISTS,
            "This family has unsaved changes in a draft. Save or discard the draft first.",
        )
    _owned(name)
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


def _family_files(folder: Path) -> list[Path]:
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
        if len(rel.parts) == 1 and rel.name.upper().startswith(EXTRAS):
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


async def _license_item(key: licenses.License, owner: str) -> Item:
    text = await github.license_text(key)
    text = text.replace("[year]", str(datetime.date.today().year)).replace(
        "[fullname]", owner
    )
    return Item("LICENSE", text.encode("utf-8"))


async def _extras(
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


async def _upload(
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
            item.sha = await github.create_blob(owner, repo, item.data)

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


async def publish(name: str, req: PublishRequest) -> AsyncGenerator[Event]:
    folder = config.FAMILIES_DIR / name
    stage = ""

    def running(stage_id: str) -> Event:
        nonlocal stage
        stage = stage_id
        return "stage", {"id": stage_id, "state": "running"}

    try:
        yield running("check")
        family = _check(name, folder)
        files = _family_files(folder)
        yield "stage", {"id": "check", "state": "done", "note": f"{len(files)} files"}

        owner, repo_name = name.split("_", 1)
        yield running("repo")
        repo = await github.get_repo(owner, repo_name)
        created = repo is None
        if repo is None:
            repo = await github.create_repo(repo_name, req.description or "")
            note = "created"
        elif config.PROTEAN_TOPIC not in repo.get("topics", []):
            raise AppError(
                409,
                NOT_PROTEAN_REPO,
                f"The repository {owner}/{repo_name} was not created by Protean, so "
                "Protean will not change it. If you made it yourself and want Protean to "
                f"update it, add the topic “{config.PROTEAN_TOPIC}” to it on GitHub.",
            )
        else:
            note = "found"
            if req.description is not None:
                await github.set_description(owner, repo_name, req.description)
        owner = repo["owner"]["login"]  # the login's own spelling
        branch = repo["default_branch"]
        tag = f"v{family.family_version}"
        tagged = not created and await github.tag_exists(owner, repo_name, tag)
        if tagged and published.version(name) != family.family_version:
            raise AppError(
                409,
                CONFLICT,
                f"The repository already has a tag {tag} that Protean did not publish. "
                "Change the family version and save, then publish again.",
            )
        yield "stage", {"id": "repo", "state": "done", "note": note}

        yield running("upload")
        commit, head_tree = await github.head(owner, repo_name, branch, fresh=created)
        remote = (
            [] if created else await github.root_entries(owner, repo_name, head_tree)
        )
        extras = await _extras(req, folder, owner, remote)
        entries: list[dict] = []
        uploads = _upload(owner, repo_name, folder, files, extras)
        async for item in uploads:
            if isinstance(item, tuple):
                yield item
            else:
                entries = item
        yield "stage", {"id": "upload", "state": "done"}

        yield running("commit")
        tree = await github.create_tree(owner, repo_name, entries)
        if tree == head_tree:
            note = "no changes"
        else:
            commit = await github.create_commit(
                owner, repo_name, f"Publish v{family.family_version}", tree, commit
            )
            await github.move_branch(owner, repo_name, branch, commit)
            note = commit[:7]
        yield "stage", {"id": "commit", "state": "done", "note": note}

        yield running("tag")
        # An existing tag here is this same version published before (a README or license
        # update): it stays where it is.
        if not tagged:
            await github.create_tag(owner, repo_name, tag, commit)
        yield "stage", {"id": "tag", "state": "done", "note": tag}

        yield running("topics")
        topics: list[str] = [] if created else repo.get("topics", [])
        wanted = [config.PROTEAN_TOPIC] + (
            [config.MARKETPLACE_TOPIC] if created else []
        )
        merged = topics + [t for t in wanted if t not in topics]
        if merged != topics:
            await github.set_topics(owner, repo_name, merged)
        listed = config.MARKETPLACE_TOPIC in merged
        if listed:
            yield "stage", {"id": "topics", "state": "done"}
        else:
            message = (
                f"The repository is not listed in the marketplace: it has no "
                f"“{config.MARKETPLACE_TOPIC}” topic."
            )
            yield "warning", {"message": message}
            yield "stage", {"id": "topics", "state": "warning", "note": "not listed"}

        _remember(folder, extras, req)
        published.record(name, family.family_version, commit, listed, req.description)
        yield (
            "done",
            {
                "url": repo["html_url"],
                "commit": commit,
                "tag": tag,
                "familyVersion": family.family_version,
                "listed": listed,
            },
        )
    except AppError:
        if stage:
            yield "stage", {"id": stage, "state": "error"}
        raise


def _remember(folder: Path, extras: list[Item], req: PublishRequest) -> None:
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


async def set_listed(name: str, listed: bool) -> bool:
    """List the repo in the marketplace (add the topic) or unlist it (remove the topic).

    Nothing else changes: the repo and its history stay, and Protean never deletes a repo.
    """
    _owned(name)
    owner, repo_name = name.split("_", 1)
    repo = await github.get_repo(owner, repo_name)
    if repo is None:
        raise AppError(
            404, REPO_NOT_FOUND, f"{owner}/{repo_name} was not found on GitHub."
        )
    topics: list[str] = repo.get("topics", [])
    if config.PROTEAN_TOPIC not in topics:
        raise AppError(
            409,
            NOT_PROTEAN_REPO,
            f"The repository {owner}/{repo_name} was not created by Protean, so Protean "
            "will not change it.",
        )
    wanted = [t for t in topics if t != config.MARKETPLACE_TOPIC]
    if listed:
        wanted.append(config.MARKETPLACE_TOPIC)
    if wanted != topics:
        await github.set_topics(owner, repo_name, wanted)
    published.set_listed(name, listed)
    return listed


def form(name: str) -> PublishForm:
    """The README and license kind the saved family has now."""
    folder = config.FAMILIES_DIR / name
    if not (folder / "family.json").is_file():
        raise AppError(404, NOT_FOUND, f"There is no saved family named “{name}”.")
    return PublishForm(
        description=published.description(name),
        readme=licenses.read_readme(folder),
        license=licenses.read_license(folder),
    )
