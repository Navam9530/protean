"""Add an import to a draft: preview what would happen, then do it. How the two are combined, and
what clashes, is worked out in `plan.py`."""

import shutil

from protean.core.errors import INTERNAL, UNRESOLVED, AppError
from protean.family.validation import safety
from protean.modules.drafts import store
from protean.modules.drafts.merge.plan import name_clashes, plan
from protean.modules.drafts.merge.schemas import MergePreview, MergeRequest, MergeTarget
from protean.modules.drafts.schemas import DraftDoc, DraftOut


def preview(name: str, target: MergeTarget) -> MergePreview:
    """What merging would add and what clashes. Changes nothing."""
    m = plan(name, target, {})
    return MergePreview(
        added=m.added,
        merged=m.merged,
        conflicts=m.conflicts,
        renamed=m.renames,
        warnings=name_clashes(m.family.get("agents")),
    )


def merge(name: str, request: MergeRequest) -> DraftOut:
    """Add the import to the draft with the user's answers, then delete the import folder."""
    m = plan(name, request, request.resolutions)
    if m.conflicts:  # nothing has been written yet, so refusing here changes nothing
        shown = ", ".join(c.agent_id for c in m.conflicts)
        raise AppError(409, UNRESOLVED, f"Settle the conflicts first: {shown}.")
    # Check the limits (and ids) of the merged result before touching the disk.
    files = [p for src, _ in m.copies for p in src.rglob("*") if p.is_file()]
    extra = (len(files), sum(p.stat().st_size for p in files))
    safety.check_draft(m.draft_dir, m.family, m.prompts, extra)
    try:
        for src, dst in m.copies:
            shutil.rmtree(dst, ignore_errors=True)  # a leftover from a removed item
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dst, symlinks=True)
    except OSError as exc:
        reason = exc.strerror or type(exc).__name__
        raise AppError(500, INTERNAL, f"Could not copy the files: {reason}.") from exc
    # family.json and the prompts go last: if copying failed above, the draft still lists nothing
    # new (the copied folders would only be unlisted leftovers).
    store.write_files(m.draft_dir, DraftDoc(family=m.family, prompts=m.prompts))
    shutil.rmtree(m.import_dir, ignore_errors=True)  # used up
    return store.read(name)
