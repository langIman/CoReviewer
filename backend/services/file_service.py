"""文件上传与项目管理业务逻辑。"""

from pathlib import PurePosixPath

from fastapi import HTTPException, UploadFile

from backend.config import ALLOWED_EXTENSIONS, MAX_PROJECT_FILES
from backend.models.schemas import FileResponse, ProjectFileInfo, ProjectUploadResponse, ProjectSummaryResponse
from backend.dao.file_store import (
    validate_file, store_file, store_project,
    get_project_files, get_project_name, set_project_summary,
)
from backend.dao.graph_cache import invalidate_cache
from backend.services.llm.llm_service import call_qwen
from backend.services.llm.prompts.summary import build_summary_prompt


async def upload_single_file(file: UploadFile) -> FileResponse:
    """验证并存储单个文件，返回文件信息。"""
    content_bytes = await file.read()
    filename = file.filename or "untitled.py"

    error = validate_file(filename, content_bytes)
    if error:
        raise HTTPException(status_code=400, detail=error)

    content = content_bytes.decode("utf-8")
    store_file(filename, content)
    return FileResponse(filename=filename, content=content, line_count=content.count("\n") + 1)


async def upload_project_files(files: list[UploadFile]) -> ProjectUploadResponse:
    """批量验证、过滤、存储项目文件，失效 AST 缓存。"""
    project_files: dict[str, str] = {}
    file_infos: list[ProjectFileInfo] = []

    for f in files:
        path = f.filename or ""
        if PurePosixPath(path).suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        content_bytes = await f.read()
        if validate_file(path, content_bytes):
            continue
        if len(file_infos) >= MAX_PROJECT_FILES:
            break

        content = content_bytes.decode("utf-8")
        project_files[path] = content
        file_infos.append(ProjectFileInfo(
            path=path,
            content=content,
            line_count=content.count("\n") + 1,
        ))

    if not file_infos:
        raise HTTPException(status_code=400, detail="No valid .py files found in upload")

    all_paths = [fi.path for fi in file_infos]
    first_parts = [p.split("/")[0] for p in all_paths if "/" in p]
    project_name = first_parts[0] if first_parts else "project"

    store_project(project_name, project_files)
    invalidate_cache()

    return ProjectUploadResponse(project_name=project_name, files=file_infos)


async def generate_project_summary() -> ProjectSummaryResponse:
    """调用 LLM 生成项目摘要并存储。"""
    project_files = get_project_files()
    project_name = get_project_name()
    if not project_files or not project_name:
        raise HTTPException(status_code=400, detail="No project loaded")

    system_prompt, user_prompt = build_summary_prompt(project_name, project_files)
    summary = await call_qwen(system_prompt, user_prompt)
    set_project_summary(summary)

    return ProjectSummaryResponse(summary=summary)
