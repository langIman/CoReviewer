"""QA 问答 HTTP 控制器。

对应 QA_REFACTOR_PLAN.md §2.13。暴露 4 个端点：
- POST   /api/qa/ask                       SSE 流式问答（fast / deep）
- GET    /api/qa/conversations             列出项目下的会话
- GET    /api/qa/conversations/{id}        会话详情（含消息）
- DELETE /api/qa/conversations/{id}        删除会话

实施顺序：Step 11 之前端点 2/3/4 已经可工作；Step 9 之前 mode=deep 会报错。
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.dao.qa_store import (
    delete_conversation,
    get_conversation,
    list_conversations,
)
from backend.models.qa_models import (
    Conversation,
    ConversationDetail,
    QARequest,
)
from backend.services.qa.qa_service import answer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/qa", tags=["qa"])


@router.post("/ask")
async def post_ask(req: QARequest):
    """流式问答入口。返回 SSE（``text/event-stream``）。

    事件协议见 QA_REFACTOR_PLAN.md §2.14。
    """

    async def sse_stream():
        try:
            async for event_name, payload in answer(req):
                data = json.dumps(payload, ensure_ascii=False)
                yield f"event: {event_name}\ndata: {data}\n\n"
        except Exception as e:
            logger.exception("QA ask failed")
            err = json.dumps({"message": f"{type(e).__name__}: {e}"}, ensure_ascii=False)
            yield f"event: error\ndata: {err}\n\n"

    # X-Accel-Buffering: 禁用反代缓冲，确保 SSE 实时推送
    return StreamingResponse(
        sse_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations", response_model=list[Conversation])
async def list_convs(project_name: str) -> list[Conversation]:
    return list_conversations(project_name)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conv(conversation_id: str) -> ConversationDetail:
    detail = get_conversation(conversation_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Conversation not found: {conversation_id}")
    return detail


@router.delete("/conversations/{conversation_id}")
async def delete_conv(conversation_id: str) -> dict:
    ok = delete_conversation(conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Conversation not found: {conversation_id}")
    return {"deleted": conversation_id}
