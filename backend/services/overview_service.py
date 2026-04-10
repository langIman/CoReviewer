"""概览流程图生成服务。

两阶段架构：
1. 初始化（硬编码）：AST 分析 + 并发函数摘要
2. Agent 子任务：LLM 生成流程图
"""

import asyncio
import logging

from backend.config import MAX_WORKER_CONCURRENCY
from backend.models.graph_models import ProjectAST
from backend.services.agent import Agent
from backend.services.llm.llm_service import call_qwen
from backend.services.llm.prompts.agent_prompts import (
    LEAD_SYSTEM_PROMPT,
    build_lead_prompt,
    build_worker_prompt,
)
from backend.utils.analysis.ast_service import get_or_build_ast
from backend.utils.analysis.business_density import find_key_function
from backend.utils.data_format import (
    parse_llm_json,
    normalize_flow_data,
    fill_line_numbers_from_ast,
)

logger = logging.getLogger(__name__)

TRIVIAL_LINE_THRESHOLD = 5


# ---------------------------------------------------------------------------
# 阶段 1：初始化（硬编码，不走 Agent）
# ---------------------------------------------------------------------------

def _extract_source_with_line_numbers(
    qname: str,
    graph: ProjectAST,
    project_files: dict[str, str],
) -> tuple[str, str]:
    """提取函数源码（带行号），返回 (file_path, numbered_source)。"""
    defn = graph.definitions[qname]
    source = project_files[defn.file]
    source_lines = source.split("\n")
    numbered_lines = [
        f"{i + 1:>4}| {source_lines[i]}"
        for i in range(defn.line_start - 1, defn.line_end)
    ]
    return defn.file, "\n".join(numbered_lines)


def _collect_needed_functions(key_qname: str, graph: ProjectAST) -> set[str]:
    """收集核心函数的 callees + 下一层 callees（2 层深度）。"""
    needed: set[str] = set()
    for edge in graph.edges:
        if edge.caller == key_qname and edge.callee_resolved:
            if edge.callee_resolved != key_qname:
                needed.add(edge.callee_resolved)
    level1 = set(needed)
    for qname in level1:
        for edge in graph.edges:
            if edge.caller == qname and edge.callee_resolved:
                if edge.callee_resolved != key_qname:
                    needed.add(edge.callee_resolved)
    return needed


async def _summarize_function(
    qname: str,
    graph: ProjectAST,
    project_files: dict[str, str],
    semaphore: asyncio.Semaphore,
) -> tuple[str, str]:
    """对单个函数生成摘要，返回 (qualified_name, summary_text)。"""
    async with semaphore:
        defn = graph.definitions.get(qname)
        if not defn:
            short_name = qname.split("::")[-1] if "::" in qname else qname
            return qname, f"函数 {short_name}"

        line_count = defn.line_end - defn.line_start + 1

        # 快捷路径：简单函数或有 docstring
        if line_count <= TRIVIAL_LINE_THRESHOLD or defn.docstring:
            return qname, defn.docstring or f"函数 {defn.name}"

        # 提取源码
        source = project_files.get(defn.file)
        if not source:
            return qname, defn.docstring or f"函数 {defn.name}"

        lines = source.split("\n")
        func_source = "\n".join(lines[defn.line_start - 1: defn.line_end])

        try:
            from backend.config import get_file_language
            from backend.utils.analysis.ts_parser import format_signature
            signature = format_signature(defn, get_file_language(defn.file))
            system_prompt, user_prompt = build_worker_prompt(
                func_name=defn.name,
                file_path=defn.file,
                signature=signature,
                source_code=func_source,
            )
            summary = (await call_qwen(system_prompt, user_prompt)).strip()
            return qname, summary
        except Exception as e:
            logger.warning("Summarize failed for %s: %s", qname, e)
            return qname, defn.docstring or f"函数 {defn.name}"


def _format_summaries(summaries: dict[str, str], graph: ProjectAST) -> str:
    """格式化摘要文本，与原 KnowledgeBase.format_for_prompt() 输出一致。"""
    if not summaries:
        return ""
    lines = []
    for qname in sorted(summaries):
        defn = graph.definitions.get(qname)
        if defn:
            params_str = ", ".join(defn.params)
            short_name = qname.split("::")[-1] if "::" in qname else qname
            lines.append(f"- {short_name}({params_str}): {summaries[qname]}")
        else:
            short_name = qname.split("::")[-1] if "::" in qname else qname
            lines.append(f"- {short_name}: {summaries[qname]}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 阶段 2：Agent 生成流程图
# ---------------------------------------------------------------------------

async def generate_overview() -> dict:
    """生成概览流程图。

    阶段 1（初始化）：AST 分析 + 并发函数摘要
    阶段 2（Agent）：LLM 生成流程图
    """
    graph, project_files = get_or_build_ast()

    # === 阶段 1：初始化 ===

    # 1. 找核心函数（纯 AST，毫秒级）
    key_qname = find_key_function(graph, project_files)
    key_file, key_source = _extract_source_with_line_numbers(key_qname, graph, project_files)
    logger.info("Key function: %s [%s]", key_qname, key_file)

    # 2. 收集需要摘要的被调函数（纯 AST）
    needed = _collect_needed_functions(key_qname, graph)
    logger.info("%d functions to summarize", len(needed))

    # 3. 并发摘要（硬编码 asyncio.gather，替代 Worker/Mailbox）
    summaries: dict[str, str] = {}
    if needed:
        sem = asyncio.Semaphore(MAX_WORKER_CONCURRENCY)
        tasks = [
            _summarize_function(qname, graph, project_files, sem)
            for qname in sorted(needed)
        ]
        results = await asyncio.gather(*tasks)
        summaries = dict(results)

    kb_text = _format_summaries(summaries, graph)

    # === 阶段 2：Agent 生成流程图 ===
    _, user_prompt = build_lead_prompt(key_file, key_source, kb_text)
    agent = Agent(system_prompt=LEAD_SYSTEM_PROMPT, tools=[])
    raw = await agent.run(user_prompt)

    # 后处理
    data = parse_llm_json(raw)
    normalize_flow_data(data)
    fill_line_numbers_from_ast(data, graph)

    return data
