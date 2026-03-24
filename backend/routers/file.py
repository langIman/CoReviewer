from fastapi import APIRouter, UploadFile, HTTPException
from backend.models.schemas import FileResponse
from backend.services.file_service import validate_file, store_file

router = APIRouter()


@router.post("/api/upload", response_model=FileResponse)
async def upload_file(file: UploadFile):
    content_bytes = await file.read()
    filename = file.filename or "untitled.py"

    error = validate_file(filename, content_bytes)
    if error:
        raise HTTPException(status_code=400, detail=error)

    content = content_bytes.decode("utf-8")
    store_file(filename, content)
    line_count = content.count("\n") + 1

    return FileResponse(filename=filename, content=content, line_count=line_count)
