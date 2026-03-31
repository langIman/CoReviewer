"""Controller for file upload and project management endpoints."""

from typing import Annotated

from fastapi import APIRouter, UploadFile, File

from backend.models.schemas import FileResponse, ProjectUploadResponse, ProjectSummaryResponse
from backend.services.file_service import upload_single_file, upload_project_files, generate_project_summary

router = APIRouter()


@router.post("/api/file/upload", response_model=FileResponse)
async def upload_file(file: UploadFile):
    return await upload_single_file(file)


@router.post("/api/file/upload-project", response_model=ProjectUploadResponse)
async def upload_project(files: Annotated[list[UploadFile], File()]):
    return await upload_project_files(files)


@router.post("/api/file/project/summary", response_model=ProjectSummaryResponse)
async def get_project_summary():
    return await generate_project_summary()
