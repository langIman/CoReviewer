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


def build_flow_data(graph: ProjectAST) -> dict:
    """Convert call graph to React Flow-compatible nodes & edges.

    Layer 1 (module level): each file is a node, import = edge
    Layer 2 (function level): each function is a node, call = edge

    Returns the complete flow data with both layers.
    """
    # --- Module-level graph ---
    module_nodes = []
    module_edges = []
    mod_id_map: dict[str, str] = {}  # file_path -> node id

    for i, (path, mod) in enumerate(sorted(graph.modules.items())):
        node_id = f"mod-{i}"
        mod_id_map[path] = node_id
        short_name = path.split("/")[-1]
        module_nodes.append({
            "id": node_id,
            "type": "process",
            "label": short_name,
            "description": f"{mod.symbol_count} 个定义, {mod.line_count} 行",
            "file": path,
            "lineStart": 1,
            "lineEnd": mod.line_count,
            "expandable": True,
            "is_entry": any(
                d.is_entry for d in graph.definitions.values() if d.file == path
            ),
            "full_path": path,
        })

    for path, mod in graph.modules.items():
        src_id = mod_id_map.get(path)
        if not src_id:
            continue
        for imp_path in mod.imports:
            tgt_id = mod_id_map.get(imp_path)
            if tgt_id:
                module_edges.append({
                    "source": src_id,
                    "target": tgt_id,
                    "label": "import",
                })

    # --- Function-level graphs (per module) ---
    function_levels: dict[str, dict] = {}

    for path in sorted(graph.modules.keys()):
        file_defs = [
            d for d in graph.definitions.values() if d.file == path
        ]
        if not file_defs:
            continue

        fn_nodes = []
        fn_edges = []
        fn_id_map: dict[str, str] = {}  # qualified_name -> node id

        for j, defn in enumerate(sorted(file_defs, key=lambda d: d.line_start)):
            node_id = f"fn-{j}"
            fn_id_map[defn.qualified_name] = node_id

            # Determine if expandable: has outgoing calls to project functions
            has_calls = any(
                e.callee_resolved and e.callee_resolved in graph.definitions
                for e in graph.edges
                if e.caller == defn.qualified_name
            )

            fn_nodes.append({
                "id": node_id,
                "type": "process",
                "label": defn.name,
                "description": defn.docstring or defn.kind,
                "file": defn.file,
                "lineStart": defn.line_start,
                "lineEnd": defn.line_end,
                "expandable": has_calls or defn.line_end - defn.line_start > 10,
                "is_entry": defn.is_entry,
                "qualified_name": defn.qualified_name,
                "kind": defn.kind,
                "params": defn.params,
                "decorators": defn.decorators,
            })

        # Edges: only resolved, same-file calls
        seen_edges: set[tuple[str, str]] = set()
        for edge in graph.edges:
            if edge.file != path:
                continue
            if not edge.callee_resolved:
                continue
            src_id = fn_id_map.get(edge.caller)
            tgt_id = fn_id_map.get(edge.callee_resolved)
            if src_id and tgt_id and src_id != tgt_id:
                edge_key = (src_id, tgt_id)
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    fn_edges.append({
                        "source": src_id,
                        "target": tgt_id,
                        "label": edge.callee_name,
                        "call_line": edge.line,
                        "call_file": edge.file,
                    })

        function_levels[path] = {
            "nodes": fn_nodes,
            "edges": fn_edges,
        }

    return {
        "module_level": {
            "nodes": module_nodes,
            "edges": module_edges,
        },
        "function_level": function_levels,
    }


