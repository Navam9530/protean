from fastapi import APIRouter

from protean.modules.profile import store
from protean.modules.profile.schemas import Profile

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=Profile)
def get_profile() -> Profile:
    return store.get()


@router.post("/skip-github", response_model=Profile)
def skip_github() -> Profile:
    """First-run choice: continue without GitHub, using the OS hostname as owner."""
    return store.skip_github()
