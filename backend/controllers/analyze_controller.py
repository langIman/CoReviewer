"""Controller for AST-based project analysis endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

from backend.dao.graph_cache import get_or_build_graph
from backend.services.flow_service import build_flow_data
from backend.services.overview_service import generate_overview
from backend.services.detail_service import generate_detail
from backend.services.annotate_service import annotate

router = APIRouter()


class AnnotateRequest(BaseModel):
    modules: list[str] | None = None


class FunctionDetailRequest(BaseModel):
    qualified_name: str


@router.post("/api/analyze/graph")
async def analyze_graph():
    """Pure AST analysis — returns call graph + FlowData in milliseconds."""
    graph, _ = get_or_build_graph()
    return {**graph.to_dict(), "flow": build_flow_data(graph)}


@router.post("/api/analyze/overview")
async def analyze_overview():
    """Semantic overview flowchart from entry function source + LLM."""
    return await generate_overview()


@router.post("/api/analyze/detail")
async def analyze_detail(req: FunctionDetailRequest):
    """Expand a function's internal logic into a flowchart."""
    return await generate_detail(req.qualified_name)


@router.post("/api/analyze/annotate")
async def analyze_annotate(req: AnnotateRequest | None = None):
    """LLM semantic annotation of call graph nodes."""
    modules = req.modules if req else None
    return await annotate(modules)
