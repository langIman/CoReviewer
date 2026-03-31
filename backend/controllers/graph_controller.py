"""Controller for AST-based project analysis endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.overview_service import generate_overview
from backend.services.detail_service import generate_detail
router = APIRouter()


class FunctionDetailRequest(BaseModel):
    qualified_name: str



@router.post("/api/graph/overview")
async def analyze_overview():
    """Semantic overview flowchart from entry function source + LLM."""
    return await generate_overview()


@router.post("/api/graph/detail")
async def analyze_detail(req: FunctionDetailRequest):
    """Expand a function's internal logic into a flowchart."""
    return await generate_detail(req.qualified_name)

