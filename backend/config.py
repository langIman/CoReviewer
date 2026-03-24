import os

QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-plus")

MAX_FILE_SIZE = 1024 * 1024  # 1MB
ALLOWED_EXTENSIONS = {".py"}
MAX_PROJECT_SIZE = 10 * 1024 * 1024  # 10MB total
MAX_PROJECT_FILES = 200
