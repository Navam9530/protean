import os
import shutil
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

# Must be set before protean is imported: config reads these once at import.
os.environ["PROTEAN_HOME"] = tempfile.mkdtemp(prefix="protean-test-")
os.environ["PROTEAN_NO_BROWSER"] = "1"

import pytest
from fastapi.testclient import TestClient

from protean import config
from protean.app import create_app
from protean.identity import profile, tokens


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty workspace for each test (never the real ~/.protean)."""
    shutil.rmtree(config.HOME, ignore_errors=True)
    monkeypatch.setattr(config, "GITHUB_MIN_POLL_INTERVAL", 0.01)
    profile.reset_cache()  # the in-memory copies belong to the previous test's home
    tokens.reset_cache()
    return config.HOME


@pytest.fixture
def client(home: Path) -> Iterator[TestClient]:
    with TestClient(create_app(), base_url="http://localhost") as c:
        yield c


@pytest.fixture
def wait_for():
    """Poll /status until it reaches a state (the backend polls GitHub in the background)."""

    def _wait(client: TestClient, state: str, timeout: float = 3.0) -> dict:
        deadline = time.monotonic() + timeout
        body: dict = {}
        while time.monotonic() < deadline:
            body = client.get("/api/auth/github/status").json()
            if body["state"] == state:
                return body
            time.sleep(0.02)
        raise AssertionError(f"never reached {state!r}; last status: {body}")

    return _wait
