"""
语义标注服务。
通过LLM为调用图节点生成中文标签。
如果LLM失败，则优雅地回退到函数名称。
"""

import json

from backend.dao.graph_cache import get_or_build_graph
from backend.services.llm.llm_service import call_qwen
from backend.services.llm.prompts.annotate import build_annotate_prompt


async def annotate(modules: list[str] | None = None) -> dict:
    """Annotate call graph nodes with Chinese labels.

    Returns {status, annotations} dict.
    """
    graph, project_files = get_or_build_graph()
    graph_dict = graph.to_dict()

    # Optionally filter to specific modules
    if modules:
        filtered_defs = {
            k: v for k, v in graph_dict["definitions"].items()
            if any(v["file"].startswith(m) for m in modules)
        }
        filtered_edges = [
            e for e in graph_dict["edges"]
            if e["caller"] in filtered_defs
        ]
        graph_dict = {
            "definitions": filtered_defs,
            "edges": filtered_edges,
        }

    system_prompt, user_prompt = build_annotate_prompt(graph_dict)

    try:
        raw = await call_qwen(system_prompt, user_prompt)

        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        annotations = json.loads(text)

        return {
            "status": "ok",
            "annotations": annotations,
        }
    except (json.JSONDecodeError, Exception) as e:
        # Graceful degradation
        fallback = {}
        for qname, d in graph_dict.get("definitions", {}).items():
            fallback[qname] = {
                "label": d.get("name", qname.split("::")[-1]),
                "description": d.get("docstring") or d.get("kind", ""),
            }
        return {
            "status": "fallback",
            "error": str(e),
            "annotations": fallback,
        }
