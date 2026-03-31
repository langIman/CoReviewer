"""
概览流程图生成服务。
从项目的入口函数源代码生成语义流程图。
"""

from backend.dao.graph_cache import get_or_build_graph
from backend.services.llm.llm_service import call_qwen
from backend.services.flow_service import (
    parse_llm_json,
    normalize_flow_data,
    fill_line_numbers_from_ast,
)
from backend.services.llm.prompts.annotate import build_overview_prompt


async def generate_overview() -> dict:
    """Generate a semantic overview flowchart.

    Returns FlowData {nodes, edges} for the frontend.
    """
    graph, project_files = get_or_build_graph()
    graph_dict = graph.to_dict()

    system_prompt, user_prompt = build_overview_prompt(graph_dict, project_files)
    raw = await call_qwen(system_prompt, user_prompt)
    data = parse_llm_json(raw)
    normalize_flow_data(data)
    fill_line_numbers_from_ast(data, graph)

    return data
