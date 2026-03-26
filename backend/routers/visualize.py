import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.llm import call_qwen
from backend.services.file_service import get_project_files
from backend.services.prompts.visualize import build_flowchart_prompt, build_detail_prompt
from backend.services.symbol_resolver import resolve_symbol

router = APIRouter()


def _parse_llm_json(raw: str) -> dict:
    """清理 LLM 返回的文本并解析为 JSON。"""
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
    """强制将所有 id/source/target 转为字符串，并过滤引用不存在节点的边。"""
    if "nodes" not in data or "edges" not in data:
        raise HTTPException(status_code=500, detail="LLM response missing nodes or edges")

    # 统一 ID 为字符串
    for node in data["nodes"]:
        node["id"] = str(node["id"])

    valid_ids = {node["id"] for node in data["nodes"]}

    for edge in data["edges"]:
        edge["source"] = str(edge["source"])
        edge["target"] = str(edge["target"])

    # 过滤掉引用不存在节点的边
    data["edges"] = [
        e for e in data["edges"]
        if e["source"] in valid_ids and e["target"] in valid_ids
    ]


def _resolve_line_numbers(data: dict, project_files: dict[str, str]) -> None:
    """将节点中的 symbol + code_snippet 解析为真实的 lineStart/lineEnd。"""
    for node in data["nodes"]:
        symbol = node.pop("symbol", None)
        code_snippet = node.pop("code_snippet", None)
        # 同时清理旧的 line 字段（兼容 LLM 仍然返回 line 的情况）
        node.pop("line", None)

        file_path = node.get("file")
        if not file_path or file_path not in project_files:
            continue

        source = project_files[file_path]
        resolved = resolve_symbol(source, symbol=symbol, code_snippet=code_snippet)

        if resolved:
            node["lineStart"] = resolved.start
            node["lineEnd"] = resolved.end
        # 解析失败则不设置行号，前端点击时不跳转


@router.post("/api/visualize")
async def visualize_project():
    project_files = get_project_files()
    if not project_files:
        raise HTTPException(status_code=400, detail="No project loaded")

    system_prompt, user_prompt = build_flowchart_prompt(project_files)
    raw = await call_qwen(system_prompt, user_prompt)
    data = _parse_llm_json(raw)
    _normalize_flow_data(data)
    _resolve_line_numbers(data, project_files)
    return data


class DetailRequest(BaseModel):
    label: str
    description: str
    file: str = ""
    symbol: str = ""


@router.post("/api/visualize/detail")
async def visualize_detail(req: DetailRequest):
    project_files = get_project_files()
    if not project_files:
        raise HTTPException(status_code=400, detail="No project loaded")

    system_prompt, user_prompt = build_detail_prompt(
        step_label=req.label,
        step_description=req.description,
        step_file=req.file,
        step_symbol=req.symbol,
        project_files=project_files,
    )
    raw = await call_qwen(system_prompt, user_prompt)
    data = _parse_llm_json(raw)
    _normalize_flow_data(data)
    _resolve_line_numbers(data, project_files)
    return data
