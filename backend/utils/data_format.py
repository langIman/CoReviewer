"""
数据流格式化、验证和增强工具。
通过概览、详情、注释和可视化服务进行共享。
"""

import json

from fastapi import HTTPException
from backend.models.graph_models import ProjectAST


def parse_llm_json(raw: str) -> dict:
    """Clean and parse LLM response text as JSON."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"LLM returned invalid JSON: {text[:200]}")


def normalize_flow_data(data: dict) -> None:
    """Force all id/source/target to string and filter invalid edges."""
    if "nodes" not in data or "edges" not in data:
        raise HTTPException(status_code=500, detail="LLM response missing nodes or edges")

    for node in data["nodes"]:
        node["id"] = str(node["id"])

    valid_ids = {node["id"] for node in data["nodes"]}

    for edge in data["edges"]:
        edge["source"] = str(edge["source"])
        edge["target"] = str(edge["target"])

    data["edges"] = [
        e for e in data["edges"]
        if e["source"] in valid_ids and e["target"] in valid_ids
    ]


def fill_line_numbers_from_ast(data: dict, graph: ProjectAST) -> None:
    """Fill lineStart/lineEnd from AST definitions as fallback.

    If LLM already provided lineStart/lineEnd (e.g. pointing to call sites
    in the entry function), respect those values. Only fill from AST
    definitions when the LLM didn't provide line numbers.
    """
    for node in data["nodes"]:
        # Clean up legacy fields
        node.pop("line", None)
        node.pop("code_snippet", None)

        # If LLM already provided line numbers, keep them
        if node.get("lineStart") and node.get("lineEnd"):
            continue

        symbol = node.get("symbol")
        file_path = node.get("file")
        if not symbol or not file_path:
            continue

        # Fallback: look up from AST definitions
        qname = f"{file_path}::{symbol}"
        defn = graph.definitions.get(qname)

        if not defn:
            for dname, d in graph.definitions.items():
                if d.file == file_path and d.name == symbol:
                    defn = d
                    break

        if not defn:
            for dname, d in graph.definitions.items():
                if d.name == symbol:
                    defn = d
                    node["file"] = d.file
                    break

        if defn:
            node["lineStart"] = defn.line_start
            node["lineEnd"] = defn.line_end


