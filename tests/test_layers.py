"""The layers of the code and who may import whom, so the structure cannot drift.

    core          infrastructure, knows nothing about families
    family        what a family is: model, folder layout, validation, values
    identity      who the user is on this machine: profile and GitHub token
    integrations  the GitHub API
    modules       the HTTP features; each uses the layers below and never another module

`app` ties the modules together and may import anything; `config` is imported by everyone.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "src" / "protean"
BELOW = {
    "core": set(),
    "family": {"core"},
    "identity": {"core"},
    "integrations": {"core", "identity"},
    "modules": {"core", "family", "identity", "integrations"},
}


def unit(path: Path) -> str:
    """The layer of a file, or for a feature module its own name ("modules.drafts")."""
    parts = path.relative_to(ROOT).with_suffix("").parts
    return ".".join(parts[:2]) if parts[0] == "modules" else parts[0]


def imported(path: Path) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        names = []
        if isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        for name in names:
            parts = name.split(".")
            if parts[0] == "protean" and len(parts) > 1:
                found.add(".".join(parts[1:3]) if parts[1] == "modules" else parts[1])
    return found


FILES = sorted(
    p
    for p in ROOT.rglob("*.py")
    if "web_dist" not in p.parts and unit(p) not in ("app", "config", "__init__")
)


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_a_file_imports_only_from_the_layers_below(path: Path) -> None:
    me = unit(path)
    layer = me.split(".")[0]
    allowed = BELOW[layer] | {me, "config"}
    stray = {i for i in imported(path) if i not in allowed and i != "app"}
    assert not stray, f"{path.relative_to(ROOT)} ({me}) must not import {sorted(stray)}"
    assert "app" not in imported(path), "only the entry point imports app"
