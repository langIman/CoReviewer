"""CallGraph cache management.

Caches the built CallGraph to avoid re-parsing on every request.
Invalidated when a new project is uploaded.
"""

from backend.models.graph_models import CallGraph
from backend.services.analysis.call_graph import build_call_graph
from backend.services.analysis.entry_detector import detect_entry_points
from backend.dao.file_store import get_project_files

_cached_graph: CallGraph | None = None
_cached_project_files: dict[str, str] | None = None


def get_or_build_graph() -> tuple[CallGraph, dict[str, str]]:
    """Get cached graph or build a new one."""
    global _cached_graph, _cached_project_files
    project_files = get_project_files()
    if not project_files:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="No project loaded")

    if _cached_graph is None or _cached_project_files is not project_files:
        _cached_graph = build_call_graph(project_files)
        detect_entry_points(_cached_graph, project_files)
        _cached_project_files = project_files

    return _cached_graph, project_files


def invalidate_cache() -> None:
    """Call when project changes (new upload)."""
    global _cached_graph, _cached_project_files
    _cached_graph = None
    _cached_project_files = None
