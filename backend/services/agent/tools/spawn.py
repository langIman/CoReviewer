"""SpawnAgentTool -- 创建子 Agent 并运行其主循环。

Agent 默认携带此工具，使 Agent 具备自主拆分子任务的能力。
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from backend.services.agent.tools.base import BaseTool

if TYPE_CHECKING:
    from backend.services.agent.agent import Agent

logger = logging.getLogger(__name__)


class SpawnAgentTool(BaseTool):
    """创建并运行子 Agent。

    子 Agent 继承父 Agent 的工具集（排除 SpawnAgentTool 防递归），
    以独立的上下文运行主循环，返回最终回复。
    """

    def __init__(
        self,
        parent_tools: list | None = None,
        parent_enable_thinking: bool | None = None,
    ) -> None:
        self._parent_tools = parent_tools or []
        self._parent_enable_thinking = parent_enable_thinking

    @property
    def name(self) -> str:
        return "spawn_agent"

    @property
    def description(self) -> str:
        return (
            "创建一个子 Agent 来处理子任务。"
            "子 Agent 拥有独立的对话上下文和主循环，"
            "会运行直到完成任务后返回结果。"
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "system_prompt": {
                    "type": "string",
                    "description": "子 Agent 的系统提示词",
                },
                "user_input": {
                    "type": "string",
                    "description": "交给子 Agent 处理的任务描述",
                },
            },
            "required": ["system_prompt", "user_input"],
        }

    async def execute(self, *, system_prompt: str, user_input: str, **kwargs: Any) -> str:
        from backend.services.agent.agent import Agent

        child_tools = [t for t in self._parent_tools if not isinstance(t, SpawnAgentTool)]

        child = Agent(
            system_prompt=system_prompt,
            tools=child_tools,
            max_iterations=5,
            enable_thinking=self._parent_enable_thinking,
        )

        logger.info("Spawning child agent with %d tools", len(child_tools))
        result = await child.run(user_input)
        logger.info("Child agent completed, result length=%d", len(result))
        return result
