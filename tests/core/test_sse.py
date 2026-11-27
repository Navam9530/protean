import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from protean.core.errors import AppError
from protean.core.sse import sse_response

closed: list[str] = []


def frames(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        event, data = block.split("\n")
        out.append(
            (event.removeprefix("event: "), json.loads(data.removeprefix("data: ")))
        )
    return out


@pytest.fixture
def stream():
    app = FastAPI()

    async def finishes():
        try:
            yield "stage", {"id": "a", "note": "né"}
            yield "done", {"ok": True}
            yield "stage", {"id": "never sent"}
        finally:
            closed.append("finishes")

    async def app_error():
        yield "stage", {"id": "a"}
        raise AppError(422, "invalid_family", "bad")

    async def crashes():
        yield "stage", {"id": "a"}
        raise RuntimeError("secret detail")

    async def no_result():
        yield "stage", {"id": "a"}

    cases = {
        "finishes": finishes,
        "app_error": app_error,
        "crashes": crashes,
        "no_result": no_result,
    }

    @app.get("/{name}")
    async def run(name: str):
        return sse_response(cases[name]())

    closed.clear()
    with TestClient(app) as client:
        yield lambda name: client.get(f"/{name}")


def test_events_are_framed_and_the_stream_stops_after_done(stream):
    r = stream("finishes")
    assert r.headers["content-type"].startswith("text/event-stream")
    assert frames(r.text) == [
        ("stage", {"id": "a", "note": "né"}),
        ("done", {"ok": True}),
    ]
    assert closed == ["finishes"]  # the generator was closed, its finally ran


def test_app_errors_become_error_events_with_their_code(stream):
    assert frames(stream("app_error").text)[-1] == (
        "error",
        {"code": "invalid_family", "message": "bad"},
    )


def test_unexpected_errors_do_not_leak_details(stream):
    code, data = frames(stream("crashes").text)[-1]
    assert code == "error" and data["code"] == "internal_error"
    assert "secret" not in data["message"]


def test_a_stream_without_a_result_still_ends_with_an_error(stream):
    assert frames(stream("no_result").text)[-1][0] == "error"
