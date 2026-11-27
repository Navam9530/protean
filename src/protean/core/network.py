"""One shared HTTP client for every GitHub call, so connections are reused.

Created on first use and closed when the app shuts down.
"""

import httpx

_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=15, follow_redirects=True)
    return _client


async def close() -> None:
    global _client
    c, _client = _client, None
    if c:
        await c.aclose()
