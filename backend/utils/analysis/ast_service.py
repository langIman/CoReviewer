"""ProjectAST 核心构建服务。

编排 call_graph + entry_detector+import_analysis，生成完整的 ProjectAST。
通过 DAO 层缓存避免重复解析。
"""

from fastapi import HTTPException

from backend.models.graph_models import ProjectAST
from backend.dao.file_store import get_project_files
from backend.dao.graph_cache import get_cached, set_cached, is_cache_valid
from backend.utils.analysis.call_graph import build_call_graph
from backend.utils.analysis.entry_detector import detect_entry_points


def get_or_build_ast() -> tuple[ProjectAST, dict[str, str]]:
    """获取或构建 ProjectAST。

    有缓存则返回缓存，否则重新构建。
    """
    project_files = get_project_files()
    if not project_files:
        raise HTTPException(status_code=400, detail="No project loaded")

    if is_cache_valid(project_files):
        return get_cached(), project_files

    # 构建新的 ProjectAST
    ast_model = build_call_graph(project_files)
    detect_entry_points(ast_model, project_files)
    set_cached(ast_model, project_files)

    return ast_model, project_files
