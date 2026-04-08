import logging

from fastapi import APIRouter, HTTPException

from backend.services.summary_service import generate_hierarchical_summary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/summary", tags=["summary"])


@router.post("/generate")
async def generate_summary():
    try:
        result = await generate_hierarchical_summary()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
