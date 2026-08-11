"""CLI-compatible rendering wrapper for canonical memory views."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shiroe.memory.views import render_views


VIEW_ALIASES = {
    "hot.md": "hot.md",
    "index.md": "project-context.md",
    "decisions": "decisions.md",
    "risks": "risks.md",
    "contradictions": "contradictions.md",
}


def render_memory_view(root: Path | str, view: str) -> dict[str, Any]:
    root_path = Path(root)
    paths = render_views(root_path)
    by_name = {path.name: path for path in paths}
    if view == "all":
        return {
            "view": "all",
            "rendered": [
                {"view": name, "path": str(path)}
                for name, path in sorted(by_name.items())
            ],
        }
    if view not in VIEW_ALIASES:
        raise ValueError(f"unsupported view: {view}")
    filename = VIEW_ALIASES[view]
    path = by_name[filename]
    return {"view": view, "path": str(path)}
