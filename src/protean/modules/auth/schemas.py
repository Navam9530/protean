"""Every data shape of the auth module: API models first, then the login in progress."""

import asyncio
from dataclasses import dataclass
from typing import Literal

from protean.core.schemas import CamelModel
from protean.identity.profile import Profile
from protean.integrations.github.oauth import DeviceCode

# Only scopes Protean actually needs. Login itself needs none (identity only).
LoginState = Literal["idle", "pending", "authorized", "denied", "expired", "error"]


# ---- API ---------------------------------------------------------------------
class LoginStatusOut(CamelModel):
    """Returned by start, status and cancel alike."""

    state: LoginState
    user_code: str | None = None  # pending: show this to the user
    verification_uri: str | None = None  # pending: where they enter it
    expires_in: int | None = None  # pending: seconds left
    error: str | None = None
    profile: Profile | None = None  # authorized


# ---- the login in progress ---------------------------------------------------
@dataclass
class LoginAttempt:
    device: DeviceCode
    scopes: list[str]
    deadline: float  # loop.time() value
    state: LoginState = "pending"
    error: str | None = None
    task: asyncio.Task | None = None
