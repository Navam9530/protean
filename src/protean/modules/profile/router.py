from fastapi import APIRouter

from protean.identity import profile
from protean.identity.profile import Profile

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=Profile)
def get_profile() -> Profile:
    return profile.get()


@router.post("/skip-github", response_model=Profile)
def skip_github() -> Profile:
    """First-run choice: continue without GitHub, using the OS hostname as owner."""
    return profile.skip_github()
