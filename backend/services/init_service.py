"""项目初始化服务。

项目上传后的一站式初始化：清理旧状态 → AST 静态分析 → 持久化。
与文件上传（file_service）解耦，职责单一。
"""

import logging

from backend.dao.ast_store import clear_project_ast
from backend.dao.summary_store import clear_project_summaries
from backend.dao.wiki_store import clear_project_wiki
from backend.utils.analysis.ast_service import get_or_build_ast, invalidate_ast_cache

logger = logging.getLogger(__name__)


def initialize_project(project_name: str) -> None:
    """项目上传后的初始化流程。

    1. 清理旧状态（缓存 + 旧 AST + 旧摘要）
    2. 构建 AST（调用图 + 入口检测 + 持久化到 SQLite）
    """
    # 1. 清理
    invalidate_ast_cache()
    clear_project_ast(project_name)
    clear_project_summaries(project_name)
    clear_project_wiki(project_name)
    logger.info("Old data cleared for project: %s", project_name)

    # 2. 构建 AST
    get_or_build_ast()
    logger.info("Project initialized: %s", project_name)
