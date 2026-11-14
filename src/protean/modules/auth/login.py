"""GitHub Device Flow.

start()   asks GitHub for a code and launches a background task that polls for approval.
status()  is what the UI polls. The token never leaves the backend.

Only one login can run at a time, so its state is a module-level variable.
"""

import asyncio
import contextlib
import logging

from protean import config
from protean.core.errors import (
    ALREADY_SIGNED_IN,
    GITHUB_ERROR,
    GITHUB_UNREACHABLE,
    AppError,
)
from protean.modules.auth import github, tokens
from protean.modules.auth.schemas import LoginAttempt, LoginStatusOut, TokenPoll
from protean.modules.profile import store as profile
from protean.modules.profile.schemas import Profile

log = logging.getLogger(__name__)

MAX_CONSECUTIVE_FAILURES = 5
SLOW_DOWN_STEP = 5  # GitHub: add 5 seconds when it says slow_down


_attempt: LoginAttempt | None = None


def _remaining(a: LoginAttempt) -> int:
    return max(0, int(a.deadline - asyncio.get_running_loop().time()))


async def start() -> LoginStatusOut:
    global _attempt
    scopes = sorted(config.GITHUB_SCOPES)
    token = tokens.load_token()
    if token and profile.is_github() and set(scopes) <= tokens.granted_scopes(token):
        raise AppError(409, ALREADY_SIGNED_IN, "Already signed in with GitHub.")

    if _attempt and _attempt.state == "pending":
        if _attempt.scopes == scopes and _remaining(_attempt) > 0:
            return status()  # popup reopened mid-login: same code
        await cancel()

    try:
        device = await github.request_device_code(" ".join(scopes))
    except github.GithubUnavailable as exc:
        raise AppError(
            502, GITHUB_UNREACHABLE, "Could not reach GitHub. Check your connection."
        ) from exc
    except github.GithubError as exc:
        raise AppError(502, GITHUB_ERROR, exc.description) from exc

    deadline = asyncio.get_running_loop().time() + device.expires_in
    _attempt = LoginAttempt(device=device, scopes=scopes, deadline=deadline)
    _attempt.task = asyncio.create_task(_poll(_attempt))
    return status()


def status() -> LoginStatusOut:
    a = _attempt
    if a:
        if a.state == "pending" and _remaining(a) <= 0:
            a.state = "expired"
        if a.state == "pending":
            return LoginStatusOut(
                state="pending",
                user_code=a.device.user_code,
                verification_uri=a.device.verification_uri,
                expires_in=_remaining(a),
            )
        return LoginStatusOut(state=a.state, error=a.error)
    if profile.is_github() and tokens.load_token() is not None:
        return LoginStatusOut(state="authorized", profile=profile.get())
    return LoginStatusOut(state="idle")


async def cancel() -> LoginStatusOut:
    global _attempt
    a, _attempt = _attempt, None
    if a and a.task and not a.task.done():
        a.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await a.task
    return status()


async def logout() -> Profile:
    """Forget the token and fall back to the local profile."""
    await cancel()
    tokens.delete_token()
    return profile.clear_github()


async def _poll(a: LoginAttempt) -> None:
    loop = asyncio.get_running_loop()
    interval: float = a.device.interval  # grows when GitHub says slow_down
    failures = 0
    try:
        while True:
            await asyncio.sleep(max(interval, config.GITHUB_MIN_POLL_INTERVAL))
            if loop.time() >= a.deadline:
                a.state = "expired"
                return
            try:
                result = await github.poll_token(a.device.device_code)
            except github.GithubUnavailable:
                failures += 1
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    a.state, a.error = "error", "Lost connection to GitHub."
                    return
                continue
            failures = 0

            if result.access_token:
                await _complete(a, result)
                return
            match result.error:
                case "authorization_pending":
                    pass
                case "slow_down":
                    interval = (
                        result.interval
                        if result.interval is not None
                        else interval + SLOW_DOWN_STEP
                    )
                case "access_denied":
                    a.state = "denied"
                    return
                case "expired_token":
                    a.state = "expired"
                    return
                case other:
                    a.state, a.error = "error", f"GitHub rejected the login ({other})."
                    return
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("GitHub login failed unexpectedly")
        a.state, a.error = "error", "Unexpected error during GitHub login."


async def _complete(a: LoginAttempt, granted: TokenPoll) -> None:
    """Token granted: read the GitHub profile, then save token and profile together."""
    global _attempt
    assert granted.access_token
    try:
        user = await github.get_user(granted.access_token)
    except github.GithubUnavailable, github.GithubError:
        log.exception("Could not fetch the GitHub profile after login")
        a.state, a.error = "error", "Signed in, but could not read your GitHub profile."
        return
    tokens.save_token(granted.access_token, granted.scope)
    try:
        profile.set_github(user.login, user.avatar_url)
    except Exception:
        tokens.delete_token()  # don't leave a token without a matching profile
        raise
    _attempt = None  # success: status() now derives "authorized" from the stored state
