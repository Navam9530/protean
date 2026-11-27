"""Before a family is created: is its name free on the signed-in user's GitHub account?"""

from protean.core.errors import ALREADY_EXISTS, AppError
from protean.identity import profile, tokens
from protean.integrations.github import repos


async def ensure_free(owner: str, repo: str) -> None:
    """Refuse a family whose GitHub repo already exists, so the user imports it instead.

    Only when signed in with GitHub, and only a best effort: offline, rate-limited or any other
    trouble lets the family be created. Publishing checks again, by the `protean` topic.
    """
    if not profile.is_github() or not tokens.access_token():
        return
    try:
        found = await repos.get_repo(owner, repo)
    except AppError:
        return
    if found:
        raise AppError(
            409,
            ALREADY_EXISTS,
            f"A repository named {owner}/{repo} already exists on GitHub. "
            "You can import it from the marketplace instead.",
        )
