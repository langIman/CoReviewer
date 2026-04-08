"""Lead Agent — 编排 Worker 并发分析，生成概览流程图。

流程：
1. find_key_function → 定位核心业务函数
2. 收集被调函数（2 层深度）
3. 分发 Workers 并发语义化
4. 等待完成 → 读 KB → 构建 prompt → LLM 生成流程图
5. 后处理 → 返回 FlowData
"""

import asyncio
import logging

from backend.models.graph_models import ProjectAST
from backend.dao.knowledge_base import KnowledgeBase
from backend.services.agents.config import MAX_WORKER_CONCURRENCY
from backend.services.agents.tools.business_density import find_key_function
from backend.services.agents.mailbox import Mailbox, Message
from backend.services.agents.worker import worker_loop
from backend.services.llm.llm_service import call_qwen
from backend.services.llm.prompts.agent_prompts import build_lead_prompt
from backend.utils.data_format import (
    parse_llm_json,
    normalize_flow_data,
    fill_line_numbers_from_ast,
)

logger = logging.getLogger(__name__)


def _extract_source_with_line_numbers(
    qname: str,
    graph: ProjectAST,
    project_files: dict[str, str],
) -> tuple[str, str]:
    """提取函数源码（带行号），返回 (file_path, numbered_source)。"""
    defn = graph.definitions[qname]
    source = project_files[defn.file]
    source_lines = source.split("\n")

    numbered_lines: list[str] = []
    for i in range(defn.line_start - 1, defn.line_end):
        numbered_lines.append(f"{i + 1:>4}| {source_lines[i]}")

    return defn.file, "\n".join(numbered_lines)


def _collect_needed_functions(key_qname: str, graph: ProjectAST) -> set[str]:
    """收集核心函数的 callees + 下一层 callees（2 层深度）。"""
    needed: set[str] = set()

    # Level 1: 核心函数的直接 callees
    for edge in graph.edges:
        if edge.caller == key_qname and edge.callee_resolved:
            if edge.callee_resolved != key_qname:  # 排除递归
                needed.add(edge.callee_resolved)

    # Level 2: 每个 level-1 callee 的 callees
    level1 = set(needed)
    for qname in level1:
        for edge in graph.edges:
            if edge.caller == qname and edge.callee_resolved:
                if edge.callee_resolved != key_qname:
                    needed.add(edge.callee_resolved)

    return needed


async def generate_overview_with_agents(
    graph: ProjectAST,
    project_files: dict[str, str],
) -> dict:
    """Multi-Agent 概览流程图生成。

    Returns FlowData {nodes, edges}。
    """
    # Phase 1: 发现核心函数
    key_qname = find_key_function(graph, project_files)
    key_file, key_source = _extract_source_with_line_numbers(key_qname, graph, project_files)
    logger.info("Lead: key function = %s [%s]", key_qname, key_file)

    # Phase 2: 收集需要语义化的被调函数
    needed = _collect_needed_functions(key_qname, graph)
    logger.info("Lead: %d functions to summarize", len(needed))

    # Phase 3: 分发 Workers
    kb = KnowledgeBase()

    if needed:
        mailbox = Mailbox()
        mailbox.register("lead")

        sem = asyncio.Semaphore(MAX_WORKER_CONCURRENCY)
        worker_tasks: list[asyncio.Task] = []
        worker_names: list[str] = []

        for i, qname in enumerate(sorted(needed)):
            worker_name = f"worker-{i}"
            worker_names.append(worker_name)
            mailbox.register(worker_name)

            # 用默认参数捕获循环变量，避免闭包陷阱
            async def _rate_limited_worker(wname=worker_name):
                async with sem:
                    await worker_loop(wname, mailbox, graph, project_files, kb)

            worker_tasks.append(asyncio.create_task(_rate_limited_worker()))

        # 发送任务
        for i, qname in enumerate(sorted(needed)):
            await mailbox.send(Message(
                sender="lead",
                receiver=f"worker-{i}",
                msg_type="task",
                payload={"qualified_name": qname},
            ))

        # 等待所有 done 通知
        for _ in range(len(needed)):
            await mailbox.read_inbox("lead")

        # 关闭 Workers
        for wname in worker_names:
            await mailbox.send(Message(
                sender="lead",
                receiver=wname,
                msg_type="shutdown",
            ))

        # 等待 worker tasks 完成
        results = await asyncio.gather(*worker_tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Worker task %d failed: %s: %s", i, type(result).__name__, result)

    # Phase 4: 构建 Lead prompt → LLM 生成流程图
    kb_text = kb.format_for_prompt()
    logger.debug("KnowledgeBase contents:\n%s", kb_text or "(empty)")
    system_prompt, user_prompt = build_lead_prompt(key_file, key_source, kb_text)
    raw = await call_qwen(system_prompt, user_prompt)

    # Phase 5: 后处理（复用现有管线）
    data = parse_llm_json(raw)
    normalize_flow_data(data)
    fill_line_numbers_from_ast(data, graph)

    return data
