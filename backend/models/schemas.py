from pydantic import BaseModel


class FileResponse(BaseModel):
    filename: str
    content: str
    line_count: int


class ReviewRequest(BaseModel):
    file_name: str
    full_content: str
    selected_code: str
    start_line: int
    end_line: int
    action: str = "explain"
