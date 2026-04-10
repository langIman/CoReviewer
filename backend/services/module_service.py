"""基于摘要 + 调用图的模块划分服务。"""

import logging
from collections import defaultdict

from backend.dao.file_store import get_project_name, get_project_files
from backend.dao.summary_store import get_summaries_by_type
from backend.dao.graph_cache import get_cached, is_cache_valid
from backend.services.agent import Agent
from backend.services.llm.prompts.module_prompts import build_module_split_prompt
from backend.utils.data_format import parse_llm_json

logger = logging.getLogger(__name__)


def _build_folder_dependencies() -> dict[str, list[str]] | None:
    """从 ProjectAST 的 ModuleNode.imports 聚合出文件夹级依赖。"""
    project_files = get_project_files()
    if not project_files or not is_cache_valid(project_files):
        return None

    graph = get_cached()
    if not graph or not graph.modules:
        return None

    folder_deps: dict[str, set[str]] = defaultdict(set)
    for path, module_node in graph.modules.items():
        src_folder = path.rsplit("/", 1)[0] if "/" in path else "."
        for imp_path in module_node.imports:
            dst_folder = imp_path.rsplit("/", 1)[0] if "/" in imp_path else "."
            if dst_folder != src_folder:
                folder_deps[src_folder].add(dst_folder)

    return {k: sorted(v) for k, v in folder_deps.items()} or None


def _collect_root_file_summaries(
    project_name: str, folder_summaries: list[dict]
) -> list[dict]:
    """收集不属于任何文件夹摘要的根目录散文件摘要。"""
    folder_paths = {s["path"] for s in folder_summaries}
    file_summaries = get_summaries_by_type(project_name, "file")
    # 只保留其父文件夹不在 folder_summaries 中的文件（即根目录散文件）
    root_files = []
    for fs in file_summaries:
        parent = fs["path"].rsplit("/", 1)[0] if "/" in fs["path"] else "."
        if parent not in folder_paths:
            root_files.append(fs)
    return root_files


def _ensure_full_coverage(result: dict, all_paths: set[str]) -> dict:
    """后处理：将 LLM 遗漏的路径追加到最相关的模块中。"""
    modules = result.get("modules", [])
    if not modules:
        return result

    assigned: set[str] = set()
    for mod in modules:
        assigned.update(mod.get("paths", []))

    missing = all_paths - assigned
    if not missing:
        return result

    logger.warning("Module split missed %d paths, assigning to nearest module: %s", len(missing), missing)

    # 将遗漏的路径分配给路径前缀最匹配的模块，无匹配则归入最后一个模块
    for path in missing:
        best_mod = modules[-1]
        best_overlap = 0
        for mod in modules:
            for existing in mod.get("paths", []):
                # 计算公共前缀长度
                prefix = _common_prefix(path, existing)
                if prefix > best_overlap:
                    best_overlap = prefix
                    best_mod = mod
        best_mod["paths"].append(path)

    return result


def _common_prefix(a: str, b: str) -> int:
    """返回两个路径的公共前缀段数。"""
    parts_a = a.split("/")
    parts_b = b.split("/")
    count = 0
    for pa, pb in zip(parts_a, parts_b):
        if pa == pb:
            count += 1
        else:
            break
    return count


async def generate_module_split() -> dict:
    """基于文件夹摘要和 import 依赖，调用 LLM 拆分项目模块。"""
    project_name = get_project_name()
    if not project_name:
        raise ValueError("No project loaded")

    folder_summaries = get_summaries_by_type(project_name, "folder")
    file_summaries = get_summaries_by_type(project_name, "file")

    if not folder_summaries and not file_summaries:
        raise ValueError("No summaries found. Please generate summaries first.")

    # 单层目录（无子文件夹）时，直接用文件摘要做模块划分
    if not folder_summaries:
        root_file_summaries = file_summaries
    else:
        root_file_summaries = _collect_root_file_summaries(project_name, folder_summaries)

    folder_deps = _build_folder_dependencies()

    system, user = build_module_split_prompt(
        project_name, folder_summaries, root_file_summaries, folder_deps
    )
    agent = Agent(system_prompt=system, tools=[])
    raw = await agent.run(user)
    result = parse_llm_json(raw)

    # 后处理：确保全覆盖
    all_paths = {s["path"] for s in folder_summaries} | {s["path"] for s in root_file_summaries}
    result = _ensure_full_coverage(result, all_paths)

    return result
