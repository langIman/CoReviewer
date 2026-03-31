"""ProjectAST 纯缓存。

只负责存取和失效，不含构建逻辑。
"""

from backend.models.graph_models import ProjectAST

_cached_ast: ProjectAST | None = None
_cached_project_files: dict[str, str] | None = None


def get_cached() -> ProjectAST:
    """返回缓存的 ProjectAST（调用前应先检查 is_cache_valid）。"""
    return _cached_ast  # type: ignore


def set_cached(ast_model: ProjectAST, project_files: dict[str, str]) -> None:
    """写入缓存。"""
    global _cached_ast, _cached_project_files
    _cached_ast = ast_model
    _cached_project_files = project_files


def is_cache_valid(project_files: dict[str, str]) -> bool:
    """缓存是否有效（同一份 project_files 且已构建）。"""
    return _cached_ast is not None and _cached_project_files is project_files


def invalidate_cache() -> None:
    """失效缓存（上传新项目时调用）。"""
    global _cached_ast, _cached_project_files
    _cached_ast = None
    _cached_project_files = None
