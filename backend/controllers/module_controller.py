import logging

from fastapi import APIRouter, HTTPException

from backend.services.module_service import generate_module_split

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/module", tags=["module"])


@router.post("/split")
async def split_modules():
    try:
        result = await generate_module_split()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
