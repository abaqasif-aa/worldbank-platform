from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

from cache import seed_country_cache, get_country_metadata
from rag import rag_query


app = FastAPI(title="World Bank Platform API")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/cache/seed")
def cache_seed():
    count = seed_country_cache()
    return {"status": "ok", "countries_cached": count}


@app.get("/countries/{country_code}")
def country_lookup(country_code: str):
    data = get_country_metadata(country_code)
    if data is None:
        raise HTTPException(status_code=404, detail="Country not found")
    return data


# ── RAG ───────────────────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str
    region: Optional[str] = None
    top_k: Optional[int] = 10


@app.post("/ask")
def ask(request: AskRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    result = rag_query(
        question=request.question,
        region=request.region,
        top_k=request.top_k,
    )
    return result