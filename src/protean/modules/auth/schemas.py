"""Every data shape of the auth module: API models first, then internal records."""

import asyncio
from dataclasses import dataclass
from typing import Literal

from protean.core.schemas import CamelModel
from protean.modules.profile.schemas import Profile

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


# ---- GitHub responses --------------------------------------------------------
@dataclass(frozen=True)
class DeviceCode:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


@dataclass(frozen=True)
class TokenPoll:
    """One poll result: a granted token, or `error` saying why not yet."""

    access_token: str | None = None
    scope: str = ""
    error: str | None = (
        None  # authorization_pending, slow_down, expired_token, access_denied, ...
    )
    interval: int | None = None  # new interval, sent with slow_down


@dataclass(frozen=True)
class GithubUser:
    login: str
    avatar_url: str | None


# ---- the login in progress ---------------------------------------------------
@dataclass
class LoginAttempt:
    device: DeviceCode
    scopes: list[str]
    deadline: float  # loop.time() value
    state: LoginState = "pending"
    error: str | None = None
    task: asyncio.Task | None = None
