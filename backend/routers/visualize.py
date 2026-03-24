import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.llm import call_qwen
from backend.services.file_service import get_project_files
from backend.services.prompts.visualize import build_flowchart_prompt, build_detail_prompt

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


def _validate_flow_data(data: dict) -> None:
    if "nodes" not in data or "edges" not in data:
        raise HTTPException(status_code=500, detail="LLM response missing nodes or edges")


@router.post("/api/visualize")
async def visualize_project():
    project_files = get_project_files()
    if not project_files:
        raise HTTPException(status_code=400, detail="No project loaded")

    system_prompt, user_prompt = build_flowchart_prompt(project_files)
    raw = await call_qwen(system_prompt, user_prompt)
    data = _parse_llm_json(raw)
    _validate_flow_data(data)
    return data


class DetailRequest(BaseModel):
    label: str
    description: str
    file: str = ""
    line: int = 0


@router.post("/api/visualize/detail")
async def visualize_detail(req: DetailRequest):
    project_files = get_project_files()
    if not project_files:
        raise HTTPException(status_code=400, detail="No project loaded")

    system_prompt, user_prompt = build_detail_prompt(
        step_label=req.label,
        step_description=req.description,
        step_file=req.file,
        step_line=req.line,
        project_files=project_files,
    )
    raw = await call_qwen(system_prompt, user_prompt)
    data = _parse_llm_json(raw)
    _validate_flow_data(data)
    return data
