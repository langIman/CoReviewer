"""通用 Agent -- 基于主循环的 LLM Agent 框架。

核心循环: 用户输入 → 上下文组装 → 模型决策 → 工具执行 → 结果注入 → 继续/停止
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from backend.services.agent.context.base import Context
from backend.services.agent.tools.base import BaseTool, Tool
from backend.services.agent.tools.spawn import SpawnAgentTool
from backend.services.llm.llm_service import call_llm, stream_qwen

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 10


class Agent:
    """通用 Agent，支持 tool-use 主循环。

    当前阶段以纯对话模式运行（无具体业务工具注册时，
    LLM 不会调用工具，主循环第一轮即停止）。
    后续只需注册新工具即可激活 tool-use 流程。
    """

    def __init__(
        self,
        system_prompt: str,
        tools: list[BaseTool | Tool] | None = None,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
    ) -> None:
        self._system_prompt = system_prompt
        self._max_iterations = max_iterations
        self._context = Context(system_prompt)

        # 构建工具列表
        # tools=None → 默认含 SpawnAgentTool
        # tools=[]   → 无工具（纯对话模式）
        # tools=[..]  → 用户工具 + 自动注入 SpawnAgentTool
        if tools is None:
            self._tools: list[BaseTool | Tool] = [SpawnAgentTool()]
        else:
            self._tools = list(tools)
            if self._tools and not any(isinstance(t, SpawnAgentTool) for t in self._tools):
                self._tools.append(SpawnAgentTool(parent_tools=self._tools))

        self._tool_map: dict[str, BaseTool | Tool] = {t.name: t for t in self._tools}

        logger.info(
            "Agent initialized: %d tools (%s), max_iterations=%d",
            len(self._tools),
            ", ".join(self._tool_map.keys()),
            self._max_iterations,
        )

    async def run(self, user_input: str) -> str:
        """执行 Agent 主循环。

        流程:
            1. 上下文组装（system prompt + 消息历史 + 工具定义）
            2. 模型决策（调用 LLM）
            3. 工具执行 + 结果注入
            4. 继续（有 tool_calls）/ 停止（纯文本）
        """
        self._context.add_user(user_input)

        assistant_message: dict[str, Any] = {}

        for iteration in range(self._max_iterations):
            logger.debug("Agent loop iteration %d/%d", iteration + 1, self._max_iterations)

            # 1. 上下文组装
            messages = self._context.to_messages()
            tool_defs = self._get_tool_definitions()

            # 2. 模型决策
            assistant_message = await call_llm(messages, tools=tool_defs)
            self._context.add_assistant(assistant_message)

            # 3. 工具执行 + 结果注入
            tool_calls = assistant_message.get("tool_calls")
            if not tool_calls:
                # 5. 停止
                content = assistant_message.get("content", "")
                logger.info("Agent completed in %d iteration(s)", iteration + 1)
                return content or ""

            for tool_call in tool_calls:
                result = await self._execute_tool(tool_call)
                self._context.add_tool_result(
                    tool_call_id=tool_call["id"],
                    name=tool_call["function"]["name"],
                    content=result,
                )
            # 5. 继续

        # 安全阀
        logger.warning("Agent hit max iterations (%d)", self._max_iterations)
        return assistant_message.get("content", "") or "[Agent 达到最大迭代次数]"

    async def stream_run(self, user_input: str) -> AsyncGenerator[str, None]:
        """流式对话（不走主循环，无 tool-use）。"""
        async for chunk in stream_qwen(self._system_prompt, user_input):
            yield chunk

    def _get_tool_definitions(self) -> list[dict] | None:
        if not self._tools:
            return None
        return [t.definition for t in self._tools]

    async def _execute_tool(self, tool_call: dict) -> str:
        """执行单个工具调用，返回结果字符串。"""
        func_info = tool_call["function"]
        tool_name = func_info["name"]
        raw_args = func_info.get("arguments", "{}")

        logger.info("Executing tool: %s", tool_name)

        tool = self._tool_map.get(tool_name)
        if not tool:
            error_msg = f"未知工具: {tool_name}"
            logger.error(error_msg)
            return json.dumps({"error": error_msg}, ensure_ascii=False)

        try:
            kwargs = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except json.JSONDecodeError as e:
            error_msg = f"工具参数解析失败: {e}"
            logger.error("%s, raw_args=%s", error_msg, raw_args[:200])
            return json.dumps({"error": error_msg}, ensure_ascii=False)

        try:
            result = await tool.execute(**kwargs)
            if isinstance(result, str):
                return result
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            error_msg = f"工具 {tool_name} 执行失败: {type(e).__name__}: {e}"
            logger.exception(error_msg)
            return json.dumps({"error": error_msg}, ensure_ascii=False)
