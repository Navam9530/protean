"""Server-sent events. An endpoint is an async generator of (event, data) pairs.

A stream always ends with exactly one `done` or `error` event. Once streaming has started the
HTTP status is already 200, so failures are sent as `error` events, not as status codes.
If the client disconnects, the generator is cancelled and its `finally` blocks run.
"""

import contextlib
import json
import logging
from collections.abc import AsyncGenerator, AsyncIterator

from fastapi.responses import StreamingResponse

from protean.core.errors import INTERNAL, AppError

log = logging.getLogger(__name__)

Event = tuple[str, dict]
TERMINAL = ("done", "error")


def _frame(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


def _error(code: str, message: str) -> bytes:
    return _frame("error", {"code": code, "message": message})


async def _frames(events: AsyncGenerator[Event]) -> AsyncIterator[bytes]:
    try:
        async with contextlib.aclosing(events):
            async for event, data in events:
                yield _frame(event, data)
                if event in TERMINAL:
                    return
        yield _error(INTERNAL, "The operation ended without a result.")
    except AppError as exc:
        yield _error(exc.code, exc.message)
    except Exception:
        log.exception("Unexpected failure inside an event stream")
        yield _error(INTERNAL, "Something went wrong. See the log for details.")


def sse_response(events: AsyncGenerator[Event]) -> StreamingResponse:
    return StreamingResponse(
        _frames(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
