"""
函数细节扩展服务。
将单个函数的内部逻辑扩展为流程图。
仅将一个函数的源代码发送给大型语言模型（而非整个项目）。
"""

import json

from fastapi import HTTPException

from backend.utils.analysis.ast_service import get_or_build_ast
from backend.models.graph_models import ProjectAST, SymbolDef
from backend.services.agent import Agent
from backend.utils.data_format import parse_llm_json, normalize_flow_data
from backend.services.llm.prompts.annotate import build_function_detail_prompt


def find_definition(qualified_name: str, graph: ProjectAST) -> SymbolDef | None:
    """Find a SymbolDef by qualified_name with fuzzy fallback.

    Handles cases where the frontend sends "main.py::register" but the
    actual definition is "services/auth_service.py::AuthService.register".
    """
    defn = graph.definitions.get(qualified_name)
    if defn:
        return defn

    raw_symbol = qualified_name.split("::")[-1] if "::" in qualified_name else qualified_name

    candidates = [raw_symbol]
    if "." in raw_symbol:
        candidates.append(raw_symbol.split(".")[-1])

    for candidate in candidates:
        for d in graph.definitions.values():
            if d.name == candidate:
                return d
            if "." in d.name and d.name.endswith(f".{candidate}"):
                return d

    return None


async def generate_detail(qualified_name: str) -> dict:
    """Expand a function's internal logic into a flowchart.

    Returns FlowData {nodes, edges} for the frontend.
    """
    graph, project_files = get_or_build_ast()

    defn = find_definition(qualified_name, graph)
    if not defn:
        raise HTTPException(status_code=404, detail=f"Function not found: {qualified_name}")

    source = project_files.get(defn.file)
    if not source:
        raise HTTPException(status_code=404, detail=f"Source file not found: {defn.file}")

    # Extract this function's source code
    lines = source.split("\n")
    func_source = "\n".join(lines[defn.line_start - 1 : defn.line_end])

    # Build signature
    from backend.config import get_file_language
    from backend.utils.analysis.ts_parser import format_signature
    signature = format_signature(defn, get_file_language(defn.file))

    # Collect called functions info
    called_functions: list[dict] = []
    for edge in graph.edges:
        if edge.caller == qualified_name and edge.callee_resolved:
            called_def = graph.definitions.get(edge.callee_resolved)
            if called_def:
                called_functions.append({
                    "name": called_def.name,
                    "params": called_def.params,
                    "docstring": called_def.docstring,
                })

    system_prompt, user_prompt = build_function_detail_prompt(
        func_name=defn.name,
        file_path=defn.file,
        signature=signature,
        docstring=defn.docstring or "",
        source_code=func_source,
        called_functions=called_functions if called_functions else None,
    )

    agent = Agent(system_prompt=system_prompt, tools=[])
    raw = await agent.run(user_prompt)
    data = parse_llm_json(raw)
    normalize_flow_data(data)

    # Ensure file info on all nodes
    for node in data["nodes"]:
        if "file" not in node:
            node["file"] = defn.file

    return data
