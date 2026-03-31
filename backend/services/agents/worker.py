"""Worker Agent — 读取函数源码，LLM 语义摘要，写入知识库。

生命周期：被 Lead 通过 asyncio.create_task 启动，处理一个任务后等待 shutdown。
错误不变量：无论发生什么，worker 必须 (1) 写入 KB，(2) 发 done 给 Lead。
"""

import logging

from backend.models.graph_models import ProjectAST
from backend.models.agent_models import FunctionSummary
from backend.dao.knowledge_base import KnowledgeBase
from backend.services.llm.llm_service import call_qwen
from backend.services.llm.prompts.agent_prompts import build_worker_prompt
from backend.services.agents.mailbox import Mailbox, Message

logger = logging.getLogger(__name__)

# 小于等于此行数的函数视为简单函数，跳过 LLM
TRIVIAL_LINE_THRESHOLD = 5


def _extract_source(qname: str, graph: ProjectAST, project_files: dict[str, str]) -> str | None:
    """提取函数源码。"""
    defn = graph.definitions.get(qname)
    if not defn:
        return None
    source = project_files.get(defn.file)
    if not source:
        return None
    lines = source.split("\n")
    return "\n".join(lines[defn.line_start - 1: defn.line_end])


def _get_callees(qname: str, graph: ProjectAST) -> list[str]:
    """获取函数调用的项目内函数 qualified_names。"""
    seen: set[str] = set()
    result: list[str] = []
    for edge in graph.edges:
        if edge.caller == qname and edge.callee_resolved:
            if edge.callee_resolved not in seen:
                seen.add(edge.callee_resolved)
                result.append(edge.callee_resolved)
    return result


async def worker_loop(
    name: str,
    mailbox: Mailbox,
    graph: ProjectAST,
    project_files: dict[str, str],
    kb: KnowledgeBase,
) -> None:
    """Worker 主循环：读任务 → 语义化 → 写 KB → 通知 Lead。"""
    while True:
        msg = await mailbox.read_inbox(name)

        if msg.msg_type == "shutdown":
            logger.debug("Worker %s: shutdown received", name)
            break

        if msg.msg_type != "task":
            continue

        qname = msg.payload["qualified_name"]
        logger.debug("Worker %s: processing %s", name, qname)

        try:
            defn = graph.definitions.get(qname)
            if not defn:
                # 定义不存在，写 fallback
                kb.put(FunctionSummary(
                    qualified_name=qname,
                    file="", line_start=0, line_end=0,
                    summary=f"函数 {qname.split('::')[-1] if '::' in qname else qname}",
                    calls=[], params=[], kind="function",
                ))
                continue

            line_count = defn.line_end - defn.line_start + 1
            callees = _get_callees(qname, graph)

            # 快捷路径：简单函数或有 docstring → 跳过 LLM
            if line_count <= TRIVIAL_LINE_THRESHOLD or defn.docstring:
                summary_text = defn.docstring or f"函数 {defn.name}"
                logger.debug("Worker %s: fast path for %s", name, qname)
            else:
                # 正常路径：提取源码 → LLM 摘要
                func_source = _extract_source(qname, graph, project_files)
                if not func_source:
                    summary_text = defn.docstring or f"函数 {defn.name}"
                else:
                    params_str = ", ".join(defn.params)
                    signature = f"def {defn.name}({params_str})"
                    system_prompt, user_prompt = build_worker_prompt(
                        func_name=defn.name,
                        file_path=defn.file,
                        signature=signature,
                        source_code=func_source,
                    )
                    summary_text = (await call_qwen(system_prompt, user_prompt)).strip()

            kb.put(FunctionSummary(
                qualified_name=qname,
                file=defn.file,
                line_start=defn.line_start,
                line_end=defn.line_end,
                summary=summary_text,
                calls=callees,
                params=defn.params,
                kind=defn.kind,
            ))

        except Exception as e:
            # 错误 fallback：保证 KB 有内容
            logger.warning("Worker %s: error processing %s: %s", name, qname, e)
            defn = graph.definitions.get(qname)
            fallback = defn.docstring if defn and defn.docstring else f"函数 {qname.split('::')[-1]}"
            kb.put(FunctionSummary(
                qualified_name=qname,
                file=defn.file if defn else "",
                line_start=defn.line_start if defn else 0,
                line_end=defn.line_end if defn else 0,
                summary=fallback,
                calls=[], params=[], kind="function",
            ))

        finally:
            # 无论成功失败，必须通知 Lead
            await mailbox.send(Message(
                sender=name,
                receiver="lead",
                msg_type="done",
                payload={"qualified_name": qname},
            ))
