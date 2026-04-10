"""Agent 技能协议（占位）。

Skill 封装一类任务的配置：system_prompt + tools 组合。
当前阶段仅定义协议，不实现具体 Skill。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from backend.services.agent.tools.base import Tool


@runtime_checkable
class Skill(Protocol):
    """Agent 技能协议。"""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def system_prompt(self) -> str: ...

    @property
    def tools(self) -> list[Tool]: ...

    def build_user_input(self, context: dict[str, Any]) -> str:
        """将业务上下文转为 Agent 的 user_input。"""
        ...
