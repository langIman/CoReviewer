"""
概览流程图生成服务。
使用 Lead-Worker 多 Agent 协作生成语义流程图。
"""

from backend.utils.analysis.ast_service import get_or_build_ast
from backend.services.agents.lead import generate_overview_with_agents


async def generate_overview() -> dict:
    """Generate a semantic overview flowchart.

    Delegates to the multi-agent system:
    1. Lead finds key business function via AST density scoring
    2. Workers concurrently summarize called functions via LLM
    3. Lead generates flowchart using key function source + summaries

    Returns FlowData {nodes, edges} for the frontend.
    """
    graph, project_files = get_or_build_ast()
    return await generate_overview_with_agents(graph, project_files)
