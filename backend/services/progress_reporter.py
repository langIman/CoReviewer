"""Wiki 生成进度上报。

设计要点：
- ContextVar 注入：``_run_generation`` 入口 set 一次，下游所有协程通过 context
  inheritance 自动拿到。**约束**：若管线引入 ``asyncio.to_thread`` /
  ``run_in_executor`` 必须 ``contextvars.copy_context().run(...)`` 否则丢失。
- 不可变事件日志：``track`` 进入和退出各 append 一条事件，复用 ``event_id``，
  前端按 id 折叠取最新。无原地 mutation，无需 asyncio.Lock。
- 上下文外调用（直接跑 service 函数、单测）拿到 no-op reporter，``track`` 是
  空 CM，不污染。
"""

from __future__ import annotations

import contextlib
import contextvars
import time
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator, Literal

from pydantic import BaseModel


Stage = Literal[
    "file_summary",
    "folder_summary",
    "project_summary",
    "module_split",
    "outline",
    "module_page",
    "chapter_page",
    "topic_page",
    "overview",
]


class WikiProgressEvent(BaseModel):
    event_id: str
    stage: Stage
    item: str | None
    status: Literal["running", "done", "failed"]
    started_at: str  # ISO 8601 UTC
    finished_at: str | None = None
    duration_ms: int | None = None
    error: str | None = None


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class WikiProgressReporter:
    """收集 Wiki 生成的事件流。线程不安全，仅供单一事件循环使用。

    时间戳设计：
    - ``started_at`` / ``finished_at``：墙钟 ISO 时间，仅用于排序与展示。
    - ``duration_ms``：用 ``time.perf_counter()``（单调时钟）测出的真实耗时，
      不受系统时钟跳变 / NTP / 跨机器时钟漂移影响。
    - 对 ``running`` 事件，``snapshot()`` 会现场用同一台机器的 perf_counter
      算出"目前已经跑了多久"填进 ``duration_ms``，前端直接展示即可，**不要**
      用浏览器 ``Date.now() - parse(started_at)``——浏览器和服务器时钟可能
      差几十秒。
    """

    def __init__(self) -> None:
        self._events: list[WikiProgressEvent] = []
        # event_id -> started_perf；running 事件结束时移除
        self._running_starts: dict[str, float] = {}

    @contextlib.asynccontextmanager
    async def track(self, stage: Stage, item: str | None) -> AsyncIterator[None]:
        event_id = uuid.uuid4().hex
        started_at = _utcnow_iso()
        started_perf = time.perf_counter()
        self._running_starts[event_id] = started_perf
        self._events.append(WikiProgressEvent(
            event_id=event_id,
            stage=stage,
            item=item,
            status="running",
            started_at=started_at,
        ))
        try:
            yield
        except BaseException as exc:
            self._running_starts.pop(event_id, None)
            self._events.append(WikiProgressEvent(
                event_id=event_id,
                stage=stage,
                item=item,
                status="failed",
                started_at=started_at,
                finished_at=_utcnow_iso(),
                duration_ms=int((time.perf_counter() - started_perf) * 1000),
                error=f"{type(exc).__name__}: {exc}"[:500],
            ))
            raise
        else:
            self._running_starts.pop(event_id, None)
            self._events.append(WikiProgressEvent(
                event_id=event_id,
                stage=stage,
                item=item,
                status="done",
                started_at=started_at,
                finished_at=_utcnow_iso(),
                duration_ms=int((time.perf_counter() - started_perf) * 1000),
            ))

    def snapshot(self) -> list[WikiProgressEvent]:
        """返回事件流快照；为 running 事件现场算 duration_ms。"""
        now_perf = time.perf_counter()
        result: list[WikiProgressEvent] = []
        for ev in self._events:
            if ev.status == "running":
                started_perf = self._running_starts.get(ev.event_id)
                if started_perf is not None:
                    ev = ev.model_copy(update={
                        "duration_ms": int((now_perf - started_perf) * 1000),
                    })
            result.append(ev)
        return result


class _NoopReporter(WikiProgressReporter):
    """上下文外的 fallback：track 是空 CM，snapshot 永远空。"""

    @contextlib.asynccontextmanager
    async def track(self, stage: Stage, item: str | None) -> AsyncIterator[None]:  # noqa: ARG002
        yield

    def snapshot(self) -> list[WikiProgressEvent]:
        return []


_NOOP = _NoopReporter()
_reporter_var: contextvars.ContextVar[WikiProgressReporter | None] = contextvars.ContextVar(
    "wiki_progress_reporter", default=None,
)


def set_reporter(reporter: WikiProgressReporter) -> contextvars.Token:
    return _reporter_var.set(reporter)


def get_reporter() -> WikiProgressReporter:
    return _reporter_var.get() or _NOOP
