"""Agent 对话上下文管理。

维护 OpenAI 格式的消息历史，提供组装和快照能力。
"""

from __future__ import annotations

import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)


class Context:
    """Agent 对话上下文。

    职责：
    1. 管理系统提示词（不可变）
    2. 追加 user/assistant/tool 消息
    3. 导出完整消息列表供 LLM 调用
    """

    def __init__(self, system_prompt: str) -> None:
        self._system_message: dict[str, Any] = {"role": "system", "content": system_prompt}
        self._messages: list[dict[str, Any]] = []

    def add_user(self, content: str) -> None:
        self._messages.append({"role": "user", "content": content})

    def add_assistant(self, message: dict[str, Any]) -> None:
        """追加助手消息（完整 message dict，可能含 tool_calls）。"""
        self._messages.append(message)

    def add_tool_result(self, tool_call_id: str, name: str, content: str) -> None:
        self._messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": content,
        })

    def to_messages(self) -> list[dict[str, Any]]:
        """导出完整消息列表（含 system）供 LLM 调用。返回深拷贝。"""
        return [copy.deepcopy(self._system_message)] + copy.deepcopy(self._messages)

    @property
    def turn_count(self) -> int:
        return sum(1 for m in self._messages if m["role"] == "user")
