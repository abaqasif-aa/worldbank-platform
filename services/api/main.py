from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

from cache import seed_country_cache, get_country_metadata, get_conversation_history, append_to_conversation
from rag import rag_query
from query_engine import classify_question, sql_query, hybrid_query, resolve_question

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
    session_id: Optional[str] = None


@app.post("/ask")
def ask(request: AskRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # Step 1 — load conversation history if a session is provided
    history = []
    if request.session_id:
        history = get_conversation_history(request.session_id)

    # Step 2 — resolve the question using history (no-op if history is empty)
    resolved_question = resolve_question(request.question, history)

    # Step 3 — classify and route (existing pipeline, now on resolved question)
    route = classify_question(resolved_question)

    if route == "OUT_OF_RANGE":
        result = {
            "answer": "Our dataset covers 2000-2023 only. Please ask about a year within that range.",
            "sources": [],
            "context_records": 0,
            "route": "OUT_OF_RANGE",
        }

    elif route == "SQL":
        result = sql_query(resolved_question)

    elif route == "HYBRID":
        result = hybrid_query(
            question=resolved_question,
            rag_query_fn=lambda q, top_k: rag_query(q, top_k=top_k),
        )

    else:  # SEMANTIC
        result = rag_query(
            question=resolved_question,
            region=request.region,
            top_k=request.top_k,
        )

    # Step 4 — save this turn to history if a session is provided
    if request.session_id:
        append_to_conversation(
            session_id=request.session_id,
            question=resolved_question,
            answer=result["answer"],
        )

    result["resolved_question"] = resolved_question
    return result