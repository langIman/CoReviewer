from pathlib import Path
from backend.config import MAX_FILE_SIZE, ALLOWED_EXTENSIONS

# In-memory file storage for MVP
_file_store: dict[str, str] = {}


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
