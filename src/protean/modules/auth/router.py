from fastapi import APIRouter

from protean.modules.auth import login
from protean.modules.auth.schemas import LoginStatusOut
from protean.modules.profile.schemas import Profile

router = APIRouter(prefix="/auth/github", tags=["auth"])


@router.post("/device", response_model=LoginStatusOut)
async def start_login() -> LoginStatusOut:
    """Begin GitHub Device Flow. Show `userCode` to the user and send them to `verificationUri`."""
    return await login.start()


@router.get("/status", response_model=LoginStatusOut)
def login_status() -> LoginStatusOut:
    return login.status()


@router.post("/cancel", response_model=LoginStatusOut)
async def cancel_login() -> LoginStatusOut:
    return await login.cancel()


@router.post("/logout", response_model=Profile)
async def logout() -> Profile:
    """Delete the stored token and fall back to the local (hostname) profile."""
    return await login.logout()
