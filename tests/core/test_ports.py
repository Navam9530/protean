import socket

import httpx
import respx

from protean import config
from protean.core import ports


def test_ping_identifies_protean(client) -> None:
    assert client.get(config.PING_URL).json() == config.PING_RESPONSE


def test_bind_falls_back_to_next_port_when_taken(monkeypatch) -> None:
    taken = socket.socket()
    taken.bind(("127.0.0.1", 0))  # occupy any free port
    busy = taken.getsockname()[1]
    monkeypatch.setattr(config, "PORT", busy)
    sock = ports.bind_free()
    try:
        assert sock is not None
        assert sock.getsockname()[1] != busy
        assert busy < sock.getsockname()[1] < busy + config.PORT_TRIES
    finally:
        taken.close()
        if sock:
            sock.close()


def test_bind_gives_up_when_every_port_is_taken(monkeypatch) -> None:
    held = []
    first = socket.socket()
    first.bind(("127.0.0.1", 0))
    held.append(first)
    base = first.getsockname()[1]
    monkeypatch.setattr(config, "PORT", base)
    monkeypatch.setattr(config, "PORT_TRIES", 1)  # only the one port we hold
    try:
        assert ports.bind_free() is None
    finally:
        first.close()


def test_is_protean() -> None:
    with respx.mock:
        respx.get(f"http://127.0.0.1:9530{config.PING_URL}").respond(
            json=config.PING_RESPONSE
        )
        respx.get(f"http://127.0.0.1:9531{config.PING_URL}").respond(
            json={"app": "other"}
        )
        respx.get(f"http://127.0.0.1:9532{config.PING_URL}").mock(
            side_effect=httpx.ConnectError("refused")
        )
        assert ports.is_protean(9530)
        assert not ports.is_protean(9531)
        assert not ports.is_protean(9532)


def test_find_running_checks_the_fallback_ports(monkeypatch) -> None:
    monkeypatch.setattr(config, "PORT", 9530)
    with respx.mock:
        for p in range(9530, 9540):
            respx.get(f"http://127.0.0.1:{p}{config.PING_URL}").mock(
                side_effect=httpx.ConnectError("refused")
            )
        respx.get(f"http://127.0.0.1:9533{config.PING_URL}").respond(
            json=config.PING_RESPONSE
        )
        assert ports.find_running() == 9533
