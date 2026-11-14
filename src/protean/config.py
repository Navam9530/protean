"""Runtime configuration, read once at import.

Use as `from protean import config` and read `config.X` at call time, so tests can monkeypatch.
"""

import os
from importlib.metadata import metadata
from pathlib import Path

# Single source of truth: [project] in pyproject.toml (re-run `uv sync` after changing it).
_PROJECT = metadata("protean")
VERSION = _PROJECT["Version"]
DESCRIPTION = _PROJECT["Summary"]

HOME = Path(os.environ.get("PROTEAN_HOME", "~/.protean")).expanduser()
FAMILIES_DIR = HOME / "families"
KEYS_DIR = HOME / "keys"
SETTINGS_FILE = HOME / "settings.json"
GITHUB_TOKEN_FILE = KEYS_DIR / "github.json"

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"  # beside src/
LOG_FILE = LOG_DIR / "protean.log"
LOG_MAX_BYTES = 5_000_000  # 5 MB
LOG_BACKUPS = 5

HOST = "127.0.0.1"
PORT = int(os.environ.get("PROTEAN_PORT", "9530"))
PORT_TRIES = 10
OPEN_BROWSER = not os.environ.get("PROTEAN_NO_BROWSER")
ALLOWED_HOSTS = ("localhost", "127.0.0.1")
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

PING_URL = "/ping"
PING_RESPONSE = {"app": "protean"}

GITHUB_CLIENT_ID = "Ov23licFzZUlfSOQC8iY"
GITHUB_SCOPES = ("public_repo",)
GITHUB_MIN_POLL_INTERVAL = 1.0
