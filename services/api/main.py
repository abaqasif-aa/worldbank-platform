from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

from cache import seed_country_cache, get_country_metadata
from rag import rag_query
from query_engine import classify_question, sql_query, hybrid_query

app = FastAPI(title="World Bank Platform API")


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}


# ── Cache ─────────────────────────────────────────────────────────────────────
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

    # Step 1 — classify the question
    route = classify_question(request.question)

    # Step 2 — route to the appropriate handler
    if route == "OUT_OF_RANGE":
        return {
            "answer": "Our dataset covers 2000-2023 only. Please ask about a year within that range.",
            "sources": [],
            "context_records": 0,
            "route": "OUT_OF_RANGE",
        }

    elif route == "SQL":
        return sql_query(request.question)

    elif route == "HYBRID":
        return hybrid_query(
            question=request.question,
            rag_query_fn=lambda q, top_k: rag_query(q, top_k=top_k),
        )

    else:  # SEMANTIC
        return rag_query(
            question=request.question,
            region=request.region,
            top_k=request.top_k,
        )