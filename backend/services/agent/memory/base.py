"""Agent 记忆系统。

Memory Protocol 定义接口，ShortTermMemory 提供内存 dict 实现。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Memory(Protocol):
    """记忆存储协议。"""

    def store(self, key: str, value: Any) -> None: ...
    def retrieve(self, key: str) -> Any | None: ...
    def clear(self) -> None: ...


class ShortTermMemory:
    """内存 dict 实现的短期记忆。生命周期与 Agent 实例相同。"""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def store(self, key: str, value: Any) -> None:
        self._store[key] = value

    def retrieve(self, key: str) -> Any | None:
        return self._store.get(key)

    def clear(self) -> None:
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)

    def all(self) -> dict[str, Any]:
        return dict(self._store)
