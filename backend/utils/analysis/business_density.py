"""业务密度评分工具。

纯 AST 分析，零 LLM 调用，毫秒级。
通过评分找到项目中最具业务逻辑的核心函数。
"""

import ast
import logging
import textwrap

from fastapi import HTTPException

from backend.models.graph_models import ProjectAST
from backend.config import DENSITY_THRESHOLD

logger = logging.getLogger(__name__)

# 基础设施调用名，这些不算业务逻辑
INFRA_CALL_NAMES: set[str] = {
    "include_router", "add_middleware", "add_event_handler",
    "setup", "init", "configure", "mount",
    "print", "log", "logging", "logger",
    "super", "__init__",
}


def _get_callees(qname: str, graph: ProjectAST) -> list[str]:
    """获取函数的所有已解析 callee qualified_names。"""
    seen: set[str] = set()
    result: list[str] = []
    for edge in graph.edges:
        if edge.caller == qname and edge.callee_resolved:
            if edge.callee_resolved not in seen:
                seen.add(edge.callee_resolved)
                result.append(edge.callee_resolved)
    return result


def _score_function(qname: str, graph: ProjectAST, project_files: dict[str, str]) -> float:
    """计算单个函数的业务密度分数。

    score = control_flow × 3 + data_chain × 2 + domain_calls × 1 - infra_calls × 0.5
    """
    defn = graph.definitions.get(qname)
    if not defn:
        return 0.0

    source = project_files.get(defn.file)
    if not source:
        return 0.0

    # 提取函数源码
    lines = source.split("\n")
    func_lines = lines[defn.line_start - 1: defn.line_end]
    func_source = "\n".join(func_lines)

    # 去除缩进后解析 AST
    try:
        tree = ast.parse(textwrap.dedent(func_source))
    except SyntaxError:
        logger.debug("AST parse failed for %s, returning 0.0", qname)
        return 0.0

    # 1. 控制流节点计数
    control_flow = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
            control_flow += 1

    # 2. 数据链：var = func() 且 var 被后续调用使用
    assigned_from_call: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned_from_call.add(target.id)

    data_chain = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for arg in node.args:
                if isinstance(arg, ast.Name) and arg.id in assigned_from_call:
                    data_chain += 1
                    break
            for kw in node.keywords:
                if isinstance(kw.value, ast.Name) and kw.value.id in assigned_from_call:
                    data_chain += 1
                    break

    # 3. 领域调用 vs 基础设施调用（从 ProjectAST edges 统计）
    domain_calls = 0
    infra_calls = 0
    for edge in graph.edges:
        if edge.caller != qname:
            continue
        if edge.callee_name in INFRA_CALL_NAMES:
            infra_calls += 1
        elif edge.callee_resolved:
            domain_calls += 1

    score = control_flow * 3.0 + data_chain * 2.0 + domain_calls * 1.0 - infra_calls * 0.5
    logger.debug(
        "density(%s) = cf=%d*3 + dc=%d*2 + dom=%d*1 - infra=%d*0.5 = %.1f",
        qname, control_flow, data_chain, domain_calls, infra_calls, score,
    )
    return score


def find_key_function(graph: ProjectAST, project_files: dict[str, str]) -> str:
    """找到项目中最具业务逻辑的核心函数。

    算法：
    1. 对每个 entry_point 评分
    2. 最高分 >= 阈值 → 直接返回
    3. 否则下钻到 callees 重新评分（最多 2 层）
    4. Fallback：返回任意层中得分最高的函数
    """
    if not graph.entry_points:
        raise HTTPException(status_code=400, detail="No entry points found in project")

    # 只评分函数/异步函数，跳过类
    entries = [
        qname for qname in graph.entry_points
        if graph.definitions.get(qname) and graph.definitions[qname].kind in ("function", "async_function")
    ]
    if not entries:
        entries = graph.entry_points

    best_qname = entries[0]
    best_score = -999.0

    # Level 0: 入口函数
    for qname in entries:
        score = _score_function(qname, graph, project_files)
        if score > best_score:
            best_score = score
            best_qname = qname

    if best_score >= DENSITY_THRESHOLD:
        logger.info("Key function found at entry level: %s (score=%.1f)", best_qname, best_score)
        return best_qname

    # Level 1: 入口函数的 callees
    level1_candidates: set[str] = set()
    for qname in entries:
        level1_candidates.update(_get_callees(qname, graph))

    for qname in level1_candidates:
        score = _score_function(qname, graph, project_files)
        if score > best_score:
            best_score = score
            best_qname = qname

    if best_score >= DENSITY_THRESHOLD:
        logger.info("Key function found at level 1: %s (score=%.1f)", best_qname, best_score)
        return best_qname

    # Level 2: 再下钻一层
    level2_candidates: set[str] = set()
    for qname in level1_candidates:
        level2_candidates.update(_get_callees(qname, graph))
    level2_candidates -= level1_candidates

    for qname in level2_candidates:
        score = _score_function(qname, graph, project_files)
        if score > best_score:
            best_score = score
            best_qname = qname

    if best_score >= DENSITY_THRESHOLD:
        logger.info("Key function found at level 2: %s (score=%.1f)", best_qname, best_score)
    else:
        logger.info("No function above threshold, fallback: %s (score=%.1f)", best_qname, best_score)

    return best_qname
