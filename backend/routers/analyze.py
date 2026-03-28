"""API router for AST-based project analysis (P1 + P2).

Endpoints:
- POST /api/analyze/graph     — Pure AST analysis, returns FlowData (milliseconds)
- POST /api/analyze/annotate  — LLM semantic annotation (async, graceful fallback)
- POST /api/analyze/detail    — Expand function internals via LLM
"""

import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.call_graph import CallGraph, build_call_graph
from backend.services.entry_detector import detect_entry_points
from backend.services.file_service import get_project_files
from backend.services.llm import call_qwen
from backend.services.prompts.annotate import (
    build_annotate_prompt,
    build_function_detail_prompt,
    build_overview_prompt,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Graph cache (invalidated on new project upload)
# ---------------------------------------------------------------------------
_cached_graph: CallGraph | None = None
_cached_project_files: dict[str, str] | None = None

#创建由ast分析构建的调用图的缓存。
def _get_or_build_graph() -> tuple[CallGraph, dict[str, str]]:
    """Get cached graph or build a new one. Returns (graph, project_files)."""
    global _cached_graph, _cached_project_files
    project_files = get_project_files()
    if not project_files:
        raise HTTPException(status_code=400, detail="No project loaded")

    if _cached_graph is None or _cached_project_files is not project_files:
        _cached_graph = build_call_graph(project_files)
        detect_entry_points(_cached_graph, project_files)
        _cached_project_files = project_files

    return _cached_graph, project_files


def invalidate_graph_cache() -> None:
    """Call when project changes (new upload)."""
    global _cached_graph, _cached_project_files
    _cached_graph = None
    _cached_project_files = None


# ---------------------------------------------------------------------------
# FlowData builder: converts CallGraph → React Flow compatible format
# ---------------------------------------------------------------------------
#将ast分析得到的调用图转换为React Flow兼容的节点和边格式，分为模块层和函数层两层结构。模块层节点表示文件，边表示import关系；函数层节点表示函数/方法，边表示调用关系。每个节点包含文件路径、行号、定义类型等元信息，供前端展示和交互使用。
def _build_flow_data(graph: CallGraph) -> dict:
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


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/analyze/graph")
async def analyze_graph():
    """Return the complete call graph built from AST analysis.

    Response includes:
    - modules: module-level dependency graph
    - definitions: all function/class/method definitions with exact line numbers
    - edges: all call relationships
    - flow: React Flow-compatible nodes & edges for both layers
    """
    graph, project_files = _get_or_build_graph()
    raw = graph.to_dict()
    flow = _build_flow_data(graph)

    return {
        **raw,
        "flow": flow,
    }


# --- Overview endpoint: semantic flowchart from AST skeleton ---

@router.post("/api/analyze/overview")
async def analyze_overview():
    """Generate a semantic flowchart (start/process/decision/end) from AST skeleton.

    This replaces the old /api/visualize endpoint with:
    - Input: AST skeleton (signatures + call graph) instead of full source code
    - Output: same FlowData format (nodes + edges) as before
    - Post-processing: line numbers filled from AST (100% accurate)

    Token usage is dramatically lower than the old approach.
    """
    graph, project_files = _get_or_build_graph()
    graph_dict = graph.to_dict()

    system_prompt, user_prompt = build_overview_prompt(graph_dict)
    raw = await call_qwen(system_prompt, user_prompt)
    data = _parse_llm_json(raw)
    _normalize_flow_data(data)
    _fill_line_numbers_from_ast(data, graph)

    return data


def _parse_llm_json(raw: str) -> dict:
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


def _normalize_flow_data(data: dict) -> None:
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


def _fill_line_numbers_from_ast(data: dict, graph: CallGraph) -> None:
    """Fill lineStart/lineEnd from AST definitions instead of guessing.

    For each process node with a 'symbol' field, look up the exact line
    numbers from the call graph's definitions. This replaces the old
    4-level-fallback symbol_resolver approach with 100% accurate data.
    """
    for node in data["nodes"]:
        symbol = node.get("symbol")
        file_path = node.get("file")
        if not symbol or not file_path:
            continue

        # Remove any existing inaccurate line numbers from LLM
        node.pop("line", None)
        node.pop("code_snippet", None)

        # Try to find exact match in AST definitions
        qname = f"{file_path}::{symbol}"
        defn = graph.definitions.get(qname)

        if not defn:
            # Try searching by name across all definitions in the file
            for dname, d in graph.definitions.items():
                if d.file == file_path and d.name == symbol:
                    defn = d
                    break

        if not defn:
            # Try searching by name across ALL definitions
            for dname, d in graph.definitions.items():
                if d.name == symbol:
                    defn = d
                    # Also fix the file path
                    node["file"] = d.file
                    break

        if defn:
            node["lineStart"] = defn.line_start
            node["lineEnd"] = defn.line_end


# --- Annotation endpoint (P2) ---

class AnnotateRequest(BaseModel):
    """Optional filter: only annotate specific modules."""
    modules: list[str] | None = None


@router.post("/api/analyze/annotate")
async def analyze_annotate(req: AnnotateRequest | None = None):
    """Ask LLM to annotate call graph nodes with Chinese labels.

    LLM receives only signatures + call relationships (no full code).
    Falls back gracefully: returns raw function names if LLM fails.
    """
    graph, project_files = _get_or_build_graph()
    graph_dict = graph.to_dict()

    # Optionally filter to specific modules
    if req and req.modules:
        filtered_defs = {
            k: v for k, v in graph_dict["definitions"].items()
            if any(v["file"].startswith(m) for m in req.modules)
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

        # Parse response
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
        # Graceful degradation: return function names as labels
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


# --- Function detail endpoint (P2) ---

class FunctionDetailRequest(BaseModel):
    qualified_name: str


@router.post("/api/analyze/detail")
async def analyze_detail(req: FunctionDetailRequest):
    """Expand a function's internal logic into a flowchart.

    This is the only endpoint that sends actual source code to LLM,
    but only for ONE specific function (not the entire project).
    """
    graph, project_files = _get_or_build_graph()

    defn = graph.definitions.get(req.qualified_name)
    if not defn:
        raise HTTPException(status_code=404, detail=f"Function not found: {req.qualified_name}")

    source = project_files.get(defn.file)
    if not source:
        raise HTTPException(status_code=404, detail=f"Source file not found: {defn.file}")

    # Extract just this function's source code
    lines = source.split("\n")
    func_source = "\n".join(lines[defn.line_start - 1 : defn.line_end])

    # Build signature string
    params_str = ", ".join(defn.params)
    signature = f"def {defn.name}({params_str})"

    # Collect info about functions this one calls
    called_functions: list[dict] = []
    for edge in graph.edges:
        if edge.caller == req.qualified_name and edge.callee_resolved:
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

    raw = await call_qwen(system_prompt, user_prompt)

    # Parse LLM response
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"LLM returned invalid JSON: {text[:200]}")

    # Normalize ids to strings and filter invalid edges
    if "nodes" not in data or "edges" not in data:
        raise HTTPException(status_code=500, detail="LLM response missing nodes or edges")

    for node in data["nodes"]:
        node["id"] = str(node["id"])
        # Ensure file and line info
        if "file" not in node:
            node["file"] = defn.file

    valid_ids = {node["id"] for node in data["nodes"]}
    for edge in data["edges"]:
        edge["source"] = str(edge["source"])
        edge["target"] = str(edge["target"])
    data["edges"] = [
        e for e in data["edges"]
        if e["source"] in valid_ids and e["target"] in valid_ids
    ]

    return data
