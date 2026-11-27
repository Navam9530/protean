"""Family fixtures shared by the marketplace and draft tests."""

import io
import json
import zipfile
from pathlib import Path


def family(**changes) -> dict:
    base = {
        "$schema": "https://agentsmp.com/schemas/family/v1.json",
        "schemaVersion": 1,
        "familyVersion": "0.1.0",
        "agents": {
            "id": "lead",
            "name": "lead",
            "description": "Splits the review.",
            "model": {"provider": "anthropic", "name": "m"},
            "mcps": [],
            "skills": [],
            "sub-agents": [
                {
                    "id": "reviewer",
                    "name": "reviewer",
                    "mcps": [],
                    "skills": [],
                    "sub-agents": [],
                }
            ],
        },
    }
    return {**base, **changes}


def make_zip(files: dict[str, str | bytes], top: str = "me-code-crew-abc123") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for path, content in files.items():
            z.writestr(f"{top}/{path}" if top else path, content)
    return buf.getvalue()


def good_files(**extra) -> dict[str, str | bytes]:
    return {
        "family.json": json.dumps(family()),
        "prompts/lead.md": "You lead.",
        "prompts/reviewer.md": "You review.",
        "LICENSE": "MIT",
        "README.md": "# Code crew",
        **extra,
    }


def make_import(
    home: Path, files: dict[str, str | bytes], import_id: str = "a" * 32
) -> str:
    folder = home / "imports" / import_id
    for path, content in files.items():
        target = folder / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode())
    return import_id


Events = list[tuple[str, dict]]


def parse_events(text: str) -> Events:
    events = []
    for block in text.strip().split("\n\n"):
        event, data = block.split("\n")
        events.append(
            (event.removeprefix("event: "), json.loads(data.removeprefix("data: ")))
        )
    return events
