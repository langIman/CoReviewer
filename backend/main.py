from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.controllers import (
    file_controller,
    review_controller,
    graph_controller,
)

app = FastAPI(title="CoReviewer", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(file_controller.router)
app.include_router(review_controller.router)
app.include_router(graph_controller.router)


@app.get("/api/health")
async def health():
    from backend.config import QWEN_MODEL
    return {"status": "ok", "model": QWEN_MODEL}
