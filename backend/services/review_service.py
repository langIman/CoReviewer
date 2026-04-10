"""代码审查业务逻辑。"""

from typing import AsyncGenerator

from backend.models.schemas import ReviewRequest, ProjectFileInfo
from backend.services.llm.prompts.review import build_review_prompt
from backend.services.agent import Agent
from backend.utils.analysis.import_analysis import get_related_files
from backend.dao.file_store import get_project_files


async def stream_review(req: ReviewRequest) -> AsyncGenerator[str, None]:
    """执行代码审查，流式返回文本片段。"""
    if req.project_mode and not req.related_files:
        project_files = get_project_files()
        if project_files:
            related = get_related_files(req.file_name, project_files)
            req.related_files = [
                ProjectFileInfo(path=p, content=c, line_count=c.count("\n") + 1)
                for p, c in related
            ]

    system_prompt, user_prompt = build_review_prompt(req)

    agent = Agent(system_prompt=system_prompt, tools=[])
    async for chunk in agent.stream_run(user_prompt):
        yield chunk
