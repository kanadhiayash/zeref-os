"""Canonical memory APIs for Shiroe."""

from shiroe.memory.core import (
    MemoryRoot,
    MemoryWriter,
    discover_project_root,
    normalize_init_values,
    scaffold_project,
)
from shiroe.memory.models import MemoryRecord, MemoryWrite, RecallResult, SearchResult
from shiroe.memory.service import MemoryService
from shiroe.memory.views import render_views

__all__ = [
    "MemoryRecord",
    "RecallResult",
    "SearchResult",
    "MemoryRoot",
    "MemoryService",
    "MemoryWriter",
    "discover_project_root",
    "normalize_init_values",
    "render_views",
    "scaffold_project",
    "MemoryWrite",
]
