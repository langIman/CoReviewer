"""Agent Tool：读取项目源文件内容。"""

from typing import Any

from backend.dao.file_store import get_project_files
from backend.services.agent.tools.base import BaseTool


class GetFileContentTool(BaseTool):
    """从内存文件存储中读取指定文件的源码。"""

    @property
    def name(self) -> str:
        return "get_file_content"

    @property
    def description(self) -> str:
        return (
            "读取项目中指定文件的源代码。"
            "需要深入理解某个文件的具体实现时使用。"
            "传入文件的相对路径，返回完整源码。"
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件相对路径，如 'backend/services/review_service.py'",
                },
            },
            "required": ["path"],
        }

    async def execute(self, *, path: str, **kwargs: Any) -> Any:
        project_files = get_project_files()
        if not project_files:
            return {"error": "没有已加载的项目"}

        content = project_files.get(path)
        if content is None:
            available = sorted(project_files.keys())
            return {"error": f"文件不存在: {path}", "available_files": available}

        return {"path": path, "content": content}
