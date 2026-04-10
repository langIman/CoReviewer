"""Agent 工具协议。

Tool Protocol 定义接口契约，BaseTool 提供 definition 的默认实现。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Tool(Protocol):
    """Agent 可调用的工具协议。"""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def parameters(self) -> dict: ...

    @property
    def definition(self) -> dict: ...

    async def execute(self, **kwargs: Any) -> Any: ...


class BaseTool:
    """工具基类。子类只需定义 name/description/parameters 和 execute。"""

    @property
    def name(self) -> str:
        raise NotImplementedError

    @property
    def description(self) -> str:
        raise NotImplementedError

    @property
    def parameters(self) -> dict:
        raise NotImplementedError

    @property
    def definition(self) -> dict:
        """自动组装 OpenAI function calling 格式。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    async def execute(self, **kwargs: Any) -> Any:
        raise NotImplementedError
