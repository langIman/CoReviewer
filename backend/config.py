import os

QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen3.6-plus")

MAX_FILE_SIZE = 1024 * 1024  # 1MB
ALLOWED_EXTENSIONS = {
    # 代码文件
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
    ".c", ".cpp", ".h", ".rb", ".php", ".swift", ".kt",
    # 配置文件
    ".json", ".yaml", ".yml", ".toml", ".xml",
    # 文档 / 其他
    ".md", ".txt", ".html", ".css", ".sql", ".sh", ".dockerfile",
}
# AST 静态分析仅支持 Python
AST_EXTENSIONS = {".py"}


def is_ast_file(path: str) -> bool:
    """Check if a file path has an AST-analyzable extension."""
    return any(path.endswith(ext) for ext in AST_EXTENSIONS)
MAX_PROJECT_SIZE = 10 * 1024 * 1024  # 10MB total
MAX_PROJECT_FILES = 200

# 摘要生成配置
SUMMARY_FUNC_LINES = 5          # 每个函数/类提取的行数
SUMMARY_TRUNCATION_PERCENT = 0.3  # 文件截断上限（30%）
