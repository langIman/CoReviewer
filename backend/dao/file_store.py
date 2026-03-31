from pathlib import Path
from backend.config import MAX_FILE_SIZE, ALLOWED_EXTENSIONS

# In-memory file storage for MVP
_file_store: dict[str, str] = {}

# Project-level storage
_project_store: dict[str, str] = {}  # relative_path -> content
_project_name: str | None = None
_project_summary: str | None = None


def validate_file(filename: str, content: bytes) -> str | None:
    """Validate uploaded file. Returns error message or None."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return f"Unsupported file type: {ext}. Only {ALLOWED_EXTENSIONS} allowed."
    if len(content) > MAX_FILE_SIZE:
        return f"File too large. Max size: {MAX_FILE_SIZE // 1024}KB."
    return None


def store_file(filename: str, content: str) -> None:
    _file_store[filename] = content


def get_file(filename: str) -> str | None:
    return _file_store.get(filename)


def store_project(project_name: str, files: dict[str, str]) -> None:
    global _project_name, _project_store
    _project_store = files.copy()
    _project_name = project_name


def get_project_files() -> dict[str, str]:
    return _project_store


def get_project_file(path: str) -> str | None:
    return _project_store.get(path)


def get_project_name() -> str | None:
    return _project_name


def set_project_summary(summary: str) -> None:
    global _project_summary
    _project_summary = summary


def get_project_summary() -> str | None:
    return _project_summary


def clear_project() -> None:
    global _project_name, _project_store, _project_summary
    _project_store = {}
    _project_name = None
    _project_summary = None
