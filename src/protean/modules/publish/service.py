"""Publish a saved family to the user's own GitHub repo, as a stream.

Stages: check, repo, upload, commit, tag, topics, then `done` or `error`. One commit on top of
the repo's current head, never forced, so every earlier version stays in the history; the
version is also tagged. The family is replaced as a whole snapshot: a skill deleted here is
gone from the new commit but still in the old ones. Only repos that carry the `protean` topic
(made by Protean) are pushed to.
"""

from collections.abc import AsyncGenerator

from protean import config
from protean.core.errors import (
    CONFLICT,
    NOT_FOUND,
    NOT_PROTEAN_REPO,
    REPO_NOT_FOUND,
    AppError,
)
from protean.core.sse import Event
from protean.family import licenses, published
from protean.integrations.github import repos
from protean.modules.publish import preflight, snapshot
from protean.modules.publish.schemas import PublishForm, PublishRequest


async def publish(name: str, req: PublishRequest) -> AsyncGenerator[Event]:
    folder = config.FAMILIES_DIR / name
    stage = ""

    def running(stage_id: str) -> Event:
        nonlocal stage
        stage = stage_id
        return "stage", {"id": stage_id, "state": "running"}

    try:
        yield running("check")
        family = preflight.check(name, folder)
        files = preflight.family_files(folder)
        yield "stage", {"id": "check", "state": "done", "note": f"{len(files)} files"}

        owner, repo_name = name.split("_", 1)
        yield running("repo")
        repo = await repos.get_repo(owner, repo_name)
        created = repo is None
        if repo is None:
            repo = await repos.create_repo(repo_name, req.description or "")
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
                await repos.set_description(owner, repo_name, req.description)
        owner = repo["owner"]["login"]  # the login's own spelling
        branch = repo["default_branch"]
        tag = f"v{family.family_version}"
        tagged = not created and await repos.tag_exists(owner, repo_name, tag)
        if tagged and published.version(name) != family.family_version:
            raise AppError(
                409,
                CONFLICT,
                f"The repository already has a tag {tag} that Protean did not publish. "
                "Change the family version and save, then publish again.",
            )
        yield "stage", {"id": "repo", "state": "done", "note": note}

        yield running("upload")
        commit, head_tree = await repos.head(owner, repo_name, branch, fresh=created)
        remote = (
            [] if created else await repos.root_entries(owner, repo_name, head_tree)
        )
        extras = await snapshot.extras(req, folder, owner, remote)
        entries: list[dict] = []
        uploads = snapshot.upload(owner, repo_name, folder, files, extras)
        async for item in uploads:
            if isinstance(item, tuple):
                yield item
            else:
                entries = item
        yield "stage", {"id": "upload", "state": "done"}

        yield running("commit")
        tree = await repos.create_tree(owner, repo_name, entries)
        if tree == head_tree:
            note = "no changes"
        else:
            commit = await repos.create_commit(
                owner, repo_name, f"Publish v{family.family_version}", tree, commit
            )
            await repos.move_branch(owner, repo_name, branch, commit)
            note = commit[:7]
        yield "stage", {"id": "commit", "state": "done", "note": note}

        yield running("tag")
        # An existing tag here is this same version published before (a README or license
        # update): it stays where it is.
        if not tagged:
            await repos.create_tag(owner, repo_name, tag, commit)
        yield "stage", {"id": "tag", "state": "done", "note": tag}

        yield running("topics")
        topics: list[str] = [] if created else repo.get("topics", [])
        wanted = [config.PROTEAN_TOPIC] + (
            [config.MARKETPLACE_TOPIC] if created else []
        )
        merged = topics + [t for t in wanted if t not in topics]
        if merged != topics:
            await repos.set_topics(owner, repo_name, merged)
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

        snapshot.remember(folder, extras, req)
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


async def set_listed(name: str, listed: bool) -> bool:
    """List the repo in the marketplace (add the topic) or unlist it (remove the topic).

    Nothing else changes: the repo and its history stay, and Protean never deletes a repo.
    """
    preflight.owned(name)
    owner, repo_name = name.split("_", 1)
    repo = await repos.get_repo(owner, repo_name)
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
        await repos.set_topics(owner, repo_name, wanted)
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
