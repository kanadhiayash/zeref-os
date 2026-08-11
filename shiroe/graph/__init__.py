"""Transitional task-graph runtime.

The generic Knowledge Graph surface was removed in vNext Phase 02. The
remaining task-graph compiler/runtime stays only until Phase 04 replaces it
with Work Graph supervision.
"""

from shiroe.graph.runtime import LoopExceeded, run_task_graph
from shiroe.graph.task_graph import TaskGraphError, compile_task_graph

__all__ = [
    "TaskGraphError", "LoopExceeded", "compile_task_graph", "run_task_graph",
]
