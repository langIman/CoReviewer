"""Agent 间异步邮箱通信。

每个 Agent 有独立收件箱，exactly-once 消费。
Mailbox 只传信号（task/done/shutdown），不传数据。数据走 KnowledgeBase。
"""

import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Agent 间的消息。"""

    sender: str  # "lead" / "worker-0"
    receiver: str
    msg_type: str  # "task" / "done" / "shutdown"
    payload: dict = field(default_factory=dict)


class Mailbox:
    """异步邮箱，每个 agent 有独立收件箱。"""

    def __init__(self) -> None:
        self._boxes: dict[str, asyncio.Queue[Message]] = {}

    def register(self, agent_name: str) -> None:
        """注册一个 agent 的收件箱（幂等）。"""
        if agent_name in self._boxes:
            logger.debug("Mailbox: %s already registered", agent_name)
            return
        self._boxes[agent_name] = asyncio.Queue()

    async def send(self, msg: Message) -> None:
        """投递消息到接收者的收件箱。"""
        box = self._boxes.get(msg.receiver)
        if not box:
            logger.error("Mailbox: receiver %s not registered, dropping message", msg.receiver)
            return
        await box.put(msg)

    async def read_inbox(self, agent_name: str) -> Message:
        """阻塞等待，读即消费（exactly-once）。"""
        return await self._boxes[agent_name].get()

