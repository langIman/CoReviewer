import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.models.schemas import ReviewRequest
from backend.services.context import build_review_prompt
from backend.services.llm import stream_qwen

router = APIRouter()


@router.post("/api/review")
async def review_code(req: ReviewRequest):
    system_prompt, user_prompt = build_review_prompt(req)

    async def event_stream():
        async for chunk in stream_qwen(system_prompt, user_prompt):
            # SSE format: JSON-encode chunk for safe transport
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
