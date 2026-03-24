from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import file, review, visualize

app = FastAPI(title="CoReviewer", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(file.router)
app.include_router(review.router)
app.include_router(visualize.router)


@app.get("/api/health")
async def health():
    from backend.config import QWEN_MODEL
    return {"status": "ok", "model": QWEN_MODEL}
