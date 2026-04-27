"""Controller for file upload and project management endpoints."""

from typing import Annotated

from fastapi import APIRouter, UploadFile, File

from backend.models.schemas import FileResponse, ProjectUploadResponse, ProjectSummaryResponse
from backend.services.file_service import (
    generate_project_summary,
    get_persisted_project,
    upload_project_files,
    upload_single_file,
)

router = APIRouter()


@router.post("/api/file/upload", response_model=FileResponse)
async def upload_file(file: UploadFile):
    return await upload_single_file(file)


@router.post("/api/file/upload-project", response_model=ProjectUploadResponse)
async def upload_project(files: Annotated[list[UploadFile], File()]):
    return await upload_project_files(files)


@router.get("/api/file/project/{project_name}", response_model=ProjectUploadResponse)
async def fetch_persisted_project(project_name: str):
    """读回此前持久化的项目源文件（页面刷新 / 后端重启后 drawer 复活）。"""
    return get_persisted_project(project_name)


@router.post("/api/file/project/summary", response_model=ProjectSummaryResponse)
async def get_project_summary():
    return await generate_project_summary()
