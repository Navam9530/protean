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
IMPORTS_DIR = HOME / "imports"  # downloaded repos (short-lived)
DRAFTS_DIR = HOME / "drafts"  # families being built; never deleted automatically
FAMILIES_DIR = HOME / "families"
KEYS_DIR = HOME / "keys"
PROFILE_FILE = HOME / "profile.json"
PUBLISHED_FILE = HOME / "published.json"  # what was last published, by family name
GITHUB_TOKEN_FILE = KEYS_DIR / "github.json"
LOG_DIR = HOME / "logs"
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

SCHEMA_VERSION = 1  # the only family.json schema this Protean understands
SCHEMA_URL = "https://agentsmp.com/schemas/family/v1.json"

# Marketplace. The limits apply to importing and publishing, so both sides agree.
MARKETPLACE_TOPIC = "agents-marketplace"
PROTEAN_TOPIC = "protean"  # marks a repo that Protean created, so it may push to it
SEARCH_PAGE_SIZE = 20
SEARCH_CACHE_SECONDS = 60
MAX_ZIP_BYTES = 20_000_000  # ~20 MB
MAX_UNZIPPED_BYTES = 50_000_000  # ~50 MB
MAX_FILES = 500
MAX_README_CHARS = 200_000
DRAFT_DISK_FACTOR = 2  # a draft may hold removed items up to this many times the limits
