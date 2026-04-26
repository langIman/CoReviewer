"""Wiki HTTP 控制器。

暴露 3 个端点：
- POST /api/wiki/generate           启动异步生成，返回 task_id
- GET  /api/wiki/status/{task_id}   查生成进度
- GET  /api/wiki/{project_name}     取整份 WikiDocument（所有页面均已生成）

任务状态用进程内字典保存，MVP 够用；以后要扩成 Celery/队列再换。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from backend.dao.file_store import get_project_name
from backend.dao.wiki_store import load_wiki_document
from backend.models.wiki_models import WikiDocument
from backend.services.wiki.exporter import export_to_markdown
from backend.services.wiki_service import generate_wiki

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiki", tags=["wiki"])


# ---------------------------- 任务追踪 ----------------------------

# task_id -> {status, project_name, message, created_at}
# status: "pending" | "running" | "done" | "failed"
_tasks: dict[str, dict] = {}


class WikiGenerateRequest(BaseModel):
    project_name: str | None = None


class WikiGenerateResponse(BaseModel):
    task_id: str
    project_name: str


class WikiTaskStatus(BaseModel):
    task_id: str
    status: str
    project_name: str
    message: str | None = None
    created_at: str


async def _run_generation(task_id: str, project_name: str) -> None:
    """背景协程：跑完整 eager 流水线，更新任务状态。"""
    _tasks[task_id]["status"] = "running"
    try:
        await generate_wiki(project_name)
        _tasks[task_id]["status"] = "done"
        logger.info("Wiki task done: %s (%s)", task_id, project_name)
    except Exception as e:
        _tasks[task_id]["status"] = "failed"
        _tasks[task_id]["message"] = f"{type(e).__name__}: {e}"
        logger.exception("Wiki task failed: %s", task_id)


# ---------------------------- 端点 ----------------------------


@router.post("/generate", response_model=WikiGenerateResponse)
async def post_generate(
    body: WikiGenerateRequest,
    background_tasks: BackgroundTasks,
) -> WikiGenerateResponse:
    project_name = body.project_name or get_project_name()
    if not project_name:
        raise HTTPException(status_code=400, detail="No project loaded")

    task_id = uuid.uuid4().hex
    _tasks[task_id] = {
        "status": "pending",
        "project_name": project_name,
        "message": None,
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    background_tasks.add_task(_run_generation, task_id, project_name)
    logger.info("Wiki task scheduled: %s (%s)", task_id, project_name)
    return WikiGenerateResponse(task_id=task_id, project_name=project_name)


@router.get("/status/{task_id}", response_model=WikiTaskStatus)
async def get_status(task_id: str) -> WikiTaskStatus:
    task = _tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    return WikiTaskStatus(
        task_id=task_id,
        status=task["status"],
        project_name=task["project_name"],
        message=task.get("message"),
        created_at=task["created_at"],
    )


@router.get("/{project_name}", response_model=WikiDocument)
async def get_wiki(project_name: str) -> WikiDocument:
    """返回整份 WikiDocument（含 index + 全部 pages，所有内容都已生成）。"""
    doc = load_wiki_document(project_name)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Wiki not found: {project_name}")
    return doc


@router.get("/{project_name}/export")
async def export_wiki(project_name: str) -> Response:
    """把整份 Wiki 导出为单个 .md 文件，浏览器触发下载。"""
    doc = load_wiki_document(project_name)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Wiki not found: {project_name}")
    md = export_to_markdown(doc)
    # 文件名里只允许基础字符，避免浏览器处理异常
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in project_name)
    filename = f"{safe_name}.md"
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
