"""Skill 驱动的模块划分服务。"""

import logging

from backend.dao.file_store import get_project_name
from backend.dao.summary_store import get_summaries_by_type
from backend.services.agent import Agent
from backend.services.agent.skills.module_split import ModuleSplitSkill
from backend.utils.data_format import parse_llm_json

logger = logging.getLogger(__name__)


async def generate_module_split() -> dict:
    """基于 Skill 驱动的 Agent 自主模块划分。"""
    project_name = get_project_name()
    if not project_name:
        raise ValueError("No project loaded")

    # 前置校验：无摘要时快速失败（不浪费 Agent 轮次）
    if not get_summaries_by_type(project_name, "folder") and not get_summaries_by_type(project_name, "file"):
        raise ValueError("No summaries found. Please generate summaries first.")

    # 用 Skill 驱动 Agent（Agent 自主收集数据、自主验证覆盖率）
    skill = ModuleSplitSkill()
    agent = Agent(system_prompt=skill.system_prompt, tools=skill.tools)
    user_input = skill.build_user_input({"project_name": project_name})
    raw = await agent.run(user_input)
    return parse_llm_json(raw)
