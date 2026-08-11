"""Canonical generated Markdown views for memory."""

from __future__ import annotations

from pathlib import Path

from shiroe.storage.state import StateDB
from shiroe.storage.views import render_all


def render_views(root: Path | str) -> list[Path]:
    """Render all memory views from canonical SQLite state only."""
    db = StateDB(root)
    db.migrate()
    return render_all(Path(root), db.connect())
