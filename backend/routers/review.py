import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.models.schemas import ReviewRequest, ProjectFileInfo
from backend.services.prompts.review import build_review_prompt
from backend.services.llm import stream_qwen
from backend.services.import_analysis import get_related_files
from backend.services.file_service import get_project_files

router = APIRouter()


@router.post("/api/review")
async def review_code(req: ReviewRequest):
    # 项目模式下自动解析 import 并注入相关文件
    if req.project_mode and not req.related_files:
        project_files = get_project_files()
        if project_files:
            related = get_related_files(req.file_name, project_files)
            req.related_files = [
                ProjectFileInfo(path=p, content=c, line_count=c.count("\n") + 1)
                for p, c in related
            ]

    system_prompt, user_prompt = build_review_prompt(req)

    async def event_stream():
        async for chunk in stream_qwen(system_prompt, user_prompt):
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
