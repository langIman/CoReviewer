"""ProjectAST 核心构建服务。

编排 call_graph + entry_detector+import_analysis，生成完整的 ProjectAST。
三级查找：内存缓存 → SQLite → 重新构建。
"""

import logging

from fastapi import HTTPException

from backend.models.graph_models import ProjectAST
from backend.dao.file_store import get_project_files, get_project_name
from backend.dao.ast_store import save_project_ast, load_project_ast
from backend.utils.analysis.call_graph import build_call_graph
from backend.utils.analysis.entry_detector import detect_entry_points

logger = logging.getLogger(__name__)

_cached_ast: ProjectAST | None = None
_cached_project_files: dict[str, str] | None = None


def invalidate_ast_cache() -> None:
    """清空内存缓存（上传新项目时调用）。"""
    global _cached_ast, _cached_project_files
    _cached_ast = None
    _cached_project_files = None


def get_or_build_ast() -> tuple[ProjectAST, dict[str, str]]:
    """获取或构建 ProjectAST。

    三级查找：
    1. 内存缓存命中 → 直接返回
    2. 内存未命中 → 从 SQLite 加载 → 写入内存缓存 → 返回
    3. SQLite 也没有 → 重新构建 → 同时写入 SQLite 和内存缓存
    """
    global _cached_ast, _cached_project_files

    project_files = get_project_files()
    if not project_files:
        raise HTTPException(status_code=400, detail="No project loaded")

    # 1. 内存缓存
    if _cached_ast is not None and _cached_project_files is project_files:
        return _cached_ast, project_files

    # 2. SQLite
    project_name = get_project_name()
    if project_name:
        ast_model = load_project_ast(project_name)
        if ast_model:
            logger.info("AST loaded from SQLite for project: %s", project_name)
            _cached_ast = ast_model
            _cached_project_files = project_files
            return ast_model, project_files

    # 3. 重新构建
    ast_model = build_call_graph(project_files)
    detect_entry_points(ast_model, project_files)
    _cached_ast = ast_model
    _cached_project_files = project_files

    if project_name:
        save_project_ast(project_name, ast_model)
        logger.info("AST built and saved to SQLite for project: %s", project_name)

    return ast_model, project_files
