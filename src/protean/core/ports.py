"""Pick the port to serve on, and detect a Protean that is already running."""

import os
import socket

import httpx

from protean import config


def _ports() -> range:
    return range(config.PORT, config.PORT + config.PORT_TRIES)


def is_protean(port: int) -> bool:
    """True if a Protean server answers on this port."""
    try:
        reply = httpx.get(f"http://127.0.0.1:{port}{config.PING_URL}", timeout=0.5)
        return reply.json() == config.PING_RESPONSE
    except httpx.HTTPError, ValueError:
        return False


def find_running() -> int | None:
    """Port of an already-running Protean (it may have fallen back to a later port)."""
    return next((p for p in _ports() if is_protean(p)), None)


def bind_free() -> socket.socket | None:
    """Bind the first free port. The caller hands the open socket to uvicorn, so nothing can
    grab the port in between."""
    for port in _ports():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if os.name != "nt":  # on Windows this flag would let two servers share a port
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((config.HOST, port))
        except OSError:
            sock.close()
            continue
        return sock
    return None
