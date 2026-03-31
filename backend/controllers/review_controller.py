"""Controller for code review streaming endpoint."""

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.models.schemas import ReviewRequest
from backend.services.review_service import stream_review

router = APIRouter()


@router.post("/api/review")
async def review_code(req: ReviewRequest):
    async def event_stream():
        async for chunk in stream_review(req):
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
