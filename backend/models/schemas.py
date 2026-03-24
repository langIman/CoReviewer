from pydantic import BaseModel


class FileResponse(BaseModel):
    filename: str
    content: str
    line_count: int


class ProjectFileInfo(BaseModel):
    path: str
    content: str
    line_count: int


class ProjectUploadResponse(BaseModel):
    project_name: str
    files: list[ProjectFileInfo]


class ProjectSummaryResponse(BaseModel):
    summary: str


class ReviewRequest(BaseModel):
    file_name: str
    full_content: str
    selected_code: str
    start_line: int
    end_line: int
    action: str = "explain"
    project_mode: bool = False
    related_files: list[ProjectFileInfo] | None = None
