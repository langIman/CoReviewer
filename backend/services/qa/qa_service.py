"""QA 问答编排服务。

对应 QA_REFACTOR_PLAN.md §2.11 / §2.12：
- ``answer(req)``：公共 async generator，yield ``(event_name, payload)``
  流；controller 负责把元组序列化成 SSE 帧
- ``_fast_stream`` / ``_deep_stream``：两种模式的内部 async generator，
  各自用 ``__final__`` 哨兵把最终 content / tool_events 回传给 ``answer``

深度模式两道安全阀（§2.11）：
1. ``MAX_ITER_DEEP``：工具调用轮数上限
2. ``DEEP_TOKEN_BUDGET``：输入 token 预算；超阈值后关闭 tools 强制收敛
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

from backend.dao.qa_store import (
    append_message,
    create_conversation,
    touch_conversation,
)
from backend.models.qa_models import QAMessage, QARequest
from backend.services.agent.tools.get_call_edges import GetCallEdgesTool
from backend.services.agent.tools.get_file_content import GetFileContentTool
from backend.services.agent.tools.get_modules import GetModulesTool
from backend.services.agent.tools.get_summaries import GetSummariesTool
from backend.services.agent.tools.get_symbols import GetSymbolsTool
from backend.services.agent.tools.search_code import SearchCodeTool
from backend.services.agent.tools.search_symbols import SearchSymbolsTool
from backend.services.llm.llm_service import call_llm, stream_messages
from backend.services.qa.code_refs import parse_code_refs
from backend.services.qa.context_builder import MAX_ITER_DEEP, QAContextBuilder

logger = logging.getLogger(__name__)

# 深度模式：输入 token 预算。超了就把下一轮 tools 设 None 强制收敛
DEEP_TOKEN_BUDGET = 20_000
# 伪流式分片参数（§2.11）
PSEUDO_STREAM_CHUNK_SIZE = 20
PSEUDO_STREAM_DELAY = 0.02


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------- 公共入口 ----------------------------


async def answer(req: QARequest) -> AsyncGenerator[tuple[str, dict[str, Any]], None]:
    """编排入口：持久化 user 消息 → 委派模式流 → 持久化 assistant 消息。

    yield ``(event_name, payload)``；controller 把这些序列化成 SSE 帧。
    内部哨兵 ``__final__`` 不转发，仅用来收 content / tool_events。
    """
    # 1. 会话 id（新建或复用）
    conv_id = req.conversation_id or create_conversation(
        req.project_name, req.question[:30],
    )

    # 2. 持久化 user 消息
    user_msg_id = append_message(conv_id, QAMessage(
        conversation_id=conv_id,
        role="user",
        content=req.question,
        created_at=_now_iso(),
    ))

    # 3. 发 start
    yield ("start", {
        "conversation_id": conv_id,
        "user_message_id": user_msg_id,
        "mode": req.mode,
    })

    # 4. 委派流式事件；同时收集最终 content / tool_events
    collected: list[str] = []
    tool_events: list[dict] = []

    inner = _fast_stream(req) if req.mode == "fast" else _deep_stream(req)
    try:
        async for event in inner:
            name, payload = event
            if name == "__final__":
                collected.append(payload.get("content", ""))
                tool_events = payload.get("tool_events", [])
                continue
            yield event
    except Exception as e:
        logger.exception("QA inner stream failed")
        yield ("error", {"message": f"{type(e).__name__}: {e}"})
        return

    # 5. 解析 code_refs 块
    full_content = "".join(collected)
    clean_content, code_refs = parse_code_refs(full_content)

    # 6. 持久化 assistant 消息
    assistant_msg_id = append_message(conv_id, QAMessage(
        conversation_id=conv_id,
        role="assistant",
        content=clean_content,
        mode=req.mode,
        tool_events=tool_events,
        code_refs=code_refs,
        created_at=_now_iso(),
    ))
    touch_conversation(conv_id)

    # 7. 发 code_refs + done
    # done 带上净化后的 content，供前端把 bubble 里残留的 code_refs 块替换掉
    yield ("code_refs", {"refs": code_refs})
    yield ("done", {
        "assistant_message_id": assistant_msg_id,
        "content": clean_content,
    })


# ---------------------------- 快速模式 ----------------------------


async def _fast_stream(
    req: QARequest,
) -> AsyncGenerator[tuple[str, dict[str, Any]], None]:
    """快速模式：BM25 预检索 → 装配 Context → stream_messages → token*。"""
    ctx = QAContextBuilder(req.project_name, req.question, "fast").build()
    buf: list[str] = []
    async for chunk in stream_messages(ctx.to_messages()):
        buf.append(chunk)
        yield ("token", {"delta": chunk})
    yield ("__final__", {"content": "".join(buf), "tool_events": []})


# ---------------------------- 深度模式 ----------------------------


def _estimate_tokens(messages: list[dict]) -> int:
    """粗估输入 token 数：字符数 / 3（中英混合偏保守）。

    换精确 tokenizer 需要额外依赖；MVP 用字符数够了。
    """
    total = 0
    for m in messages:
        total += len(json.dumps(m, ensure_ascii=False, default=str))
    return total // 3


def _truncate(obj: Any, limit: int) -> str:
    """把对象序列化后截断，用于 SSE 推送到前端的 preview。"""
    s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, default=str)
    if len(s) <= limit:
        return s
    return s[:limit] + f"... ({len(s) - limit} more chars)"


async def _pseudo_stream(
    content: str,
    chunk_size: int = PSEUDO_STREAM_CHUNK_SIZE,
    delay: float = PSEUDO_STREAM_DELAY,
) -> AsyncGenerator[str, None]:
    """把非流式最终答复切片模拟打字效果。"""
    for i in range(0, len(content), chunk_size):
        yield content[i : i + chunk_size]
        await asyncio.sleep(delay)


def _build_deep_tools() -> list:
    """深度模式工具集（§2.11）。"""
    return [
        GetSummariesTool(),
        GetModulesTool(),
        GetSymbolsTool(),
        GetCallEdgesTool(),
        GetFileContentTool(),
        SearchSymbolsTool(),
        SearchCodeTool(),
    ]


async def _deep_stream(
    req: QARequest,
) -> AsyncGenerator[tuple[str, dict[str, Any]], None]:
    """深度模式工具循环（不改 agent.py，这里手写一份）。

    每轮：
    1. 估算输入 tokens，超预算 → 本轮起关闭工具
    2. call_llm(messages, tools=?)
    3. 若返回 tool_calls → 依次执行，追加 tool_result，下一轮
    4. 若返回纯文本 → 伪流式分片产出 → 退出
    5. 达迭代上限 → 给出兜底回答
    """
    ctx = QAContextBuilder(req.project_name, req.question, "deep").build()

    tools = _build_deep_tools()
    tool_map = {t.name: t for t in tools}
    tool_defs = [t.definition for t in tools]
    tool_events: list[dict] = []

    for iteration in range(1, MAX_ITER_DEEP + 1):
        messages = ctx.to_messages()

        # —— 安全阀 2：token 预算用尽，强制关闭工具 ——
        tokens_est = _estimate_tokens(messages)
        over_budget = tokens_est > DEEP_TOKEN_BUDGET
        current_tools = None if over_budget else tool_defs
        if over_budget:
            yield ("budget_exhausted", {
                "tokens_est": tokens_est,
                "budget": DEEP_TOKEN_BUDGET,
            })

        msg = await call_llm(messages, tools=current_tools)
        ctx.add_assistant(msg)

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            # LLM 给出最终答复 → 先去 code_refs 块，再伪流式出净化后的内容
            # 否则那块裸 JSON 会流给前端显示在 bubble 里
            raw_content = msg.get("content") or ""
            clean_content, _ = parse_code_refs(raw_content)
            async for chunk in _pseudo_stream(clean_content):
                yield ("token", {"delta": chunk})
            # __final__ 仍传原始 content，让 answer() 统一走 parse_code_refs + 落库
            yield ("__final__", {"content": raw_content, "tool_events": tool_events})
            return

        # 预算用尽时忽略本轮 tool_calls（罕见但防御）；下一轮 tools=None 强制收敛
        if over_budget:
            logger.warning(
                "Deep QA: ignoring %d tool_calls after budget exhaustion",
                len(tool_calls),
            )
            continue

        # —— 执行工具 ——
        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name", "")
            raw_args = func.get("arguments", "{}")
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except json.JSONDecodeError:
                args = {}

            yield ("tool_call", {
                "iteration": iteration,
                "name": name,
                "args_preview": args,
            })

            tool = tool_map.get(name)
            if tool is None:
                result: Any = {"error": f"未知工具: {name}"}
            else:
                try:
                    result = await tool.execute(**args)
                except Exception as e:
                    logger.exception("Deep QA tool failed: %s", name)
                    result = {"error": f"{type(e).__name__}: {e}"}

            result_str = json.dumps(result, ensure_ascii=False, default=str)
            tool_call_id = tc.get("id", "")
            ctx.add_tool_result(
                tool_call_id=tool_call_id, name=name, content=result_str,
            )

            ok = not (isinstance(result, dict) and "error" in result)
            preview = _truncate(result_str, 500)
            yield ("tool_result", {
                "iteration": iteration,
                "name": name,
                "ok": ok,
                "preview": preview,
            })
            tool_events.append({
                "iteration": iteration,
                "name": name,
                "args": args,
                "result_preview": preview,
            })

    # —— 安全阀 1：迭代上限 ——
    fallback = "[达到工具调用上限，回答可能不完整]"
    async for chunk in _pseudo_stream(fallback):
        yield ("token", {"delta": chunk})
    yield ("__final__", {"content": fallback, "tool_events": tool_events})
